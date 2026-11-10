import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono, Noto_Sans_Arabic, Vazirmatn } from "next/font/google";
import { getLocale } from "next-intl/server";
import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";
import { CompanyProvider } from "@/lib/company-context";
import { ThemeProvider } from "@/lib/theme-context";
import { LocaleProvider } from "@/lib/locale-context";
import { AppLocale, dirFor } from "@/i18n/config";

// Runs before paint, before React hydrates: reads the persisted
// preference (or OS preference for "system"/first visit) and sets
// data-theme synchronously, so the very first painted frame is already
// correct -- no flash of the wrong theme. Intentionally plain JS, not a
// dependency: this must execute before any CSS/JS bundle loads.
const NO_FLASH_THEME_SCRIPT = `
(function () {
  try {
    var stored = localStorage.getItem("onholland-theme");
    var theme = stored === "light" || stored === "dark" ? stored :
      (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    document.documentElement.setAttribute("data-theme", theme);
  } catch (e) {}
})();
`;

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// Phase 16: Arabic-script font coverage for fa-IR/ar-SA. Vazirmatn is used
// for Persian specifically (tuned Persian metrics/ligatures -- noticeably
// better than a generic Arabic-script font for fa text); Noto Sans Arabic
// covers Arabic itself plus acts as a shared fallback. Both are loaded
// unconditionally (not only when that locale is active) so there's no
// layout shift switching into an RTL language mid-session -- the font is
// already in the page's font-family stack, just unused until then. See
// globals.css for where [dir="rtl"]/:lang(fa) apply these as the primary
// sans-serif stack.
const notoSansArabic = Noto_Sans_Arabic({
  variable: "--font-noto-sans-arabic",
  subsets: ["arabic"],
});

const vazirmatn = Vazirmatn({
  variable: "--font-vazirmatn",
  subsets: ["arabic"],
});

export const metadata: Metadata = {
  title: "OnHolland Accounting",
  description: "AI-powered accounting and Dutch VAT administration platform",
};

// Phase 16: resolving the interface locale needs cookies()/headers() (see
// i18n/request.ts). Under `cacheComponents` that makes every route fully
// dynamic (no static shell) -- acceptable here, since every route sits
// behind AuthGuard and fetches account-specific data client-side, and it
// keeps <html lang/dir> synchronous instead of behind a Suspense boundary.
// NOTE: this only holds while next start sees next.config.ts at runtime
// (see frontend/Dockerfile); without it Next falls back to legacy static
// generation and cookies() throws DYNAMIC_SERVER_USAGE.
// `instant` only disables instant-navigation validation for this tree.
export const instant = false;

// viewport-fit=cover lets the shell extend under notches/home indicators and
// pad itself with env(safe-area-inset-*) (see globals.css). No maximum-scale
// or user-scalable=no: pinch-zoom stays available (WCAG 1.4.4). Input-focus
// zoom on iOS is avoided by giving form controls a 16px font on coarse
// pointers instead (globals.css), not by disabling zoom.
export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover" };

export default async function RootLayout({ children }: LayoutProps<"/">) {
  // Server-resolved (cookie, then Accept-Language, then Dutch -- see
  // i18n/request.ts) so <html lang/dir> are correct on the very first
  // byte sent to the browser. Unlike the theme (which can only be known
  // client-side, hence the no-flash script below), locale never flashes.
  const locale = (await getLocale()) as AppLocale;
  const dir = dirFor(locale);

  return (
    <html
      lang={locale}
      dir={dir}
      className={`${geistSans.variable} ${geistMono.variable} ${notoSansArabic.variable} ${vazirmatn.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: NO_FLASH_THEME_SCRIPT }} />
      </head>
      <body className="min-h-full flex flex-col bg-background text-foreground">
        <ThemeProvider>
          <AuthProvider>
            <LocaleProvider initialLocale={locale}>
              <CompanyProvider>{children}</CompanyProvider>
            </LocaleProvider>
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
