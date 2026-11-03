"use client";

import { ReactNode, useEffect, useRef, useState } from "react";
import { IconChevronDown } from "./icons";

interface GlassDropdownProps {
  label: ReactNode;
  children: (close: () => void) => ReactNode;
  align?: "left" | "right";
}

export default function GlassDropdown({ label, children, align = "right" }: GlassDropdownProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  return (
    <div ref={ref} className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="btn-secondary-v2 px-3 py-2 text-sm inline-flex items-center gap-1.5"
      >
        {label}
        <IconChevronDown size={14} />
      </button>
      {open && (
        <div
          role="menu"
          className={`absolute z-40 mt-2 min-w-[12rem] glass-panel p-1.5 ${align === "right" ? "right-0" : "left-0"}`}
        >
          {children(() => setOpen(false))}
        </div>
      )}
    </div>
  );
}
