"use client";

import { ReactNode } from "react";

interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  className?: string;
}

interface GlassTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string | number;
  onRowClick?: (row: T) => void;
  emptyMessage?: string;
}

/** Table that degrades to a stacked card list under `sm` -- avoids
 * horizontal overflow on mobile instead of forcing a scroll container. */
export default function GlassTable<T>({ columns, rows, rowKey, onRowClick, emptyMessage = "No data yet." }: GlassTableProps<T>) {
  if (rows.length === 0) {
    return <p className="px-5 py-8 text-sm text-text-secondary text-center">{emptyMessage}</p>;
  }

  return (
    <>
      <table className="w-full text-sm hidden sm:table">
        <thead>
          <tr className="text-left text-text-secondary border-b border-border">
            {columns.map((c) => (
              <th key={c.key} className={`px-5 py-2.5 font-medium whitespace-nowrap ${c.className ?? ""}`}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={rowKey(row)}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              onKeyDown={onRowClick ? (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onRowClick(row); } } : undefined}
              tabIndex={onRowClick ? 0 : undefined}
              role={onRowClick ? "button" : undefined}
              className={`border-b border-border last:border-0 ${onRowClick ? "cursor-pointer hover:bg-muted" : ""}`}
            >
              {columns.map((c) => (
                <td key={c.key} className={`px-5 py-3 ${c.className ?? ""}`}>
                  {c.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>

      {/* Mobile: stacked cards, one per row, label/value pairs */}
      <div className="sm:hidden divide-y divide-white/30">
        {rows.map((row) => (
          <div
            key={rowKey(row)}
            onClick={onRowClick ? () => onRowClick(row) : undefined}
            onKeyDown={onRowClick ? (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onRowClick(row); } } : undefined}
            tabIndex={onRowClick ? 0 : undefined}
            role={onRowClick ? "button" : undefined}
            className={`px-4 py-3 space-y-1 ${onRowClick ? "cursor-pointer active:bg-muted" : ""}`}
          >
            {columns.map((c) => (
              <div key={c.key} className="flex items-center justify-between gap-3 text-xs">
                <span className="text-text-secondary">{c.header}</span>
                <span className="text-text-primary text-right">{c.render(row)}</span>
              </div>
            ))}
          </div>
        ))}
      </div>
    </>
  );
}
