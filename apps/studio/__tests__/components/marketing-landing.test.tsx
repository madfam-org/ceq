import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { MarketingLanding } from "@/components/landing/marketing-landing";

const authMock = vi.hoisted(() => ({
  login: vi.fn(),
}));

vi.mock("@/contexts/auth-context", () => ({
  useAuth: () => ({
    login: authMock.login,
    user: null,
    isAuthenticated: false,
    isLoading: false,
    token: null,
    logout: vi.fn(),
    refreshToken: vi.fn(),
  }),
}));

describe("MarketingLanding", () => {
  beforeEach(() => {
    authMock.login.mockClear();
  });

  it("leads with the repeatable production workflow promise", () => {
    render(<MarketingLanding />);

    expect(
      screen.getByRole("heading", {
        name: /generate repeatable client-ready ai assets/i,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText(/deterministic render pipeline live/i)).toBeInTheDocument();
    expect(screen.getByText(/same inputs, same asset/i)).toBeInTheDocument();
  });

  it("starts the free sign-in flow from the hero CTA", async () => {
    const user = userEvent.setup();
    render(<MarketingLanding />);

    await user.click(screen.getAllByRole("button", { name: /start generating free/i })[0]);

    expect(authMock.login).toHaveBeenCalledWith("/");
  });

  it("lets visitors switch demo templates", async () => {
    const user = userEvent.setup();
    render(<MarketingLanding />);

    expect(screen.getByRole("heading", { name: /card standard/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /audio/i }));

    expect(screen.getByRole("heading", { name: /tone beep/i })).toBeInTheDocument();
    expect(screen.getByText(/a4 signal/i)).toBeInTheDocument();
  });

  it("shows cache-hit economics after rerunning identical inputs", async () => {
    const user = userEvent.setup();
    render(<MarketingLanding />);

    expect(screen.getByText(/cache miss · bill once/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /run deterministic render/i }));

    expect(screen.getByText(/cache hit · no rebill/i)).toBeInTheDocument();
    expect(screen.getByText(/0 cached/i)).toBeInTheDocument();
  });

  it("links buyer safety docs from the trust section", () => {
    render(<MarketingLanding />);

    expect(screen.getByRole("link", { name: /terms/i })).toHaveAttribute(
      "href",
      "/legal/terms",
    );
    expect(screen.getByRole("link", { name: /privacy/i })).toHaveAttribute(
      "href",
      "/legal/privacy",
    );
  });
});
