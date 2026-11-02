"use client";

import Link from "next/link";
import { ReactNode } from "react";
import { useAuth } from "@/lib/auth-context";

export default function Shell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();

  return (
    <div className="flex-1 flex flex-col">
      <header className="bg-navy text-white px-6 py-4 flex items-center justify-between">
        <Link href="/" className="font-semibold tracking-tight text-lg">
          OnHolland <span className="text-slate-300 font-normal">Accounting</span>
        </Link>
        <div className="flex items-center gap-4 text-sm">
          {user && (
            <span className="text-slate-300">
              {user.full_name} <span className="text-slate-500">· {user.role}</span>
            </span>
          )}
          <button
            onClick={logout}
            className="rounded-md border border-slate-600 px-3 py-1.5 hover:bg-navy-light transition-colors"
          >
            Log out
          </button>
        </div>
      </header>
      <main className="flex-1 bg-slate-50 p-6">{children}</main>
    </div>
  );
}
