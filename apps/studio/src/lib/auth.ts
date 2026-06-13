/**
 * CEQ Authentication Module
 *
 * Lightweight OIDC integration with Janua (auth.madfam.io)
 * for the MADFAM ecosystem SSO.
 */

import { isJwtExpired, parseJwtUser } from "@/lib/jwt";

// Auth configuration from environment
export const AUTH_CONFIG = {
  // Janua OIDC endpoints
  januaUrl: process.env.NEXT_PUBLIC_JANUA_URL || "https://auth.madfam.io",
  authorizationEndpoint: `${
    process.env.NEXT_PUBLIC_JANUA_URL || "https://auth.madfam.io"
  }/api/v1/oauth/authorize`,
  tokenEndpoint: `${
    process.env.NEXT_PUBLIC_JANUA_URL || "https://auth.madfam.io"
  }/api/v1/oauth/token`,
  userInfoEndpoint: `${
    process.env.NEXT_PUBLIC_JANUA_URL || "https://auth.madfam.io"
  }/api/v1/oauth/userinfo`,
  clientId: process.env.NEXT_PUBLIC_JANUA_CLIENT_ID || "ceq-studio",

  // CEQ endpoints
  redirectUri:
    typeof window !== "undefined"
      ? `${window.location.origin}/auth/callback`
      : "",
  postLogoutUri:
    typeof window !== "undefined" ? `${window.location.origin}/` : "",
};

// User type from Janua JWT
export interface User {
  id: string;
  email: string;
  name?: string;
  avatar?: string;
}

interface AuthSession {
  accessToken: string | null;
  user: User | null;
}

const authSession: AuthSession = {
  accessToken: null,
  user: null,
};

const SAFE_AUTH_BASE = (() => {
  if (typeof window === "undefined") {
    return "https://app.ceq.lol";
  }

  return window.location.origin;
})();

export function sanitizeReturnPath(returnTo?: string | null): string {
  if (typeof returnTo !== "string") {
    return "/";
  }

  const trimmed = returnTo.trim();
  if (!trimmed) {
    return "/";
  }

  try {
    const candidate = new URL(trimmed, SAFE_AUTH_BASE);
    if (candidate.origin !== SAFE_AUTH_BASE) {
      return "/";
    }

    if (candidate.protocol !== "http:" && candidate.protocol !== "https:") {
      return "/";
    }

    const path = candidate.pathname || "/";
    const allowedPath = path.startsWith("/") ? path : `/${path}`;
    return `${allowedPath}${candidate.search}`;
  } catch {
    return "/";
  }
}

/**
 * Get the current access token from the in-memory session.
 */
export function getToken(): string | null {
  return authSession.accessToken;
}

/**
 * Refresh tokens are stored only in httpOnly cookies.
 */
export function getRefreshToken(): string | null {
  return null;
}

/**
 * Get the current user from storage
 */
export function getStoredUser(): User | null {
  return authSession.user;
}

/**
 * Store auth tokens and user
 */
export function setAuth(
  accessToken: string,
  refreshToken: string | null,
  user: User
): void {
  authSession.accessToken = accessToken;
  authSession.user = user;
  void refreshToken;
}

/**
 * Clear in-memory auth session state.
 */
export function clearAuth(): void {
  authSession.accessToken = null;
  authSession.user = null;
}

/**
 * Probe whether the Studio session can reach authenticated CEQ API routes.
 */
export async function probeApiSession(): Promise<boolean> {
  try {
    const response = await fetch("/api/proxy/v1/credits/balance", {
      method: "GET",
      credentials: "same-origin",
      cache: "no-store",
    });
    return response.ok;
  } catch {
    return false;
  }
}

/**
 * Parse JWT to get user info (without verification - that's done by API)
 */
export function parseJwt(token: string): User | null {
  return parseJwtUser(token);
}

/**
 * Check if token is expired
 */
export function isTokenExpired(token: string): boolean {
  return isJwtExpired(token);
}

/**
 * Generate OIDC authorization URL
 */
export function getLoginUrl(returnTo?: string): string {
  const params = new URLSearchParams({
    client_id: AUTH_CONFIG.clientId,
    redirect_uri: AUTH_CONFIG.redirectUri,
    response_type: "code",
    scope: "openid profile email",
    state: sanitizeReturnPath(returnTo),
  });

  return `${AUTH_CONFIG.authorizationEndpoint}?${params}`;
}

/**
 * Generate logout URL
 */
export function getLogoutUrl(): string {
  const params = new URLSearchParams({
    client_id: AUTH_CONFIG.clientId,
    post_logout_redirect_uri: AUTH_CONFIG.postLogoutUri,
  });

  return `${AUTH_CONFIG.januaUrl}/logout?${params}`;
}

/**
 * Exchange authorization code for tokens
 * This should be called from an API route to keep client_secret server-side
 */
export async function exchangeCodeForTokens(
  code: string
): Promise<{ accessToken: string; refreshToken?: string; user: User } | null> {
  try {
    // Call our own API route which handles the token exchange
    const response = await fetch("/api/auth/token", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
    });

    if (!response.ok) {
      console.error("Token exchange failed:", response.status);
      return null;
    }

    const data = await response.json();
    const user = parseJwt(data.access_token);

    if (!user) {
      console.error("Failed to parse user from token");
      return null;
    }

    return {
      accessToken: data.access_token,
      refreshToken: data.refresh_token,
      user,
    };
  } catch (error) {
    console.error("Token exchange error:", error);
    return null;
  }
}

/**
 * Refresh the access token
 */
export async function refreshAccessToken(): Promise<string | null> {
  try {
    const response = await fetch("/api/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: undefined,
    });

    if (!response.ok) {
      clearAuth();
      return null;
    }

    const data = await response.json();
    const user = parseJwt(data.access_token);

    if (user) {
      setAuth(data.access_token, data.refresh_token || null, user);
    }

    return data.access_token;
  } catch {
    clearAuth();
    return null;
  }
}

/**
 * Bootstrap auth from the httpOnly Studio session cookie.
 */
export async function getSessionAuth(): Promise<{
  accessToken: string;
  user: User;
} | null> {
  try {
    const response = await fetch("/api/auth/session", {
      method: "GET",
      credentials: "same-origin",
      cache: "no-store",
    });

    if (!response.ok) return null;

    const data = await response.json();
    const user = data.user || parseJwt(data.access_token);

    if (!data.access_token || !user) return null;

    return {
      accessToken: data.access_token,
      user,
    };
  } catch {
    return null;
  }
}

/**
 * Validate token with Janua API
 */
export async function validateToken(token: string): Promise<User | null> {
  try {
    const response = await fetch(AUTH_CONFIG.userInfoEndpoint, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (!response.ok) return null;

    const data = await response.json();
    return {
      id: data.sub || data.id,
      email: data.email,
      name: data.name || data.first_name || data.email?.split("@")[0],
      avatar: data.picture || data.avatar_url,
    };
  } catch {
    return null;
  }
}
