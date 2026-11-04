"use client";

import { useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import GlassPageHeader from "@/components/glass/GlassPageHeader";
import GlassCard from "@/components/glass/GlassCard";
import GlassButton from "@/components/glass/GlassButton";
import { GlassSelect, GlassInput } from "@/components/glass/GlassInput";
import GlassEmptyState from "@/components/glass/GlassEmptyState";
import { GlassErrorState } from "@/components/glass/GlassLoadingState";
import { IconDocuments } from "@/components/glass/icons";
import { useAuth } from "@/lib/auth-context";
import { api, Company, JsonReport } from "@/lib/api";
import { formatEUR } from "@/lib/format";

function AnnualStatementsContent() {
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [employees, setEmployees] = useState<JsonReport[]>([]);
  const [employeeId, setEmployeeId] = useState<number | "">("");
  const [taxYear, setTaxYear] = useState(new Date().getFullYear());
  const [statement, setStatement] = useState<JsonReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  useEffect(() => {
    if (!token || !companyId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setEmployees([]);
      return;
    }
    api.listEmployees(token, Number(companyId)).then(setEmployees).catch((e) => setError(e.message));
  }, [token, companyId]);

  async function fetchStatement() {
    if (!token || !employeeId) return;
    setLoading(true);
    setError(null);
    setStatement(null);
    try {
      setStatement(await api.getAnnualStatement(token, Number(employeeId), taxYear));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load annual statement");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-5">
      <GlassPageHeader
        title="Annual Statements (Jaaropgaaf)"
        subtitle="A sum of each employee's already-calculated payslip figures for the tax year -- never a fresh tax calculation."
      />

      {error && <GlassErrorState message={error} />}

      <GlassCard className="flex flex-wrap items-end gap-3">
        <div>
          <label htmlFor="as-company" className="text-label-v2 block mb-1">Company</label>
          <GlassSelect id="as-company" value={companyId} onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")}>
            <option value="">Select a company</option>
            {companies.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </GlassSelect>
        </div>
        <div>
          <label htmlFor="as-employee" className="text-label-v2 block mb-1">Employee</label>
          <GlassSelect id="as-employee" value={employeeId} onChange={(e) => setEmployeeId(e.target.value ? Number(e.target.value) : "")} disabled={!companyId}>
            <option value="">Select an employee</option>
            {employees.map((emp) => (
              <option key={emp.id} value={emp.id}>
                {emp.full_name}
              </option>
            ))}
          </GlassSelect>
        </div>
        <div>
          <label htmlFor="as-tax-year" className="text-label-v2 block mb-1">Tax year</label>
          <GlassInput id="as-tax-year" type="number" value={taxYear} onChange={(e) => setTaxYear(Number(e.target.value))} className="w-24" />
        </div>
        <GlassButton onClick={fetchStatement} disabled={!employeeId || loading}>
          {loading ? "Loading…" : "View statement"}
        </GlassButton>
      </GlassCard>

      {statement && (
        <GlassCard padding="lg">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-text-primary">Tax year {statement.tax_year}</h2>
            <a
              href={employeeId ? api.annualStatementPdfUrl(Number(employeeId), taxYear) : "#"}
              target="_blank"
              rel="noreferrer"
              className="btn-secondary-v2 px-3 py-1.5 text-xs"
            >
              Download PDF
            </a>
          </div>
          {Number(statement.number_of_payslips) === 0 ? (
            <GlassEmptyState title="No payslips for this tax year" icon={<IconDocuments size={28} />} />
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-sm">
              <StatRow label="Payslips included" value={String(statement.number_of_payslips)} />
              <StatRow label="Gross salary" value={formatEUR(statement.gross_salary)} />
              <StatRow label="Taxable wage" value={formatEUR(statement.taxable_wage)} />
              <StatRow label="Wage tax + NI withheld" value={formatEUR(statement.wage_tax_and_national_insurance)} />
              <StatRow label="General tax credit" value={formatEUR(statement.general_tax_credit_applied)} />
              <StatRow label="Labor tax credit" value={formatEUR(statement.labor_tax_credit_applied)} />
              <StatRow label="Pension deduction" value={formatEUR(statement.pension_deduction)} />
              <StatRow label="Net salary paid" value={formatEUR(statement.net_salary)} strong />
              <StatRow label="Employer Zvw levy" value={formatEUR(statement.employer_levy_zvw)} />
            </div>
          )}
          <p className="text-xs text-text-secondary mt-4">{String(statement.note)}</p>
        </GlassCard>
      )}
    </div>
  );
}

function StatRow({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className="rounded-lg bg-muted px-3 py-2">
      <p className="text-xs text-text-secondary">{label}</p>
      <p className={`font-mono ${strong ? "text-base font-semibold text-text-primary" : "text-sm text-text-primary"}`}>{value}</p>
    </div>
  );
}

export default function AnnualStatementsPage() {
  return (
    <AuthGuard>
      <Shell>
        <AnnualStatementsContent />
      </Shell>
    </AuthGuard>
  );
}
