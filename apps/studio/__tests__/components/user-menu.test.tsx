import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { UserMenu } from "@/components/layout/user-menu";
import { TooltipProvider } from "@/components/ui/tooltip";

vi.mock("@/contexts/auth-context", () => ({
  useAuth: vi.fn(),
}));

import { useAuth } from "@/contexts/auth-context";

function renderUserMenu() {
  return render(
    <TooltipProvider>
      <UserMenu />
    </TooltipProvider>
  );
}

describe("UserMenu", () => {
  const mockUseAuth = vi.mocked(useAuth);

  it("exposes an Account control for authenticated users", () => {
    mockUseAuth.mockReturnValue({
      user: {
        id: "user-1",
        email: "studio-e2e@madfam.io",
        name: "Studio E2E",
      },
      isAuthenticated: true,
      isLoading: false,
      token: "access.jwt",
      login: vi.fn(),
      logout: vi.fn(),
      refreshToken: vi.fn(),
    });

    renderUserMenu();

    expect(screen.getByRole("button", { name: "Account" })).toBeInTheDocument();
  });

  it("shows Sign in when unauthenticated", () => {
    mockUseAuth.mockReturnValue({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      token: null,
      login: vi.fn(),
      logout: vi.fn(),
      refreshToken: vi.fn(),
    });

    renderUserMenu();

    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });
});
