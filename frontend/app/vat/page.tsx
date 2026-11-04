"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import GlassPageHeader from "@/components/glass/GlassPageHeader";
import GlassPanel from "@/components/glass/GlassPanel";
import GlassButton from "@/components/glass/GlassButton";
import { GlassSelect } from "@/components/glass/GlassInput";
import { GlassErrorState } from "@/components/glass/GlassLoadingState";
import { useAuth } from "@/lib/auth-context";
import { api, Company, FinancialYear, VatReturn } from "@/lib/api";
import { formatEUR } from "@/lib/format";

function LockControl({ companyId, fy, onChange }: { companyId: number; fy: FinancialYear; onChange: (fy: FinancialYear) => void }) {
  const { token } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      const updated = fy.is_locked ? await api.unlockFinancialYear(token, companyId, fy.id) : await api.lockFinancialYear(token, companyId, fy.id);
      onChange(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center gap-2">
      {error && <span className="text-xs value-negative">{error}</span>}
      <span className={`text-xs font-medium rounded-full px-2.5 py-1 ${fy.is_locked ? "bg-amber-100 text-amber-700" : "bg-green-100 text-green-700"}`}>
        {fy.is_locked ? "Locked" : "Open"}
      </span>
      <GlassButton size="sm" variant="secondary" onClick={toggle} disabled={busy}>
        {busy ? "…" : fy.is_locked ? "Unlock" : "Lock"}
      </GlassButton>
    </div>
  );
}

function VatContent() {
  const { token } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [financialYears, setFinancialYears] = useState<FinancialYear[]>([]);
  const [returns, setReturns] = useState<Record<number, VatReturn>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (token) api.listCompanies(token).then(setCompanies).catch((e) => setError(e.message));
  }, [token]);

  useEffect(() => {
    const load = token && companyId ? api.listFinancialYears(token, Number(companyId)) : Promise.resolve([]);
    load.then(setFinancialYears).catch((e) => setError(e.message));
  }, [token, companyId]);

  useEffect(() => {
    if (!token || !companyId) return;
    financialYears.forEach((fy) => {
      fy.vat_periods.forEach((p) => {
        api
          .getOrComputeVatReturn(token, Number(companyId), p.id)
          .then((vr) => setReturns((prev) => ({ ...prev, [p.id]: vr })))
          .catch(() => {});
      });
    });
  }, [token, companyId, financialYears]);

  return (
    <div className="space-y-5">
      <GlassPageHeader title="VAT Overview" subtitle="Per financial year, per period -- locking a financial year blocks new or corrected ledger postings dated within it." />

      {error && <GlassErrorState message={error} />}

      <GlassSelect aria-label="Company" value={companyId} onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")}>
        <option value="">Select a company</option>
        {companies.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </GlassSelect>

      {financialYears.map((fy) => (
        <GlassPanel
          key={fy.id}
          title={`Financial year ${fy.year}`}
          actions={<LockControl companyId={Number(companyId)} fy={fy} onChange={(updated) => setFinancialYears((prev) => prev.map((f) => (f.id === updated.id ? updated : f)))} />}
        >
          <div className="overflow-x-auto">
          <table className="table-v3">
            <thead>
              <tr>
                <th>Period</th>
                <th>Filing deadline</th>
                <th className="text-right">VAT due (5a)</th>
                <th className="text-right">Deductible (5b)</th>
                <th className="text-right">Net payable</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {fy.vat_periods.map((p) => {
                const vr = returns[p.id];
                return (
                  <tr key={p.id} className="hover:bg-muted">
                    <td>
                      {vr ? (
                        <Link href={`/vat/${vr.id}`} className="text-navy hover:underline">
                          {p.label}
                        </Link>
                      ) : (
                        <span className="text-text-primary">{p.label}</span>
                      )}
                    </td>
                    <td className="text-text-secondary">{p.filing_deadline}</td>
                    <td className="col-amount">{vr ? formatEUR(vr.box_5a_vat) : "—"}</td>
                    <td className="col-amount">{vr ? formatEUR(vr.box_5b_vat) : "—"}</td>
                    <td className="col-amount font-medium">{vr ? formatEUR(vr.net_payable) : "—"}</td>
                    <td className="text-xs uppercase text-text-secondary">{vr?.status.replaceAll("_", " ") ?? "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          </div>
        </GlassPanel>
      ))}
    </div>
  );
}

export default function VatPage() {
  return (
    <AuthGuard>
      <Shell>
        <VatContent />
      </Shell>
    </AuthGuard>
  );
}
