"use client";

import { FormEvent, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, Company, JsonReport } from "@/lib/api";

function WorkingHoursContent() {
  const t = useTranslations("workingHours");
  const tCommon = useTranslations("common");
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
      <h1 className="text-2xl font-semibold text-text-primary">{t("title")}</h1>
      <p className="text-sm text-text-secondary">{t("pageExplainer")}</p>
      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <div className="flex flex-wrap items-center gap-3">
        <select value={companyId} aria-label={tCommon("company")} onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")} className="input-v2 px-3 py-2 text-sm">
          <option value="">{tCommon("selectCompany")}</option>
          {companies.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        {companyId && (
          <select value={employeeId} aria-label={t("employee")} onChange={(e) => setEmployeeId(e.target.value ? Number(e.target.value) : "")} className="input-v2 px-3 py-2 text-sm">
            <option value="">{t("selectEmployee")}</option>
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
            <input type="date" value={entryDate} aria-label={t("entryDate")} onChange={(e) => setEntryDate(e.target.value)} className="input-v2 px-3 py-2 text-sm" />
            <select value={entryType} aria-label={t("entryType")} onChange={(e) => setEntryType(e.target.value)} className="input-v2 px-3 py-2 text-sm">
              <option value="WORKED">{t("worked")}</option>
              <option value="HOLIDAY">{t("holiday")}</option>
              <option value="SICK">{t("sick")}</option>
              <option value="ABSENCE">{t("absence")}</option>
            </select>
            <input inputMode="decimal" value={hours} aria-label={t("hours")} onChange={(e) => setHours(e.target.value)} placeholder={t("hours")} className="input-v2 px-3 py-2 text-sm w-24" />
            <button type="submit" className="btn-primary-v2 px-4 py-2 text-sm">
              {t("logEntry")}
            </button>
          </form>

          <div className="card-v2 overflow-hidden">
            <div className="overflow-x-auto" tabIndex={0}>
            <table className="table-v3">
              <thead>
                <tr>
                  <th>{tCommon("date")}</th>
                  <th>{t("type")}</th>
                  <th className="text-right">{t("hours")}</th>
                  <th>{tCommon("status")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => (
                  <tr key={entry.id}>
                    <td className="text-text-secondary">{entry.entry_date}</td>
                    <td className="text-text-primary">{entry.entry_type}</td>
                    <td className="text-right font-mono tabular-nums">{entry.hours}</td>
                    <td className="text-text-secondary">{entry.status}</td>
                    <td className="text-xs">
                      {entry.status === "DRAFT" && (
                        <button onClick={() => submit(entry)} className="text-navy hover:underline">
                          {t("submit")}
                        </button>
                      )}
                      {entry.status === "SUBMITTED" && (
                        <span className="flex flex-wrap gap-2">
                          <button onClick={() => approve(entry)} className="text-navy hover:underline">
                            {t("approve")}
                          </button>
                          <button onClick={() => reject(entry)} className="text-error hover:underline">
                            {t("reject")}
                          </button>
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
                {entries.length === 0 && (
                  <tr>
                    <td colSpan={5} className="text-text-secondary">
                      {t("noEntriesYet")}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
            </div>
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
