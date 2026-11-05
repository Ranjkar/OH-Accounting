"use client";

import { FormEvent, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, Company, JsonReport } from "@/lib/api";
import { formatEUR } from "@/lib/format";

function EmployeesContent() {
  const t = useTranslations("payroll");
  const tCommon = useTranslations("common");
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
      <h1 className="text-2xl font-semibold text-text-primary">{t("employees")}</h1>
      <p className="text-sm text-text-secondary">{t("bsnEncryptionNotice")}</p>
      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}

      <select aria-label={tCommon("company")} value={companyId} onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")} className="input-v2 px-3 py-2 text-sm">
        <option value="">{tCommon("selectCompany")}</option>
        {companies.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </select>

      {companyId && (
        <form onSubmit={createEmployee} className="card-v2 p-4 space-y-3">
          <h2 className="font-medium text-text-primary">{t("addEmployee")}</h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <input aria-label={t("employeeNumber")} required value={employeeNumber} onChange={(e) => setEmployeeNumber(e.target.value)} placeholder={t("employeeNumber")} className="input-v2 px-3 py-2 text-sm" />
            <input aria-label={t("fullName")} required value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder={t("fullName")} className="input-v2 px-3 py-2 text-sm" />
            <input aria-label={t("bsnOptional")} value={bsn} onChange={(e) => setBsn(e.target.value)} placeholder={t("bsnOptional")} className="input-v2 px-3 py-2 text-sm" />
            <input aria-label={t("employmentStartDate")} type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="input-v2 px-3 py-2 text-sm" />
            <select aria-label={t("salaryBasis")} value={salaryBasis} onChange={(e) => setSalaryBasis(e.target.value as "MONTHLY" | "HOURLY")} className="input-v2 px-3 py-2 text-sm">
              <option value="MONTHLY">{t("monthlySalary")}</option>
              <option value="HOURLY">{t("hourlyRate")}</option>
            </select>
            {salaryBasis === "MONTHLY" ? (
              <input aria-label={t("monthlySalaryEur")} required value={monthlySalary} onChange={(e) => setMonthlySalary(e.target.value)} placeholder={t("monthlySalaryEur")} className="input-v2 px-3 py-2 text-sm" />
            ) : (
              <input aria-label={t("hourlyRateEur")} required value={hourlyRate} onChange={(e) => setHourlyRate(e.target.value)} placeholder={t("hourlyRateEur")} className="input-v2 px-3 py-2 text-sm" />
            )}
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={isDga} onChange={(e) => setIsDga(e.target.checked)} /> {t("director")}
          </label>
          <button type="submit" className="btn-primary-v2 px-4 py-2 text-sm">
            {t("addEmployee")}
          </button>
        </form>
      )}

      <div className="card-v2 overflow-hidden">
        <div className="overflow-x-auto">
        <table className="table-v3">
          <thead>
            <tr>
              <th>{t("number")}</th>
              <th>{tCommon("name")}</th>
              <th>{t("bsn")}</th>
              <th className="text-right">{t("salary")}</th>
              <th>{t("dga")}</th>
            </tr>
          </thead>
          <tbody>
            {employees.map((emp) => (
              <tr key={emp.id}>
                <td className="text-text-secondary">{emp.employee_number}</td>
                <td className="text-text-primary">{emp.full_name}</td>
                <td className="font-mono text-xs text-text-secondary">{emp.bsn_masked ?? "—"}</td>
                <td className="col-amount">{emp.salary_basis === "MONTHLY" ? formatEUR(emp.monthly_salary) : t("perHour", { amount: formatEUR(emp.hourly_rate) })}</td>
                <td>{emp.is_dga ? tCommon("yes") : ""}</td>
              </tr>
            ))}
            {employees.length === 0 && (
              <tr>
                <td colSpan={5} className="text-text-secondary">
                  {t("noEmployeesYet")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
        </div>
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
