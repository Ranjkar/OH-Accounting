import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, cleanup, within } from "@testing-library/react";
import GlassSidebar from "../GlassSidebar";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
}));

vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({
    user: { id: 1, full_name: "Test User", email: "test@example.com", role: "admin", is_platform_admin: false, mfa_enabled: false },
    logout: vi.fn(),
  }),
}));

/** Phase 15: only one expandable nav group may be open at a time. Covers
 * the regression this phase fixed -- openGroups used to be a
 * Record<string, boolean>, which let every group stay open
 * independently. */
describe("GlassSidebar accordion behaviour", () => {
  afterEach(() => {
    cleanup();
    localStorage.clear();
  });

  it("opens exactly one group on mount (the one containing the active route)", () => {
    render(<GlassSidebar mobileOpen={false} onMobileClose={() => {}} />);
    // "/" belongs to the Dashboard group -- its "Overview" item should be visible...
    expect(screen.getByRole("link", { name: "Overview" })).toBeInTheDocument();
    // ...while a item from a different group should not be rendered at all.
    expect(screen.queryByRole("link", { name: "General Ledger" })).not.toBeInTheDocument();
  });

  it("opening a second group closes the first -- never both at once", () => {
    render(<GlassSidebar mobileOpen={false} onMobileClose={() => {}} />);
    expect(screen.getByRole("link", { name: "Overview" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Accounting" }));

    expect(screen.getByRole("link", { name: "General Ledger" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Overview" })).not.toBeInTheDocument();
  });

  it("clicking the already-open group's header collapses it", () => {
    render(<GlassSidebar mobileOpen={false} onMobileClose={() => {}} />);
    expect(screen.getByRole("link", { name: "Overview" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Dashboard" }));

    expect(screen.queryByRole("link", { name: "Overview" })).not.toBeInTheDocument();
  });

  it("sets aria-expanded correctly on the open and closed group headers", () => {
    render(<GlassSidebar mobileOpen={false} onMobileClose={() => {}} />);
    expect(screen.getByRole("button", { name: "Dashboard" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("button", { name: "Accounting" })).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(screen.getByRole("button", { name: "Accounting" }));

    expect(screen.getByRole("button", { name: "Dashboard" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByRole("button", { name: "Accounting" })).toHaveAttribute("aria-expanded", "true");
  });

  it("selecting a route inside the mobile drawer closes the drawer", () => {
    // Both the desktop rail (CSS-hidden below lg:, but still present in the
    // DOM in jsdom) and the mobile drawer render when mobileOpen is true --
    // scope the query to the drawer (role="dialog") specifically.
    const onMobileClose = vi.fn();
    render(<GlassSidebar mobileOpen onMobileClose={onMobileClose} />);
    const drawer = screen.getByRole("dialog", { name: "Navigation" });
    const { getByRole } = within(drawer);
    fireEvent.click(getByRole("link", { name: "Overview" }));
    expect(onMobileClose).toHaveBeenCalled();
  });
});
