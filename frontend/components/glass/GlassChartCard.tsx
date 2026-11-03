"use client";

import { useId, useState } from "react";

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
 * one, and every extra KB here is one the brief asked us to avoid. */
export default function GlassChartCard({ title, subtitle, points, formatValue, actions, height = 220, kind = "line" }: GlassChartCardProps) {
  const gradientId = useId();
  const [hover, setHover] = useState<number | null>(null);
  const fmt = formatValue ?? ((v: number) => v.toLocaleString("nl-NL", { maximumFractionDigits: 0 }));

  if (points.length === 0) {
    return (
      <div className="glass-panel p-5">
        <h3 className="font-semibold text-text-primary">{title}</h3>
        <p className="text-sm text-text-secondary mt-8 text-center">No data yet for this period.</p>
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

  return (
    <div className="glass-panel p-5">
      <div className="flex items-start justify-between mb-2">
        <div>
          <h3 className="font-semibold text-text-primary">{title}</h3>
          {subtitle && <p className="text-xs text-text-secondary mt-0.5">{subtitle}</p>}
        </div>
        {actions}
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full"
        style={{ height }}
        role="img"
        aria-label={title}
        onMouseLeave={() => setHover(null)}
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#7c3aed" stopOpacity={0.35} />
            <stop offset="100%" stopColor="#7c3aed" stopOpacity={0} />
          </linearGradient>
        </defs>

        <line x1={padding} y1={zeroY} x2={width - padding} y2={zeroY} stroke="#e9e7f0" strokeWidth={1} strokeDasharray="4 4" />

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
                  fill={c.value >= 0 ? "#7c3aed" : "#b91c1c"}
                  opacity={hover === null || hover === i ? 1 : 0.45}
                  onMouseEnter={() => setHover(i)}
                />
              );
            })
          : (
            <>
              <path d={areaPath} fill={`url(#${gradientId})`} stroke="none" />
              <path d={linePath} fill="none" stroke="#7c3aed" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" />
              {coords.map((c, i) => (
                <circle
                  key={i}
                  cx={c.x}
                  cy={c.y}
                  r={hover === i ? 5 : 3}
                  fill="#7c3aed"
                  stroke="#fff"
                  strokeWidth={1.5}
                  onMouseEnter={() => setHover(i)}
                  style={{ transition: "r 100ms ease" }}
                />
              ))}
            </>
          )}

        {/* invisible wide hit targets for touch/hover */}
        {coords.map((c, i) => (
          <rect
            key={`hit-${i}`}
            x={c.x - stepX / 2}
            y={0}
            width={stepX}
            height={height}
            fill="transparent"
            onMouseEnter={() => setHover(i)}
            onTouchStart={() => setHover(i)}
          />
        ))}

        {hover !== null && (
          <g>
            <line x1={coords[hover].x} y1={padding} x2={coords[hover].x} y2={height - padding} stroke="#a78bfa" strokeWidth={1} strokeDasharray="3 3" />
          </g>
        )}
      </svg>

      <div className="flex justify-between text-[10px] text-text-secondary mt-1 px-1">
        {points.map((p, i) => (
          <span key={i} className={i === hover ? "text-brand-purple-600 font-medium" : ""}>
            {p.label}
          </span>
        ))}
      </div>

      {hover !== null && (
        <div className="mt-2 inline-flex items-center gap-2 glass-panel px-3 py-1.5 text-xs" role="status">
          <span className="text-text-secondary">{points[hover].label}</span>
          <span className="font-semibold text-text-primary">{fmt(points[hover].value)}</span>
        </div>
      )}
    </div>
  );
}
