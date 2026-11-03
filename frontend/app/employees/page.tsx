"use client";

import { FormEvent, useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, Company, JsonReport } from "@/lib/api";

function EmployeesContent() {
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [employees, setEmployees] = useState<JsonReport[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [fullName, setFullName] = useState("");
  const [employeeNumber, setEmployeeNumber] = useState("");
  const [bsn, setBsn] = useState("");
  const [salaryBasis, setSalaryBasis] = useState<"MONTHLY" | "HOURLY">("MONTHLY");
  const [monthlySalary, setMonthlySalary] = useState("");
  const [hourlyRate, setHourlyRate] = useState("");
  const [startDate, setStartDate] = useState("2025-01-01");
  const [isDga, setIsDga] = useState(false);

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  function refresh() {
    if (!token || !companyId) return;
    api.listEmployees(token, Number(companyId)).then(setEmployees).catch((e) => setError(e.message));
  }

  useEffect(refresh, [token, companyId]);

  async function createEmployee(e: FormEvent) {
    e.preventDefault();
    if (!token || !companyId) return;
    try {
      await api.createEmployee(token, {
        company_id: Number(companyId), employee_number: employeeNumber, full_name: fullName,
        bsn: bsn || undefined, employment_start_date: startDate, employment_type: "PERMANENT",
        salary_basis: salaryBasis, monthly_salary: salaryBasis === "MONTHLY" ? monthlySalary : undefined,
        hourly_rate: salaryBasis === "HOURLY" ? hourlyRate : undefined, is_dga: isDga,
      });
      setFullName("");
      setEmployeeNumber("");
      setBsn("");
      setMonthlySalary("");
      setHourlyRate("");
      refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-text-primary">Employees</h1>
      <p className="text-sm text-text-secondary">
        BSN is encrypted at rest and only ever shown masked here -- it is never sent to the AI assistant or written
        to a log.
      </p>
      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <select value={companyId} onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")} className="input-v2 px-3 py-2 text-sm">
        <option value="">Select a company</option>
        {companies.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </select>

      {companyId && (
        <form onSubmit={createEmployee} className="card-v2 p-4 space-y-3">
          <h2 className="font-medium text-text-primary">Add employee</h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <input required value={employeeNumber} onChange={(e) => setEmployeeNumber(e.target.value)} placeholder="Employee number" className="input-v2 px-3 py-2 text-sm" />
            <input required value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Full name" className="input-v2 px-3 py-2 text-sm" />
            <input value={bsn} onChange={(e) => setBsn(e.target.value)} placeholder="BSN (optional)" className="input-v2 px-3 py-2 text-sm" />
            <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="input-v2 px-3 py-2 text-sm" />
            <select value={salaryBasis} onChange={(e) => setSalaryBasis(e.target.value as "MONTHLY" | "HOURLY")} className="input-v2 px-3 py-2 text-sm">
              <option value="MONTHLY">Monthly salary</option>
              <option value="HOURLY">Hourly rate</option>
            </select>
            {salaryBasis === "MONTHLY" ? (
              <input required value={monthlySalary} onChange={(e) => setMonthlySalary(e.target.value)} placeholder="Monthly salary (EUR)" className="input-v2 px-3 py-2 text-sm" />
            ) : (
              <input required value={hourlyRate} onChange={(e) => setHourlyRate(e.target.value)} placeholder="Hourly rate (EUR)" className="input-v2 px-3 py-2 text-sm" />
            )}
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={isDga} onChange={(e) => setIsDga(e.target.checked)} /> Director-shareholder (DGA)
          </label>
          <button type="submit" className="btn-primary-v2 px-4 py-2 text-sm">
            Add employee
          </button>
        </form>
      )}

      <div className="card-v2 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-text-secondary border-b border-border-subtle">
              <th className="px-4 py-2 font-medium">Number</th>
              <th className="px-4 py-2 font-medium">Name</th>
              <th className="px-4 py-2 font-medium">BSN</th>
              <th className="px-4 py-2 font-medium">Salary</th>
              <th className="px-4 py-2 font-medium">DGA</th>
            </tr>
          </thead>
          <tbody>
            {employees.map((emp) => (
              <tr key={emp.id} className="border-b border-border-subtle last:border-0">
                <td className="px-4 py-2.5">{emp.employee_number}</td>
                <td className="px-4 py-2.5">{emp.full_name}</td>
                <td className="px-4 py-2.5 font-mono text-xs">{emp.bsn_masked ?? "—"}</td>
                <td className="px-4 py-2.5 font-mono">{emp.salary_basis === "MONTHLY" ? emp.monthly_salary : `${emp.hourly_rate}/hr`}</td>
                <td className="px-4 py-2.5">{emp.is_dga ? "Yes" : ""}</td>
              </tr>
            ))}
            {employees.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-4 text-text-secondary">
                  No employees yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function EmployeesPage() {
  return (
    <AuthGuard>
      <Shell>
        <EmployeesContent />
      </Shell>
    </AuthGuard>
  );
}
