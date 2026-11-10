"use client";

import { InputHTMLAttributes, SelectHTMLAttributes, forwardRef, ReactNode } from "react";

export const GlassInput = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function GlassInput(
  { className = "", ...rest },
  ref
) {
  return <input ref={ref} className={`input-v2 px-3 py-2 text-sm w-full ${className}`} {...rest} />;
});

interface GlassSelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  children: ReactNode;
}

export const GlassSelect = forwardRef<HTMLSelectElement, GlassSelectProps>(function GlassSelect(
  { className = "", children, ...rest },
  ref
) {
  return (
    <select ref={ref} className={`input-v2 px-3 py-2 text-sm ${className}`} {...rest}>
      {children}
    </select>
  );
});
