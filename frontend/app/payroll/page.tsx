"use client";

import { FormEvent, useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, Company, JsonReport } from "@/lib/api";
import { formatEUR } from "@/lib/format";

function PayrollContent() {
  const t = useTranslations("payroll");
  const tCommon = useTranslations("common");
  const locale = useLocale();
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [employees, setEmployees] = useState<JsonReport[]>([]);
  const [runs, setRuns] = useState<JsonReport[]>([]);
  const [selectedRun, setSelectedRun] = useState<JsonReport | null>(null);
  const [payslips, setPayslips] = useState<JsonReport[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const [periodYear, setPeriodYear] = useState(2025);
  const [periodNumber, setPeriodNumber] = useState(3);
  const [selectedEmployeeId, setSelectedEmployeeId] = useState<number | "">("");
  const [bonus, setBonus] = useState("0");
  const [payHolidayAllowance, setPayHolidayAllowance] = useState(false);

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  function refresh() {
    if (!token || !companyId) return;
    api.listEmployees(token, Number(companyId)).then(setEmployees).catch((e) => setError(e.message));
    api.listPayrollRuns(token, Number(companyId)).then(setRuns).catch((e) => setError(e.message));
  }

  useEffect(refresh, [token, companyId]);

  async function viewRun(run: JsonReport) {
    if (!token) return;
    setSelectedRun(run);
    try {
      setPayslips(await api.listPayslips(token, run.id));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function createRun(e: FormEvent) {
    e.preventDefault();
    if (!token || !companyId) return;
    try {
      await api.createPayrollRun(token, { company_id: Number(companyId), period_type: "MONTHLY", period_year: periodYear, period_number: periodNumber });
      refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function addPayslip() {
    if (!token || !selectedRun || !selectedEmployeeId) return;
    try {
      await api.addPayslip(token, selectedRun.id, {
        employee_id: Number(selectedEmployeeId), bonus_amount: bonus, pay_holiday_allowance_this_period: payHolidayAllowance,
      });
      viewRun(selectedRun);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function approve() {
    if (!token || !selectedRun) return;
    try {
      const updated = await api.approvePayrollRun(token, selectedRun.id);
      setSelectedRun(updated);
      refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function markPaid() {
    if (!token || !selectedRun) return;
    const updated = await api.markPayrollRunPaid(token, selectedRun.id);
    setSelectedRun(updated);
    refresh();
  }

  async function correct(payslip: JsonReport) {
    if (!token) return;
    const reason = window.prompt(t("reasonForCorrection"));
    if (!reason) return;
    await api.correctPayslip(token, payslip.id, { reason, bonus_amount: "0" });
    setMessage(t("correctionCreatedNotice"));
    if (selectedRun) viewRun(selectedRun);
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-text-primary">{t("title")}</h1>
      <p className="text-sm text-text-secondary">{t("deterministicNotice")}</p>
      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}
      {message && <div className="rounded-md bg-green-50 text-green-700 text-sm px-3 py-2">{message}</div>}

      <select aria-label={tCommon("company")} value={companyId} onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")} className="input-v2 px-3 py-2 text-sm">
        <option value="">{tCommon("selectCompany")}</option>
        {companies.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </select>

      {companyId && (
        <form onSubmit={createRun} className="card-v2 p-4 flex items-end gap-3">
          <input aria-label={t("periodYear")} type="number" value={periodYear} onChange={(e) => setPeriodYear(Number(e.target.value))} className="input-v2 px-3 py-2 text-sm w-24" />
          <select aria-label={t("periodMonth")} value={periodNumber} onChange={(e) => setPeriodNumber(Number(e.target.value))} className="input-v2 px-3 py-2 text-sm">
            {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
              <option key={m} value={m}>
                {t("monthNumber", { month: m })}
              </option>
            ))}
          </select>
          <button type="submit" className="btn-primary-v2 px-4 py-2 text-sm">
            {t("createPayrollRun")}
          </button>
        </form>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card-v2 overflow-hidden">
          <div className="overflow-x-auto" tabIndex={0}>
          <table className="table-v3">
            <thead>
              <tr>
                <th>{t("period")}</th>
                <th>{tCommon("status")}</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr
                  key={run.id}
                  className="cursor-pointer hover:bg-muted"
                  onClick={() => viewRun(run)}
                  onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); viewRun(run); } }}
                  tabIndex={0}
                  role="button"
                >
                  <td className="text-text-primary">{run.period_type} {run.period_number}/{run.period_year}</td>
                  <td className="text-text-secondary">{t(`runStatus.${run.status}` as never)}</td>
                </tr>
              ))}
              {runs.length === 0 && (
                <tr>
                  <td colSpan={2} className="text-text-secondary">
                    {t("noPayrollRunsYet")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          </div>
        </div>

        <div className="card-v2 p-4">
          {selectedRun ? (
            <div className="space-y-3 text-sm">
              <h3 className="font-medium text-text-primary">
                {selectedRun.period_type} {selectedRun.period_number}/{selectedRun.period_year} -- {t(`runStatus.${selectedRun.status}` as never)}
              </h3>
              {selectedRun.status === "DRAFT" && (
                <div className="flex flex-wrap items-end gap-2">
                  <select aria-label={t("employee")} value={selectedEmployeeId} onChange={(e) => setSelectedEmployeeId(e.target.value ? Number(e.target.value) : "")} className="input-v2 px-2 py-1.5 text-xs">
                    <option value="">{t("employee")}</option>
                    {employees.map((emp) => (
                      <option key={emp.id} value={emp.id}>
                        {emp.full_name}
                      </option>
                    ))}
                  </select>
                  <input aria-label={t("bonus")} value={bonus} onChange={(e) => setBonus(e.target.value)} placeholder={t("bonus")} className="input-v2 px-2 py-1.5 text-xs w-20" />
                  <label className="flex items-center gap-1 text-xs">
                    <input type="checkbox" checked={payHolidayAllowance} onChange={(e) => setPayHolidayAllowance(e.target.checked)} /> {t("holidayAllowance")}
                  </label>
                  <button onClick={addPayslip} className="btn-secondary-v2 px-3 py-1.5 text-xs">
                    {t("addPayslip")}
                  </button>
                </div>
              )}
              {payslips.map((p) => (
                <div key={p.id} className="border border-border rounded-md p-2 flex items-center justify-between">
                  <span className="text-text-primary">
                    #{p.id} {p.voided && <span className="value-negative">({t("voided")})</span>}
                    {p.corrects_payslip_id && <span className="text-text-secondary"> {t("correctionOf", { id: p.corrects_payslip_id })}</span>}
                  </span>
                  <span className="font-mono tabular-nums text-text-primary">{formatEUR(p.gross_salary, locale)} → {formatEUR(p.net_salary, locale)}</span>
                  <div className="flex items-center gap-2">
                    <a href={api.payslipPdfUrl(p.id)} target="_blank" rel="noreferrer" className="text-xs text-navy hover:underline">
                      PDF
                    </a>
                    {!p.voided && (
                      <button onClick={() => correct(p)} className="text-xs text-navy hover:underline">
                        {t("correct")}
                      </button>
                    )}
                  </div>
                </div>
              ))}
              {selectedRun.status === "DRAFT" && (
                <button onClick={approve} className="btn-primary-v2 px-3 py-1.5 text-xs">
                  {t("approveRun")}
                </button>
              )}
              {selectedRun.status === "APPROVED" && (
                <button onClick={markPaid} className="btn-primary-v2 px-3 py-1.5 text-xs">
                  {t("markPaid")}
                </button>
              )}
            </div>
          ) : (
            <p className="text-sm text-text-secondary">{t("selectPayrollRun")}</p>
          )}
        </div>
      </div>
    </div>
  );
}

export default function PayrollPage() {
  return (
    <AuthGuard>
      <Shell>
        <PayrollContent />
      </Shell>
    </AuthGuard>
  );
}
