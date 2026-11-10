import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { AuthProvider, useAuth } from "../auth-context";

/**
 * Phase 17.3 regression tests for audit finding 6.13.
 *
 * Before the fix, `logout()` in auth-context.tsx was purely client-side:
 *
 *     function logout() {
 *       localStorage.removeItem("token");
 *       setToken(null); setUser(null); router.push("/login");
 *     }
 *
 * and `lib/api.ts` had no `logout` method at all, so nothing ever called
 * POST /api/v1/auth/logout. Because the backend issues 24-hour access
 * tokens with no refresh token, a JWT captured before logout stayed
 * cryptographically valid AND kept passing the `token_version` revocation
 * check for the rest of its lifetime. The revocation machinery the backend
 * documents at length was never triggered by the app's most common
 * revocation event.
 *
 * These tests pin the three properties the fix must guarantee:
 *   1. the backend endpoint is actually called with the live token;
 *   2. local state is ALWAYS cleared and the user redirected, even when the
 *      revocation request fails -- a network error must not strand someone
 *      on an authenticated page;
 *   3. the token is still revoked when React state has not hydrated yet but
 *      localStorage holds a token.
 */

const mockLogout = vi.fn();
const mockMe = vi.fn();

vi.mock("../api", () => ({
  api: {
    logout: (...args: unknown[]) => mockLogout(...args),
    me: (...args: unknown[]) => mockMe(...args),
  },
}));

const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, replace: mockPush }),
}));

const USER = {
  id: 1,
  email: "admin@acme.nl",
  full_name: "Admin",
  role: "admin",
  mfa_enabled: false,
  is_platform_admin: false,
  locale: null,
  tenant_default_locale: "nl",
};

function Probe() {
  const { token, user, logout } = useAuth();
  return (
    <div>
      <span data-testid="token">{token ?? "none"}</span>
      <span data-testid="user">{user ? user.email : "none"}</span>
      <button data-testid="logout" onClick={() => void logout()}>
        log out
      </button>
    </div>
  );
}

/** Renders the provider and waits for the mount effect to restore the
 * session from localStorage, so `token` state is populated before the test
 * acts -- mirroring a real signed-in page load. */
async function renderSignedIn(storedToken: string | null) {
  if (storedToken) localStorage.setItem("token", storedToken);
  render(
    <AuthProvider>
      <Probe />
    </AuthProvider>
  );
  if (storedToken) {
    await waitFor(() => expect(screen.getByTestId("token")).toHaveTextContent(storedToken));
  } else {
    await waitFor(() => expect(screen.getByTestId("token")).toHaveTextContent("none"));
  }
}

describe("AuthProvider.logout", () => {
  beforeEach(() => {
    localStorage.clear();
    mockLogout.mockReset();
    mockMe.mockReset();
    mockPush.mockReset();
    mockLogout.mockResolvedValue(undefined);
    mockMe.mockResolvedValue(USER);
  });

  afterEach(() => {
    cleanup();
    localStorage.clear();
  });

  it("calls POST /auth/logout with the live token so the backend can bump token_version", async () => {
    await renderSignedIn("live-jwt");

    await act(async () => {
      screen.getByTestId("logout").click();
    });

    expect(mockLogout).toHaveBeenCalledTimes(1);
    expect(mockLogout).toHaveBeenCalledWith("live-jwt");
  });

  it("clears local auth state and redirects to /login", async () => {
    await renderSignedIn("live-jwt");

    await act(async () => {
      screen.getByTestId("logout").click();
    });

    await waitFor(() => expect(screen.getByTestId("token")).toHaveTextContent("none"));
    expect(screen.getByTestId("user")).toHaveTextContent("none");
    expect(localStorage.getItem("token")).toBeNull();
    expect(mockPush).toHaveBeenCalledWith("/login");
  });

  it("STILL clears local state and redirects when the revocation request fails", async () => {
    // The critical property: a 401 (token already expired), a 500, or the
    // backend being unreachable must never leave the user sitting on an
    // authenticated page with a token still in localStorage.
    mockLogout.mockRejectedValue(new Error("network unreachable"));
    await renderSignedIn("live-jwt");

    await act(async () => {
      screen.getByTestId("logout").click();
    });

    await waitFor(() => expect(screen.getByTestId("token")).toHaveTextContent("none"));
    expect(screen.getByTestId("user")).toHaveTextContent("none");
    expect(localStorage.getItem("token")).toBeNull();
    expect(mockPush).toHaveBeenCalledWith("/login");
  });

  it("does not swallow the failure silently in a way that skips the redirect", async () => {
    mockLogout.mockRejectedValue(new Error("500"));
    await renderSignedIn("live-jwt");

    await act(async () => {
      screen.getByTestId("logout").click();
    });

    expect(mockLogout).toHaveBeenCalledTimes(1);
    expect(mockPush).toHaveBeenCalledTimes(1);
  });

  it("revokes a token found only in localStorage when React state has not hydrated", async () => {
    // No token in state, but one in storage -- e.g. logout pressed during the
    // initial restore, or state cleared by another tab.
    await renderSignedIn(null);
    localStorage.setItem("token", "stored-only-jwt");

    await act(async () => {
      screen.getByTestId("logout").click();
    });

    expect(mockLogout).toHaveBeenCalledWith("stored-only-jwt");
    expect(localStorage.getItem("token")).toBeNull();
    expect(mockPush).toHaveBeenCalledWith("/login");
  });

  it("skips the API call when there is no token anywhere, but still redirects", async () => {
    await renderSignedIn(null);

    await act(async () => {
      screen.getByTestId("logout").click();
    });

    expect(mockLogout).not.toHaveBeenCalled();
    expect(mockPush).toHaveBeenCalledWith("/login");
  });

  it("logs out exactly once per click", async () => {
    await renderSignedIn("live-jwt");

    await act(async () => {
      screen.getByTestId("logout").click();
    });

    expect(mockLogout).toHaveBeenCalledTimes(1);
  });
});
