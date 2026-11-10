"use client";

import { FormEvent, useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import { useAuth } from "@/lib/auth-context";
import { api, Company, JsonReport } from "@/lib/api";
import { formatEUR } from "@/lib/format";

const LEGAL_FORMS = ["EENMANSZAAK", "VOF", "MAATSCHAP", "CV", "BV", "NV", "COOPERATIE", "OWM", "STICHTING", "VERENIGING", "VVE", "REDERIJ", "OTHER"];

function TaxCentreContent() {
  const t = useTranslations("taxCentre");
  const tCommon = useTranslations("common");
  const locale = useLocale();
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [overview, setOverview] = useState<JsonReport | null>(null);
  const [legalForm, setLegalForm] = useState("EENMANSZAAK");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const [annualProfit, setAnnualProfit] = useState("50000");
  const [hoursCriterionMet, setHoursCriterionMet] = useState(true);
  const [incomeEstimate, setIncomeEstimate] = useState<JsonReport | null>(null);

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  function refresh() {
    if (!token || !companyId) return;
    api.taxCentreOverview(token, Number(companyId)).then(setOverview).catch((e) => setError(e.message));
  }

  useEffect(refresh, [token, companyId]);

  async function setForm(e: FormEvent) {
    e.preventDefault();
    if (!token || !companyId) return;
    try {
      await api.setCompanyLegalForm(token, { company_id: Number(companyId), legal_form_code: legalForm, effective_from: new Date().toISOString().slice(0, 10) });
      setMessage(t("legalFormSetMessage", { form: legalForm }));
      refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function estimateIncomeTax() {
    if (!token || !companyId) return;
    try {
      setIncomeEstimate(await api.incomeTaxEstimate(token, Number(companyId), annualProfit, hoursCriterionMet, false));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-text-primary">{t("title")}</h1>
      <p className="text-sm text-text-secondary">
        {t("pageExplainer")}
      </p>
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

      {overview && (
        <>
          {overview.legal_form_warning && <div className="rounded-md bg-amber-50 text-amber-700 text-sm px-3 py-2">{overview.legal_form_warning}</div>}

          {!overview.current_legal_form && (
            <form onSubmit={setForm} className="card-v2 p-4 flex items-end gap-3">
              <select aria-label={t("legalForm")} value={legalForm} onChange={(e) => setLegalForm(e.target.value)} className="input-v2 px-3 py-2 text-sm">
                {LEGAL_FORMS.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </select>
              <button type="submit" className="btn-primary-v2 px-4 py-2 text-sm">
                {t("setLegalForm")}
              </button>
            </form>
          )}

          {overview.current_legal_form && (
            <div className="card-v2 p-4">
              <p className="text-sm text-text-secondary">{t("currentLegalForm")}</p>
              <p className="text-xl font-semibold text-text-primary">{overview.current_legal_form}</p>
            </div>
          )}

          <div className="grid grid-cols-2 gap-4">
            <div className="card-v2 p-4">
              <h2 className="font-medium text-text-primary mb-2">{t("btwVat")}</h2>
              {overview.btw.length === 0 && <p className="text-sm text-text-secondary">{t("noVatReturnsYet")}</p>}
              {overview.btw.map((row: JsonReport) => (
                <div key={row.period_label} className="flex items-center justify-between text-sm py-1 border-b border-border-subtle last:border-0">
                  <span>{row.period_label}</span>
                  <span className="pill-v2 bg-surface-page px-2 py-0.5 text-xs">{row.status}</span>
                  <span className="font-mono">{formatEUR(row.net_payable, locale)}</span>
                </div>
              ))}
            </div>
            <div className="card-v2 p-4 space-y-2">
              <h2 className="font-medium text-text-primary mb-2">{t("otherDeclarations")}</h2>
              <p className="text-sm">{t("icpLabel")} <span className="text-text-secondary">{overview.icp.note}</span></p>
              <p className="text-sm">{t("ossLabel")} <span className="text-text-secondary">{overview.oss.note}</span></p>
              <p className="text-sm">{t("incomeTaxLabel")} <span className="text-text-secondary">{overview.income_tax.note}</span></p>
              <p className="text-sm">{t("corporateTaxLabel")} <span className="text-text-secondary">{overview.corporate_income_tax.note}</span></p>
              <p className="text-xs text-pending pt-2">{overview.sbr_digipoort_integration_status}</p>
            </div>
          </div>

          {overview.current_legal_form && ["EENMANSZAAK", "VOF", "MAATSCHAP", "CV"].includes(overview.current_legal_form) && (
            <div className="card-v2 p-4 space-y-3">
              <h2 className="font-medium text-text-primary">{t("incomeTaxEstimate")}</h2>
              <div className="flex items-end gap-3">
                <input aria-label={t("annualProfit")} value={annualProfit} onChange={(e) => setAnnualProfit(e.target.value)} placeholder={t("annualProfit")} className="input-v2 px-3 py-2 text-sm w-40" />
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={hoursCriterionMet} onChange={(e) => setHoursCriterionMet(e.target.checked)} /> {t("hoursCriterionMet")}
                </label>
                <button onClick={estimateIncomeTax} className="btn-secondary-v2 px-3 py-1.5 text-sm">
                  {t("estimate")}
                </button>
              </div>
              {incomeEstimate && (
                <pre className="text-xs bg-surface-page rounded-md p-3 overflow-x-auto" dir="ltr">{JSON.stringify(incomeEstimate, null, 2)}</pre>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default function TaxCentrePage() {
  return (
    <AuthGuard>
      <Shell>
        <TaxCentreContent />
      </Shell>
    </AuthGuard>
  );
}
