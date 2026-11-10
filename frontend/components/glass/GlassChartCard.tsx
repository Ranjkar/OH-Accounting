"use client";

import { useId, useState } from "react";
import { useLocale, useTranslations } from "next-intl";

export interface ChartPoint {
  label: string;
  value: number;
}

interface GlassChartCardProps {
  title: string;
  subtitle?: string;
  points: ChartPoint[];
  formatValue?: (v: number) => string;
  actions?: React.ReactNode;
  height?: number;
  kind?: "line" | "bar";
}

/** Dependency-free SVG line/bar chart with a hover tooltip. Deliberately
 * not pulling in a charting library (recharts/chart.js etc.) -- this is a
 * handful of data points per company per period, not a case that needs
 * one, and every extra KB here is one the brief asked us to avoid.
 *
 * Accessibility: the SVG itself is decorative to a screen reader (an SVG
 * line chart has no useful semantics to expose point-by-point) -- the
 * actual data is also rendered as a visually-hidden table immediately
 * after it, which is what a screen reader user gets instead. Each data
 * point is also a real, keyboard-focusable element (not just a mouse
 * hover target), so the same tooltip a mouse user sees is reachable by
 * tabbing/arrow-keying through the chart. */
export default function GlassChartCard({ title, subtitle, points, formatValue, actions, height = 220, kind = "line" }: GlassChartCardProps) {
  const t = useTranslations("charts");
  const locale = useLocale();
  const gradientId = useId();
  const tableId = useId();
  const [hover, setHover] = useState<number | null>(null);
  const fmt = formatValue ?? ((v: number) => v.toLocaleString(locale, { maximumFractionDigits: 0 }));

  if (points.length === 0) {
    return (
      <div className="glass-panel p-5">
        <h3 className="text-card-heading">{title}</h3>
        <p className="text-secondary-v2 mt-8 text-center">{t("noDataForPeriod")}</p>
      </div>
    );
  }

  const width = 600;
  const padding = 28;
  const values = points.map((p) => p.value);
  const max = Math.max(...values, 0);
  const min = Math.min(...values, 0);
  const span = max - min || 1;
  const stepX = (width - padding * 2) / Math.max(points.length - 1, 1);

  const coords = points.map((p, i) => ({
    x: padding + i * stepX,
    y: padding + (height - padding * 2) * (1 - (p.value - min) / span),
    ...p,
  }));

  const linePath = coords.map((c, i) => `${i === 0 ? "M" : "L"} ${c.x} ${c.y}`).join(" ");
  const areaPath = `${linePath} L ${coords[coords.length - 1].x} ${height - padding} L ${coords[0].x} ${height - padding} Z`;
  const zeroY = padding + (height - padding * 2) * (1 - (0 - min) / span);

  function onPointKeyDown(e: React.KeyboardEvent, i: number) {
    if (e.key === "ArrowRight") {
      e.preventDefault();
      setHover(Math.min(i + 1, points.length - 1));
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      setHover(Math.max(i - 1, 0));
    } else if (e.key === "Home") {
      e.preventDefault();
      setHover(0);
    } else if (e.key === "End") {
      e.preventDefault();
      setHover(points.length - 1);
    }
  }

  return (
    <div className="glass-panel p-5">
      <div className="flex flex-wrap items-start justify-between gap-2 mb-2">
        <div className="min-w-0">
          <h3 className="text-card-heading">{title}</h3>
          {subtitle && <p className="text-helper-v2 mt-0.5">{subtitle}</p>}
        </div>
        {actions}
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full"
        style={{ height }}
        role="group"
        aria-label={t("chartAriaLabel", { title })}
        aria-describedby={tableId}
        onMouseLeave={() => setHover(null)}
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--navy)" stopOpacity={0.18} />
            <stop offset="100%" stopColor="var(--navy)" stopOpacity={0} />
          </linearGradient>
        </defs>

        <line x1={padding} y1={zeroY} x2={width - padding} y2={zeroY} stroke="var(--border-subtle)" strokeWidth={1} />

        {kind === "bar"
          ? coords.map((c, i) => {
              const barWidth = Math.min(stepX * 0.5, 28);
              const barY = c.value >= 0 ? c.y : zeroY;
              const barHeight = Math.abs(zeroY - c.y);
              return (
                <rect
                  key={i}
                  x={c.x - barWidth / 2}
                  y={barY}
                  width={barWidth}
                  height={Math.max(barHeight, 1)}
                  rx={3}
                  fill={c.value >= 0 ? "var(--navy)" : "var(--semantic-error)"}
                  opacity={hover === null || hover === i ? 1 : 0.45}
                  onMouseEnter={() => setHover(i)}
                  aria-hidden="true"
                />
              );
            })
          : (
            <>
              <path d={areaPath} fill={`url(#${gradientId})`} stroke="none" aria-hidden="true" />
              <path d={linePath} fill="none" stroke="var(--navy)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" />
              {coords.map((c, i) => (
                <circle
                  key={i}
                  cx={c.x}
                  cy={c.y}
                  r={hover === i ? 5 : 3}
                  fill="var(--navy)"
                  stroke="var(--surface-card)"
                  strokeWidth={1.5}
                  onMouseEnter={() => setHover(i)}
                  style={{ transition: "r 100ms ease" }}
                  aria-hidden="true"
                />
              ))}
            </>
          )}

        {/* Real, keyboard-focusable hit targets -- one per data point, tab
            order left-to-right, arrow keys move between points, matching
            the visible mouse-hover tooltip behaviour. */}
        {coords.map((c, i) => (
          <rect
            key={`hit-${i}`}
            x={c.x - stepX / 2}
            y={0}
            width={stepX}
            height={height}
            fill="transparent"
            tabIndex={0}
            role="button"
            aria-label={`${c.label}: ${fmt(c.value)}`}
            onMouseEnter={() => setHover(i)}
            onTouchStart={() => setHover(i)}
            onFocus={() => setHover(i)}
            onKeyDown={(e) => onPointKeyDown(e, i)}
          />
        ))}

        {hover !== null && (
          <g aria-hidden="true">
            <line x1={coords[hover].x} y1={padding} x2={coords[hover].x} y2={height - padding} stroke="var(--border-strong)" strokeWidth={1} />
          </g>
        )}
      </svg>

      <div className="flex justify-between gap-1 text-helper-v2 mt-1 px-1 overflow-hidden" aria-hidden="true">
        {points.map((p, i) => (
          <span key={i} className={`min-w-0 truncate ${i === hover ? "text-brand-purple-600 font-medium" : ""}`}>
            {p.label}
          </span>
        ))}
      </div>

      {hover !== null && (
        <div className="mt-2 inline-flex items-center gap-2 glass-panel px-3 py-1.5 text-sm" role="status" aria-live="polite">
          <span className="text-secondary-v2">{points[hover].label}</span>
          <span className="financial-value-sm">{fmt(points[hover].value)}</span>
        </div>
      )}

      {/* Screen-reader-only data table: the actual accessible representation
          of this chart's values, per "Provide textual summaries of important
          values" -- never relies on the SVG being interpretable. */}
      <table id={tableId} className="sr-only">
        <caption>{t("tableCaption", { title })}</caption>
        <thead>
          <tr>
            <th scope="col">{t("colPeriod")}</th>
            <th scope="col">{t("colValue")}</th>
          </tr>
        </thead>
        <tbody>
          {points.map((p, i) => (
            <tr key={i}>
              <td>{p.label}</td>
              <td>{fmt(p.value)}{p.value < 0 ? t("negativeSuffix") : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
