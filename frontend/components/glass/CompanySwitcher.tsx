"use client";

import { useState } from "react";
import { useCompany } from "@/lib/company-context";
import { IconChevronDown } from "./icons";

export default function CompanySwitcher() {
  const { companies, selectedCompany, selectedCompanyId, setSelectedCompanyId, loading } = useCompany();
  const [open, setOpen] = useState(false);

  if (loading) return null;
  if (companies.length === 0) {
    return <span className="text-xs text-text-secondary hidden sm:inline">No companies yet</span>;
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-label="Switch active company"
        className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm text-text-primary hover:bg-muted transition-colors max-w-[10rem] sm:max-w-[14rem]"
      >
        <span className="truncate font-medium">{selectedCompany?.name ?? "Select a company"}</span>
        <IconChevronDown size={14} className="text-text-secondary flex-shrink-0" />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <ul
            role="listbox"
            aria-label="Companies"
            className="absolute start-0 mt-1 w-64 max-h-80 overflow-y-auto glass-panel p-1.5 z-50"
          >
            {companies.map((c) => (
              <li key={c.id}>
                <button
                  role="option"
                  aria-selected={c.id === selectedCompanyId}
                  onClick={() => {
                    setSelectedCompanyId(c.id);
                    setOpen(false);
                  }}
                  className={`w-full text-start px-3 py-2 rounded-md text-sm hover:bg-muted transition-colors ${
                    c.id === selectedCompanyId ? "bg-brand-purple-500/10 text-brand-purple-700 font-medium" : "text-text-primary"
                  }`}
                >
                  {c.name}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
