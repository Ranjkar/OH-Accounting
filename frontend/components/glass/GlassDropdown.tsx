"use client";

import { ReactNode, useEffect, useRef, useState } from "react";
import { IconChevronDown } from "./icons";

interface GlassDropdownProps {
  label: ReactNode;
  children: (close: () => void) => ReactNode;
  align?: "left" | "right";
}

const MENU_ITEM_SELECTOR = '[role="menuitem"], a[href], button:not([disabled])';

export default function GlassDropdown({ label, children, align = "right" }: GlassDropdownProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  function close() {
    setOpen(false);
    triggerRef.current?.focus();
  }

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  useEffect(() => {
    if (!open || !menuRef.current) return;
    // Move focus into the menu on open -- matches native <select>/menu
    // behaviour and is required for a keyboard user to reach the items.
    const items = menuRef.current.querySelectorAll<HTMLElement>(MENU_ITEM_SELECTOR);
    items[0]?.focus();

    function onKey(e: KeyboardEvent) {
      const list = Array.from(menuRef.current?.querySelectorAll<HTMLElement>(MENU_ITEM_SELECTOR) ?? []);
      const currentIndex = list.indexOf(document.activeElement as HTMLElement);
      if (e.key === "Escape") {
        e.preventDefault();
        close();
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        list[(currentIndex + 1) % list.length]?.focus();
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        list[(currentIndex - 1 + list.length) % list.length]?.focus();
      } else if (e.key === "Home") {
        e.preventDefault();
        list[0]?.focus();
      } else if (e.key === "End") {
        e.preventDefault();
        list[list.length - 1]?.focus();
      } else if (e.key === "Tab") {
        // Tabbing out of the menu closes it rather than trapping focus --
        // this is a menu, not a modal dialog.
        close();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <div ref={ref} className="relative inline-block">
      <button
        ref={triggerRef}
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
          ref={menuRef}
          role="menu"
          className={`absolute z-40 mt-2 min-w-[12rem] glass-panel p-1.5 ${align === "right" ? "right-0" : "left-0"}`}
        >
          {
            // `close` only reads triggerRef.current inside its own body,
            // invoked later from a menu item's event handler -- never
            // during this render itself. Passing the function reference
            // down is the standard "render prop" callback pattern; it is
            // not the render-phase ref read the rule guards against.
            // eslint-disable-next-line react-hooks/refs
            children(close)
          }
        </div>
      )}
    </div>
  );
}
