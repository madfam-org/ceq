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
    expect(screen.getByText(/build once, run everywhere/i)).toBeInTheDocument();
    expect(screen.getByText(/stable assets/i)).toBeInTheDocument();
  });

  it("starts the free sign-in flow from the hero CTA", async () => {
    const user = userEvent.setup();
    render(<MarketingLanding />);

    await user.click(screen.getAllByRole("button", { name: /start generating free/i })[0]);

    expect(authMock.login).toHaveBeenCalledWith("/templates?onboarding=demo");
  });

  it("lets visitors switch demo templates", async () => {
    const user = userEvent.setup();
    global.fetch = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/v1/demo/presets")) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve([
              {
                id: "card",
                label: "Card",
                title: "Card Standard",
                api_path: "card",
                credit_cost: 5,
                input_summary: "Stratum Chronicle",
                output_summary: "512×768 PNG",
              },
              {
                id: "audio",
                label: "Audio",
                title: "Tone Beep",
                api_path: "audio",
                credit_cost: 3,
                input_summary: "A4 pulse",
                output_summary: "22.05kHz WAV",
              },
            ]),
        } as Response);
      }
      return Promise.resolve({ ok: false } as Response);
    });

    render(<MarketingLanding />);

    await vi.waitFor(() => {
      expect(screen.getByRole("heading", { name: /card standard/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /audio/i }));

    expect(screen.getByRole("heading", { name: /tone beep/i })).toBeInTheDocument();
  });

  it("runs live demo renders against the public API", async () => {
    const user = userEvent.setup();
    global.fetch = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/v1/demo/presets")) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve([
              {
                id: "card",
                label: "Card",
                title: "Card Standard",
                api_path: "card",
                credit_cost: 5,
                input_summary: "Stratum Chronicle",
                output_summary: "512×768 PNG",
              },
            ]),
        } as Response);
      }
      if (url.includes("/v1/demo/render/card") && init?.method === "POST") {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              url: "https://cdn.ceq.lol/render/card-standard/demo.png",
              storage_uri: "r2://ceq-assets/render/card-standard/demo.png",
              hash: "abc123",
              template: "card-standard",
              template_version: "1",
              content_type: "image/png",
              cached: false,
            }),
        } as Response);
      }
      if (url.includes("/v1/demo/status")) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              api: "ok",
              demo_enabled: true,
              workflow_templates: 4,
              render_templates: 3,
              render_template_names: ["card-standard"],
            }),
        } as Response);
      }
      if (url.includes("/v1/templates/")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ templates: [] }),
        } as Response);
      }
      return Promise.resolve({ ok: false } as Response);
    });

    render(<MarketingLanding />);

    await vi.waitFor(() => {
      expect(screen.getByRole("button", { name: /run live render/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /run live render/i }));

    await vi.waitFor(() => {
      expect(screen.getByText(/cache miss · bill once/i)).toBeInTheDocument();
    });
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

  it("surfaces founder-seat conversion framing in paid tiers", () => {
    render(<MarketingLanding />);

    expect(
      screen.getByRole("button", { name: /reserve founder price/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /book studio pilot/i }),
    ).toBeInTheDocument();
  });
});
