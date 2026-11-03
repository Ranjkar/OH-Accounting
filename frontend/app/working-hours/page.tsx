"use client";

import { FormEvent, useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, Company, JsonReport } from "@/lib/api";

function WorkingHoursContent() {
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [employees, setEmployees] = useState<JsonReport[]>([]);
  const [employeeId, setEmployeeId] = useState<number | "">("");
  const [entries, setEntries] = useState<JsonReport[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [entryDate, setEntryDate] = useState("2025-03-01");
  const [entryType, setEntryType] = useState("WORKED");
  const [hours, setHours] = useState("8");

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  useEffect(() => {
    if (!token || !companyId) return;
    api.listEmployees(token, Number(companyId)).then(setEmployees).catch((e) => setError(e.message));
  }, [token, companyId]);

  function refresh() {
    if (!token || !employeeId) return;
    api.listTimesheetEntries(token, Number(employeeId)).then(setEntries).catch((e) => setError(e.message));
  }

  useEffect(refresh, [token, employeeId]);

  async function createEntry(e: FormEvent) {
    e.preventDefault();
    if (!token || !employeeId) return;
    try {
      await api.createTimesheetEntry(token, { employee_id: Number(employeeId), entry_date: entryDate, entry_type: entryType, hours });
      refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function submit(entry: JsonReport) {
    if (!token) return;
    await api.submitTimesheetEntry(token, entry.id);
    refresh();
  }
  async function approve(entry: JsonReport) {
    if (!token) return;
    await api.approveTimesheetEntry(token, entry.id);
    refresh();
  }
  async function reject(entry: JsonReport) {
    if (!token) return;
    await api.rejectTimesheetEntry(token, entry.id);
    refresh();
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-text-primary">Working Hours</h1>
      <p className="text-sm text-text-secondary">Employee timesheets with a submit/approve/reject audit trail.</p>
      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="flex items-center gap-3">
        <select value={companyId} aria-label="Company" onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")} className="input-v2 px-3 py-2 text-sm">
          <option value="">Select a company</option>
          {companies.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        {companyId && (
          <select value={employeeId} aria-label="Employee" onChange={(e) => setEmployeeId(e.target.value ? Number(e.target.value) : "")} className="input-v2 px-3 py-2 text-sm">
            <option value="">Select an employee</option>
            {employees.map((emp) => (
              <option key={emp.id} value={emp.id}>
                {emp.full_name}
              </option>
            ))}
          </select>
        )}
      </div>

      {employeeId && (
        <>
          <form onSubmit={createEntry} className="card-v2 p-4 flex items-end gap-3">
            <input type="date" value={entryDate} aria-label="Entry Date" onChange={(e) => setEntryDate(e.target.value)} className="input-v2 px-3 py-2 text-sm" />
            <select value={entryType} aria-label="Entry Type" onChange={(e) => setEntryType(e.target.value)} className="input-v2 px-3 py-2 text-sm">
              <option value="WORKED">Worked</option>
              <option value="HOLIDAY">Holiday</option>
              <option value="SICK">Sick</option>
              <option value="ABSENCE">Absence</option>
            </select>
            <input value={hours} aria-label="Hours" onChange={(e) => setHours(e.target.value)} placeholder="Hours" className="input-v2 px-3 py-2 text-sm w-24" />
            <button type="submit" className="btn-primary-v2 px-4 py-2 text-sm">
              Log entry
            </button>
          </form>

          <div className="card-v2 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-text-secondary border-b border-border-subtle">
                  <th className="px-4 py-2 font-medium">Date</th>
                  <th className="px-4 py-2 font-medium">Type</th>
                  <th className="px-4 py-2 font-medium">Hours</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="px-4 py-2 font-medium" />
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => (
                  <tr key={entry.id} className="border-b border-border-subtle last:border-0">
                    <td className="px-4 py-2.5">{entry.entry_date}</td>
                    <td className="px-4 py-2.5">{entry.entry_type}</td>
                    <td className="px-4 py-2.5 font-mono">{entry.hours}</td>
                    <td className="px-4 py-2.5">{entry.status}</td>
                    <td className="px-4 py-2.5 text-xs">
                      {entry.status === "DRAFT" && (
                        <button onClick={() => submit(entry)} className="underline">
                          Submit
                        </button>
                      )}
                      {entry.status === "SUBMITTED" && (
                        <span className="flex gap-2">
                          <button onClick={() => approve(entry)} className="underline">
                            Approve
                          </button>
                          <button onClick={() => reject(entry)} className="underline">
                            Reject
                          </button>
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
                {entries.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-4 py-4 text-text-secondary">
                      No entries yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

export default function WorkingHoursPage() {
  return (
    <AuthGuard>
      <Shell>
        <WorkingHoursContent />
      </Shell>
    </AuthGuard>
  );
}
