"use client";

/** Skeleton shimmer, respects prefers-reduced-motion via the global rule in
 * globals.css (animation-duration forced to ~0 there). */
export default function GlassLoadingState({ rows = 3 }: { rows?: number }) {
  return (
    <div className="glass-panel p-5 space-y-3" role="status" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-4 rounded-full bg-white/40 animate-pulse" style={{ width: `${85 - i * 12}%` }} />
      ))}
    </div>
  );
}

export function GlassErrorState({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-red-300/50 bg-red-500/10 text-red-700 text-sm px-4 py-3" role="alert">
      {message}
    </div>
  );
}
