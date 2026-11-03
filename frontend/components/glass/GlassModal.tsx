"use client";

import { ReactNode, useEffect, useRef } from "react";
import { IconX } from "./icons";

interface GlassModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
}

export default function GlassModal({ open, onClose, title, children, footer }: GlassModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    panelRef.current?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="presentation">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} aria-hidden />
      <div
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="glass-panel relative w-full max-w-lg max-h-[85vh] overflow-y-auto"
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-white/40 sticky top-0 bg-inherit">
          <h2 className="font-semibold text-text-primary">{title}</h2>
          <button onClick={onClose} aria-label="Close dialog" className="text-text-secondary hover:text-text-primary p-1 rounded-md">
            <IconX size={18} />
          </button>
        </div>
        <div className="p-5">{children}</div>
        {footer && <div className="px-5 py-4 border-t border-white/40 flex justify-end gap-2">{footer}</div>}
      </div>
    </div>
  );
}
