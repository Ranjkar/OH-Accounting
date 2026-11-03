"use client";

/* Hand-written stroke icon set -- no icon library dependency. Covers the
 * navigation groups and the handful of action icons the redesign needs.
 * Each icon is a plain 20x20 (or 24x24) stroke SVG, consistent weight. */

import { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function base(props: IconProps, children: React.ReactNode) {
  const { size = 18, ...rest } = props;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...rest}
    >
      {children}
    </svg>
  );
}

export const IconDashboard = (p: IconProps) => base(p, <><rect x="3" y="3" width="7" height="9" rx="1.5" /><rect x="14" y="3" width="7" height="5" rx="1.5" /><rect x="14" y="12" width="7" height="9" rx="1.5" /><rect x="3" y="16" width="7" height="5" rx="1.5" /></>);
export const IconLedger = (p: IconProps) => base(p, <><path d="M6 3h9l3 3v15H6z" /><path d="M15 3v3h3" /><path d="M9 11h6M9 15h6" /></>);
export const IconInvoice = (p: IconProps) => base(p, <><rect x="4" y="3" width="16" height="18" rx="1.5" /><path d="M8 8h8M8 12h8M8 16h5" /></>);
export const IconBank = (p: IconProps) => base(p, <><path d="M3 10l9-6 9 6" /><rect x="5" y="10" width="14" height="8" /><path d="M3 21h18" /></>);
export const IconPayroll = (p: IconProps) => base(p, <><circle cx="9" cy="8" r="3" /><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6" /><path d="M17 7h4M17 11h4" /></>);
export const IconTax = (p: IconProps) => base(p, <><rect x="4" y="4" width="16" height="16" rx="2" /><path d="M9 9h.01M15 9h.01" /><path d="M8 15l8-6" /></>);
export const IconPlanning = (p: IconProps) => base(p, <><path d="M4 19V5M4 19h16" /><path d="M8 15l3-4 3 2 4-6" /></>);
export const IconDocuments = (p: IconProps) => base(p, <><path d="M7 3h7l3 3v15H7z" /><path d="M14 3v3h3" /></>);
export const IconSettings = (p: IconProps) => base(p, <><circle cx="12" cy="12" r="3" /><path d="M19.4 13a7.4 7.4 0 0 0 0-2l1.9-1.5-2-3.4-2.2.8a7.6 7.6 0 0 0-1.7-1l-.3-2.4h-4l-.3 2.4a7.6 7.6 0 0 0-1.7 1l-2.2-.8-2 3.4L4.6 11a7.4 7.4 0 0 0 0 2l-1.9 1.5 2 3.4 2.2-.8c.5.4 1.1.7 1.7 1l.3 2.4h4l.3-2.4c.6-.3 1.2-.6 1.7-1l2.2.8 2-3.4z" /></>);
export const IconChevronDown = (p: IconProps) => base(p, <path d="M6 9l6 6 6-6" />);
export const IconChevronRight = (p: IconProps) => base(p, <path d="M9 6l6 6-6 6" />);
export const IconMenu = (p: IconProps) => base(p, <path d="M4 6h16M4 12h16M4 18h16" />);
export const IconX = (p: IconProps) => base(p, <path d="M6 6l12 12M18 6L6 18" />);
export const IconSearch = (p: IconProps) => base(p, <><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" /></>);
export const IconBell = (p: IconProps) => base(p, <><path d="M6 9a6 6 0 1 1 12 0c0 4 1.5 5 1.5 5H4.5S6 13 6 9Z" /><path d="M10 20a2 2 0 0 0 4 0" /></>);
export const IconPlus = (p: IconProps) => base(p, <path d="M12 5v14M5 12h14" />);
export const IconUser = (p: IconProps) => base(p, <><circle cx="12" cy="8" r="4" /><path d="M4 20c0-4 3.5-7 8-7s8 3 8 7" /></>);
export const IconLogout = (p: IconProps) => base(p, <><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><path d="M16 17l5-5-5-5" /><path d="M21 12H9" /></>);
export const IconCollapse = (p: IconProps) => base(p, <><path d="M9 3v18" /><path d="M15 9l-3 3 3 3" /></>);
export const IconExpand = (p: IconProps) => base(p, <><path d="M9 3v18" /><path d="M13 9l3 3-3 3" /></>);
export const IconBuilding = (p: IconProps) => base(p, <><rect x="4" y="3" width="16" height="18" /><path d="M9 7h2M13 7h2M9 11h2M13 11h2M9 15h2M13 15h2" /></>);
export const IconChart = (p: IconProps) => base(p, <><path d="M4 4v16h16" /><path d="M8 15l2.5-4L14 13l3-6" /></>);
export const IconAlertTriangle = (p: IconProps) => base(p, <><path d="M12 3l9 16H3z" /><path d="M12 10v4M12 17h.01" /></>);
export const IconCheckCircle = (p: IconProps) => base(p, <><circle cx="12" cy="12" r="9" /><path d="M8.5 12.5l2.5 2.5 5-5.5" /></>);
export const IconClock = (p: IconProps) => base(p, <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3.5 2" /></>);
export const IconArrowUp = (p: IconProps) => base(p, <><path d="M12 19V5" /><path d="M6 11l6-6 6 6" /></>);
export const IconArrowDown = (p: IconProps) => base(p, <><path d="M12 5v14" /><path d="M6 13l6 6 6-6" /></>);
export const IconSparkle = (p: IconProps) => base(p, <><path d="M12 3v4M12 17v4M3 12h4M17 12h4" /><path d="M12 8a4 4 0 0 0 4 4 4 4 0 0 0-4 4 4 4 0 0 0-4-4 4 4 0 0 0 4-4Z" /></>);
export const IconCalculator = (p: IconProps) => base(p, <><rect x="5" y="3" width="14" height="18" rx="1.5" /><path d="M8 7h8M8 11h2M12 11h2M16 11h0M8 15h2M12 15h2M16 15h0" /></>);
export const IconCalendar = (p: IconProps) => base(p, <><rect x="3" y="5" width="18" height="16" rx="1.5" /><path d="M3 9h18M8 3v4M16 3v4" /></>);
export const IconShield = (p: IconProps) => base(p, <path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z" />);
export const IconUsers = (p: IconProps) => base(p, <><circle cx="8" cy="8" r="3" /><circle cx="17" cy="9" r="2.5" /><path d="M2 20c0-3 2.7-5.5 6-5.5s6 2.5 6 5.5" /><path d="M14.5 15c2.5.3 4.5 2.3 4.5 5" /></>);
