"use client";

import { FormEvent, useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, Company, JsonReport } from "@/lib/api";

function PayrollContent() {
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
    const reason = window.prompt("Reason for correction?");
    if (!reason) return;
    await api.correctPayslip(token, payslip.id, { reason, bonus_amount: "0" });
    setMessage("Correction created -- the original payslip is voided, never deleted.");
    if (selectedRun) viewRun(selectedRun);
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-text-primary">Salarisadministratie</h1>
      <p className="text-sm text-text-secondary">
        Deterministic Dutch payroll calculation -- wage tax/national insurance is approximated from the same tax
        brackets used elsewhere in this app, not an LLM. Figures are Decimal and never silently recalculated once
        issued; corrections void the original and create a new, linked payslip.
      </p>
      {error && <div className="rounded-md bg-red-50 text-error text-sm px-3 py-2">{error}</div>}
      {message && <div className="rounded-md bg-green-50 text-green-700 text-sm px-3 py-2">{message}</div>}

      <select value={companyId} onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")} className="input-v2 px-3 py-2 text-sm">
        <option value="">Select a company</option>
        {companies.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </select>

      {companyId && (
        <form onSubmit={createRun} className="card-v2 p-4 flex items-end gap-3">
          <input type="number" value={periodYear} onChange={(e) => setPeriodYear(Number(e.target.value))} className="input-v2 px-3 py-2 text-sm w-24" />
          <select value={periodNumber} onChange={(e) => setPeriodNumber(Number(e.target.value))} className="input-v2 px-3 py-2 text-sm">
            {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
              <option key={m} value={m}>
                Month {m}
              </option>
            ))}
          </select>
          <button type="submit" className="btn-primary-v2 px-4 py-2 text-sm">
            Create payroll run
          </button>
        </form>
      )}

      <div className="grid grid-cols-2 gap-6">
        <div className="card-v2 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-text-secondary border-b border-border-subtle">
                <th className="px-4 py-2 font-medium">Period</th>
                <th className="px-4 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.id} className="border-b border-border-subtle last:border-0 hover:bg-surface-page cursor-pointer" onClick={() => viewRun(run)}>
                  <td className="px-4 py-2.5">{run.period_type} {run.period_number}/{run.period_year}</td>
                  <td className="px-4 py-2.5">{run.status}</td>
                </tr>
              ))}
              {runs.length === 0 && (
                <tr>
                  <td colSpan={2} className="px-4 py-4 text-text-secondary">
                    No payroll runs yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="card-v2 p-4">
          {selectedRun ? (
            <div className="space-y-3 text-sm">
              <h3 className="font-medium text-text-primary">
                {selectedRun.period_type} {selectedRun.period_number}/{selectedRun.period_year} -- {selectedRun.status}
              </h3>
              {selectedRun.status === "DRAFT" && (
                <div className="flex items-end gap-2">
                  <select value={selectedEmployeeId} onChange={(e) => setSelectedEmployeeId(e.target.value ? Number(e.target.value) : "")} className="input-v2 px-2 py-1.5 text-xs">
                    <option value="">Employee</option>
                    {employees.map((emp) => (
                      <option key={emp.id} value={emp.id}>
                        {emp.full_name}
                      </option>
                    ))}
                  </select>
                  <input value={bonus} onChange={(e) => setBonus(e.target.value)} placeholder="Bonus" className="input-v2 px-2 py-1.5 text-xs w-20" />
                  <label className="flex items-center gap-1 text-xs">
                    <input type="checkbox" checked={payHolidayAllowance} onChange={(e) => setPayHolidayAllowance(e.target.checked)} /> Holiday allowance
                  </label>
                  <button onClick={addPayslip} className="btn-secondary-v2 px-3 py-1.5 text-xs">
                    Add payslip
                  </button>
                </div>
              )}
              {payslips.map((p) => (
                <div key={p.id} className="border border-border-subtle rounded-md p-2 flex items-center justify-between">
                  <span>
                    #{p.id} {p.voided && <span className="text-error">(voided)</span>}
                    {p.corrects_payslip_id && <span className="text-text-secondary"> correction of #{p.corrects_payslip_id}</span>}
                  </span>
                  <span className="font-mono">{p.gross_salary} → {p.net_salary}</span>
                  <div className="flex items-center gap-2">
                    <a href={api.payslipPdfUrl(p.id)} target="_blank" rel="noreferrer" className="text-xs underline">
                      PDF
                    </a>
                    {!p.voided && (
                      <button onClick={() => correct(p)} className="text-xs underline">
                        Correct
                      </button>
                    )}
                  </div>
                </div>
              ))}
              {selectedRun.status === "DRAFT" && (
                <button onClick={approve} className="btn-primary-v2 px-3 py-1.5 text-xs">
                  Approve run
                </button>
              )}
              {selectedRun.status === "APPROVED" && (
                <button onClick={markPaid} className="btn-primary-v2 px-3 py-1.5 text-xs">
                  Mark paid
                </button>
              )}
            </div>
          ) : (
            <p className="text-sm text-text-secondary">Select a payroll run.</p>
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
