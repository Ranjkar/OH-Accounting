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

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

export default function GlassModal({ open, onClose, title, children, footer }: GlassModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    // Remember what had focus before the dialog opened, to return it on close.
    triggerRef.current = document.activeElement as HTMLElement | null;
    panelRef.current?.focus();

    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key !== "Tab" || !panelRef.current) return;

      // Focus trap: Tab/Shift+Tab cycle within the dialog's own focusable
      // elements instead of escaping to the page behind it.
      const focusables = Array.from(panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const active = document.activeElement;

      if (e.shiftKey && active === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      // Return focus to whatever triggered the dialog -- never leave focus
      // stranded on a removed element or silently reset to <body>.
      triggerRef.current?.focus();
    };
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
        className="glass-panel-elevated relative w-full max-w-lg max-h-[85vh] overflow-y-auto"
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-border sticky top-0 bg-inherit">
          <h2 className="text-card-heading">{title}</h2>
          <button onClick={onClose} aria-label="Close dialog" className="text-text-secondary hover:text-text-primary p-1 rounded-md">
            <IconX size={18} />
          </button>
        </div>
        <div className="p-5">{children}</div>
        {footer && <div className="px-5 py-4 border-t border-border flex justify-end gap-2">{footer}</div>}
      </div>
    </div>
  );
}
