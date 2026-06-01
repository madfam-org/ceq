import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { UserMenu } from "@/components/layout/user-menu";
import { TooltipProvider } from "@/components/ui/tooltip";

vi.mock("@/contexts/auth-context", () => ({
  useAuth: vi.fn(),
}));

vi.mock("@/lib/hooks", () => ({
  useCreditBalance: vi.fn(),
}));

import { useAuth } from "@/contexts/auth-context";
import { useCreditBalance } from "@/lib/hooks";

function renderUserMenu() {
  return render(
    <TooltipProvider>
      <UserMenu />
    </TooltipProvider>
  );
}

describe("UserMenu", () => {
  const mockUseAuth = vi.mocked(useAuth);
  const mockUseCreditBalance = vi.mocked(useCreditBalance);

  beforeEach(() => {
    mockUseCreditBalance.mockReturnValue({
      data: { user_id: "user-1", org_id: null, balance: 100 },
      isLoading: false,
      isFetching: false,
    } as ReturnType<typeof useCreditBalance>);
  });

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

  it("shows credit balance for authenticated users", async () => {
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
    mockUseCreditBalance.mockReturnValue({
      data: { user_id: "user-1", org_id: null, balance: 2500 },
      isLoading: false,
      isFetching: false,
    } as ReturnType<typeof useCreditBalance>);

    renderUserMenu();

    await userEvent.click(screen.getByRole("button", { name: "Account" }));

    expect(screen.getByText("Credits")).toBeInTheDocument();
    expect(screen.getByText("2,500")).toBeInTheDocument();
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
