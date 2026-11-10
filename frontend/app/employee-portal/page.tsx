"use client";

import { FormEvent, useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import GlassPageHeader from "@/components/glass/GlassPageHeader";
import GlassCard from "@/components/glass/GlassCard";
import GlassPanel from "@/components/glass/GlassPanel";
import GlassButton from "@/components/glass/GlassButton";
import { GlassInput, GlassSelect } from "@/components/glass/GlassInput";
import GlassTabs from "@/components/glass/GlassTabs";
import GlassEmptyState from "@/components/glass/GlassEmptyState";
import GlassLoadingState, { GlassErrorState } from "@/components/glass/GlassLoadingState";
import { IconDocuments, IconClock } from "@/components/glass/icons";
import { useAuth } from "@/lib/auth-context";
import { api, JsonReport } from "@/lib/api";
import { formatEUR } from "@/lib/format";

type Tab = "profile" | "payslips" | "statement" | "hours";

function ProfileTab() {
  const t = useTranslations("employeePortal");
  const { token } = useAuth();
  const [profile, setProfile] = useState<JsonReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (token) api.myProfile(token).then(setProfile).catch((e) => setError(e.message));
  }, [token]);

  if (error) return <GlassErrorState message={error} />;
  if (!profile) return <GlassLoadingState rows={3} />;

  return (
    <GlassCard padding="lg" className="max-w-md">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-12 h-12 rounded-full bg-gradient-to-br from-brand-purple-500 to-accent-indigo-600 text-white flex items-center justify-center font-semibold text-lg">
          {String(profile.full_name).slice(0, 1)}
        </div>
        <div>
          <p className="font-semibold text-text-primary">{String(profile.full_name)}</p>
          <p className="text-xs text-text-secondary">{String(profile.employee_number)}</p>
        </div>
      </div>
      <dl className="space-y-2 text-sm">
        <Row label={t("jobTitle")} value={profile.job_title ? String(profile.job_title) : "—"} />
        <Row label={t("department")} value={profile.department ? String(profile.department) : "—"} />
        <Row label={t("contractedHoursPerWeek")} value={profile.contracted_hours_per_week ? String(profile.contracted_hours_per_week) : "—"} />
        <Row label={t("employmentStart")} value={String(profile.employment_start_date)} />
        <Row label={t("employmentEnd")} value={profile.employment_end_date ? String(profile.employment_end_date) : t("active")} />
      </dl>
    </GlassCard>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between border-b border-border pb-2 last:border-0">
      <dt className="text-text-secondary">{label}</dt>
      <dd className="text-text-primary font-medium">{value}</dd>
    </div>
  );
}

function PayslipsTab() {
  const t = useTranslations("employeePortal");
  const locale = useLocale();
  const { token } = useAuth();
  const [payslips, setPayslips] = useState<JsonReport[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (token) api.myPayslips(token).then(setPayslips).catch((e) => setError(e.message));
  }, [token]);

  if (error) return <GlassErrorState message={error} />;
  if (!payslips) return <GlassLoadingState rows={3} />;
  if (payslips.length === 0) return <GlassEmptyState title={t("noPayslipsYet")} icon={<IconDocuments size={28} />} />;

  return (
    <GlassPanel title={t("myPayslips")}>
      <div className="overflow-x-auto" tabIndex={0}>
      <table className="table-v3">
        <thead>
          <tr>
            <th>{t("payslip")}</th>
            <th className="text-right">{t("gross")}</th>
            <th className="text-right">{t("net")}</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {payslips.map((p) => (
            <tr key={String(p.id)}>
              <td className="text-text-primary">
                #{String(p.id)} {p.voided ? <span className="value-negative">({t("voided")})</span> : null}
              </td>
              <td className="col-amount">{formatEUR(String(p.gross_salary), locale)}</td>
              <td className="col-amount font-medium">{formatEUR(String(p.net_salary), locale)}</td>
              <td>
                <a href={api.myPayslipPdfUrl(Number(p.id))} target="_blank" rel="noreferrer" className="text-navy hover:underline text-xs">
                  PDF
                </a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </GlassPanel>
  );
}

function StatementTab() {
  const t = useTranslations("employeePortal");
  const tCommon = useTranslations("common");
  const locale = useLocale();
  const { token } = useAuth();
  const [taxYear, setTaxYear] = useState(new Date().getFullYear());
  const [statement, setStatement] = useState<JsonReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function load() {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      setStatement(await api.myAnnualStatement(token, taxYear));
    } catch (e) {
      setError(e instanceof Error ? e.message : t("couldNotLoadStatement"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <GlassCard padding="lg" className="max-w-lg space-y-4">
      <div className="flex flex-wrap items-end gap-2">
        <GlassInput aria-label={t("taxYear")} type="number" value={taxYear} onChange={(e) => setTaxYear(Number(e.target.value))} className="w-24" />
        <GlassButton onClick={load} disabled={loading} size="sm">
          {loading ? tCommon("loading") : t("viewMyAnnualStatement")}
        </GlassButton>
        {statement && (
          <a href={api.myAnnualStatementPdfUrl(taxYear)} target="_blank" rel="noreferrer" className="btn-secondary-v2 px-3 py-1.5 text-xs">
            PDF
          </a>
        )}
      </div>
      {error && <GlassErrorState message={error} />}
      {statement && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
          <Row label={t("payslipsIncluded")} value={String(statement.number_of_payslips)} />
          <Row label={t("grossSalary")} value={formatEUR(statement.gross_salary, locale)} />
          <Row label={t("netSalaryPaid")} value={formatEUR(statement.net_salary, locale)} />
          <Row label={t("wageTaxWithheld")} value={formatEUR(statement.wage_tax_and_national_insurance, locale)} />
        </div>
      )}
    </GlassCard>
  );
}

function HoursTab() {
  const t = useTranslations("employeePortal");
  const { token } = useAuth();
  const [entries, setEntries] = useState<JsonReport[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [entryDate, setEntryDate] = useState(new Date().toISOString().slice(0, 10));
  const [entryType, setEntryType] = useState("WORKED");
  const [hours, setHours] = useState("8.00");
  const [employeeId, setEmployeeId] = useState<number | null>(null);

  function refresh() {
    if (!token) return;
    api.myTimesheetEntries(token).then(setEntries).catch((e) => setError(e.message));
    api.myProfile(token).then((p) => setEmployeeId(Number(p.id))).catch(() => {});
  }
  useEffect(refresh, [token]);

  async function submitEntry(e: FormEvent) {
    e.preventDefault();
    if (!token || !employeeId) return;
    try {
      await api.createMyTimesheetEntry(token, { employee_id: employeeId, entry_date: entryDate, entry_type: entryType, hours });
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("couldNotSubmitEntry"));
    }
  }

  async function submitForApproval(id: number) {
    if (!token) return;
    await api.submitMyTimesheetEntry(token, id);
    refresh();
  }

  return (
    <div className="space-y-4">
      {error && <GlassErrorState message={error} />}
      <GlassCard>
        <form onSubmit={submitEntry} className="flex flex-wrap items-end gap-2">
          <GlassInput aria-label={t("entryDate")} type="date" value={entryDate} onChange={(e) => setEntryDate(e.target.value)} />
          <GlassSelect aria-label={t("entryType")} value={entryType} onChange={(e) => setEntryType(e.target.value)}>
            <option value="WORKED">{t("entryTypeWorked")}</option>
            <option value="HOLIDAY">{t("entryTypeHoliday")}</option>
            <option value="SICK">{t("entryTypeSick")}</option>
            <option value="ABSENCE">{t("entryTypeAbsence")}</option>
          </GlassSelect>
          <GlassInput aria-label={t("hours")} type="number" step="0.25" value={hours} onChange={(e) => setHours(e.target.value)} className="w-24" />
          <GlassButton type="submit" size="sm">
            {t("logEntry")}
          </GlassButton>
        </form>
      </GlassCard>

      {entries === null ? (
        <GlassLoadingState rows={2} />
      ) : entries.length === 0 ? (
        <GlassEmptyState title={t("noHoursLoggedYet")} icon={<IconClock size={28} />} />
      ) : (
        <GlassPanel title={t("myHours")}>
          <ul className="divide-y divide-white/30">
            {entries.map((entry) => (
              <li key={String(entry.id)} className="flex items-center justify-between px-5 py-3 text-sm">
                <span>
                  {String(entry.entry_date)} · {String(entry.entry_type)} · {t("hoursSuffix", { hours: String(entry.hours) })}
                </span>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-text-secondary">{String(entry.status)}</span>
                  {entry.status === "DRAFT" && (
                    <GlassButton size="sm" variant="secondary" onClick={() => submitForApproval(Number(entry.id))}>
                      {t("submit")}
                    </GlassButton>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </GlassPanel>
      )}
    </div>
  );
}

function EmployeePortalContent() {
  const t = useTranslations("employeePortal");
  const [tab, setTab] = useState<Tab>("profile");

  return (
    <div className="space-y-5">
      <GlassPageHeader title={t("myWorkspace")} subtitle={t("myWorkspaceSubtitle")} />
      <GlassTabs
        tabs={[
          { value: "profile", label: t("profile") },
          { value: "payslips", label: t("payslips") },
          { value: "statement", label: t("annualStatement") },
          { value: "hours", label: t("myHours") },
        ]}
        value={tab}
        onChange={setTab}
      />
      {tab === "profile" && <ProfileTab />}
      {tab === "payslips" && <PayslipsTab />}
      {tab === "statement" && <StatementTab />}
      {tab === "hours" && <HoursTab />}
    </div>
  );
}

export default function EmployeePortalPage() {
  return (
    <AuthGuard>
      <Shell>
        <EmployeePortalContent />
      </Shell>
    </AuthGuard>
  );
}
