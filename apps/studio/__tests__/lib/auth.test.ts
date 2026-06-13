import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import {
  AUTH_CONFIG,
  clearAuth,
  getRefreshToken,
  getSessionAuth,
  getStoredUser,
  getToken,
  getLoginUrl,
  sanitizeReturnPath,
  getLogoutUrl,
  isTokenExpired,
  parseJwt,
  setAuth,
} from "@/lib/auth";

describe("Auth Configuration", () => {
  it("has Janua URL configured", () => {
    expect(AUTH_CONFIG.januaUrl).toContain("auth.madfam.io");
  });

  it("has client ID configured", () => {
    expect(AUTH_CONFIG.clientId).toBeDefined();
  });

  it("has redirect URI based on window origin", () => {
    expect(AUTH_CONFIG.redirectUri).toContain("/auth/callback");
  });

  it("has post logout URI based on window origin", () => {
    expect(AUTH_CONFIG.postLogoutUri).toBeDefined();
  });
});

describe("Session state", () => {
  beforeEach(() => {
    clearAuth();
  });

  it("getToken returns null when no token is set", () => {
    expect(getToken()).toBeNull();
  });

  it("setAuth updates in-memory auth state", () => {
    const user = { id: "user-123", email: "test@example.com", name: "Test User" };
    setAuth("access-token", "refresh-token", user);

    expect(getToken()).toBe("access-token");
    expect(getStoredUser()).toEqual(user);
    expect(getRefreshToken()).toBeNull();
  });

  it("clearAuth clears in-memory auth state", () => {
    const user = { id: "user-123", email: "test@example.com" };
    setAuth("access-token", "refresh-token", user);

    clearAuth();

    expect(getToken()).toBeNull();
    expect(getStoredUser()).toBeNull();
    expect(getRefreshToken()).toBeNull();
  });
});

describe("JWT Parsing", () => {
  function createTestJwt(payload: object): string {
    const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }));
    const body = btoa(JSON.stringify(payload));
    const signature = "test-signature";
    return `${header}.${body}.${signature}`;
  }

  it("parseJwt extracts user from valid token", () => {
    const token = createTestJwt({
      sub: "user-123",
      email: "test@example.com",
      name: "Test User",
      avatar: "https://example.com/avatar.jpg",
    });

    expect(parseJwt(token)).toEqual({
      id: "user-123",
      email: "test@example.com",
      name: "Test User",
      avatar: "https://example.com/avatar.jpg",
    });
  });

  it("parseJwt uses email prefix when no name", () => {
    const token = createTestJwt({
      sub: "user-123",
      email: "test@example.com",
    });

    expect(parseJwt(token)?.name).toBe("test");
  });

  it("parseJwt returns null for invalid token", () => {
    expect(parseJwt("invalid-token")).toBeNull();
  });

  it("parseJwt returns null for malformed JWT", () => {
    expect(parseJwt("not.a.valid.jwt")).toBeNull();
  });
});

describe("Token Expiration", () => {
  function createTestJwt(payload: object): string {
    const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }));
    const body = btoa(JSON.stringify(payload));
    const signature = "test-signature";
    return `${header}.${body}.${signature}`;
  }

  it("isTokenExpired returns true for expired token", () => {
    const expiredToken = createTestJwt({
      sub: "user-123",
      exp: Math.floor(Date.now() / 1000) - 3600, // 1 hour ago
    });

    expect(isTokenExpired(expiredToken)).toBe(true);
  });

  it("isTokenExpired returns true for token expiring soon", () => {
    const expiringToken = createTestJwt({
      sub: "user-123",
      exp: Math.floor(Date.now() / 1000) + 30, // 30 seconds from now
    });

    expect(isTokenExpired(expiringToken)).toBe(true);
  });

  it("isTokenExpired returns false for valid token", () => {
    const validToken = createTestJwt({
      sub: "user-123",
      exp: Math.floor(Date.now() / 1000) + 3600, // 1 hour from now
    });

    expect(isTokenExpired(validToken)).toBe(false);
  });

  it("isTokenExpired returns true for invalid token", () => {
    expect(isTokenExpired("invalid-token")).toBe(true);
  });
});

describe("URL Generation", () => {
  it("getLoginUrl generates authorization URL", () => {
    const url = getLoginUrl();

    expect(url).toContain(AUTH_CONFIG.januaUrl);
    expect(url).toContain("/api/v1/oauth/authorize");
    expect(url).toContain("client_id=");
    expect(url).toContain("redirect_uri=");
    expect(url).toContain("response_type=code");
    expect(url).toContain("scope=openid+profile+email");
  });

  it("getLoginUrl includes returnTo in state", () => {
    const url = getLoginUrl("/dashboard");

    expect(url).toContain("state=%2Fdashboard");
  });

  it("getLoginUrl sanitizes absolute returnTo paths for state", () => {
    const url = getLoginUrl("https://evil.com/phishing");

    expect(url).toContain("state=%2F");
    expect(url).not.toContain("https%3A%2F%2Fevil.com");
  });

  it("getLogoutUrl returns Studio login surface", () => {
    const url = getLogoutUrl();

    expect(url).toContain("/login");
    expect(url).not.toContain("/logout");
  });
});

describe("Return path sanitization", () => {
  it("defaults missing returnTo to root", () => {
    expect(sanitizeReturnPath(undefined)).toBe("/");
  });

  it("keeps internal relative paths", () => {
    expect(sanitizeReturnPath("/templates?category=social")).toBe(
      "/templates?category=social"
    );
  });

  it("rejects absolute URLs and returns root", () => {
    expect(sanitizeReturnPath("https://evil.com/")).toBe("/");
  });

  it("rejects javascript protocol urls and returns root", () => {
    expect(sanitizeReturnPath("javascript:alert(1)")).toBe("/");
  });
});

describe("Session bootstrap", () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
  });

  function createTestJwt(payload: object): string {
    const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }));
    const body = btoa(JSON.stringify(payload));
    const signature = "test-signature";
    return `${header}.${body}.${signature}`;
  }

  it("returns null when the server session is absent", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
    });

    await expect(getSessionAuth()).resolves.toBeNull();
    expect(global.fetch).toHaveBeenCalledWith("/api/auth/session", {
      method: "GET",
      credentials: "same-origin",
      cache: "no-store",
    });
  });

  it("returns the server session user and access token", async () => {
    const accessToken = createTestJwt({
      sub: "user-123",
      email: "test@example.com",
    });
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        access_token: accessToken,
        user: {
          id: "user-123",
          email: "test@example.com",
          name: "test",
        },
      }),
    });

    await expect(getSessionAuth()).resolves.toEqual({
      accessToken,
      user: {
        id: "user-123",
        email: "test@example.com",
        name: "test",
      },
    });
  });
});
