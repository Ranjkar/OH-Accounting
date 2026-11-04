import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";
import { CompanyProvider } from "@/lib/company-context";
import { ThemeProvider } from "@/lib/theme-context";

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

export const metadata: Metadata = {
  title: "OnHolland Accounting",
  description: "AI-powered accounting and Dutch VAT administration platform",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: NO_FLASH_THEME_SCRIPT }} />
      </head>
      <body className="min-h-full flex flex-col bg-background text-foreground">
        <ThemeProvider>
          <AuthProvider>
            <CompanyProvider>{children}</CompanyProvider>
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
