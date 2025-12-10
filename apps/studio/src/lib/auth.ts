/**
 * CEQ Authentication Module
 *
 * Lightweight OIDC integration with Janua (auth.madfam.io)
 * for the MADFAM ecosystem SSO.
 */

// Auth configuration from environment
export const AUTH_CONFIG = {
  // Janua OIDC endpoints
  januaUrl: process.env.NEXT_PUBLIC_JANUA_URL || "https://auth.madfam.io",
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

// Token storage keys
const TOKEN_KEY = "janua_token";
const REFRESH_TOKEN_KEY = "janua_refresh_token";
const USER_KEY = "janua_user";

/**
 * Get the current access token
 */
export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

/**
 * Get the refresh token
 */
export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

/**
 * Get the current user from storage
 */
export function getStoredUser(): User | null {
  if (typeof window === "undefined") return null;
  const stored = localStorage.getItem(USER_KEY);
  if (!stored) return null;
  try {
    return JSON.parse(stored);
  } catch {
    return null;
  }
}

/**
 * Store auth tokens and user
 */
export function setAuth(
  accessToken: string,
  refreshToken: string | null,
  user: User
): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(TOKEN_KEY, accessToken);
  if (refreshToken) {
    localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  }
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

/**
 * Clear all auth data
 */
export function clearAuth(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

/**
 * Parse JWT to get user info (without verification - that's done by API)
 */
export function parseJwt(token: string): User | null {
  try {
    const base64Url = token.split(".")[1];
    const base64 = base64Url.replace(/-/g, "+").replace(/_/g, "/");
    const payload = JSON.parse(
      decodeURIComponent(
        atob(base64)
          .split("")
          .map((c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
          .join("")
      )
    );

    return {
      id: payload.sub,
      email: payload.email,
      name: payload.name || payload.email?.split("@")[0],
      avatar: payload.avatar,
    };
  } catch {
    return null;
  }
}

/**
 * Check if token is expired
 */
export function isTokenExpired(token: string): boolean {
  try {
    const base64Url = token.split(".")[1];
    const base64 = base64Url.replace(/-/g, "+").replace(/_/g, "/");
    const payload = JSON.parse(atob(base64));
    const exp = payload.exp * 1000; // Convert to milliseconds
    return Date.now() >= exp - 60000; // Expired or expiring in 1 minute
  } catch {
    return true;
  }
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
    state: returnTo || "/",
  });

  return `${AUTH_CONFIG.januaUrl}/authorize?${params}`;
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
  const refreshToken = getRefreshToken();
  if (!refreshToken) return null;

  try {
    const response = await fetch("/api/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (!response.ok) {
      clearAuth();
      return null;
    }

    const data = await response.json();
    const user = parseJwt(data.access_token);

    if (user) {
      setAuth(data.access_token, data.refresh_token || refreshToken, user);
    }

    return data.access_token;
  } catch {
    clearAuth();
    return null;
  }
}

/**
 * Validate token with Janua API
 */
export async function validateToken(token: string): Promise<User | null> {
  try {
    const response = await fetch(`${AUTH_CONFIG.januaUrl}/api/v1/auth/me`, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (!response.ok) return null;

    const data = await response.json();
    return {
      id: data.id,
      email: data.email,
      name: data.first_name || data.email?.split("@")[0],
      avatar: data.avatar_url,
    };
  } catch {
    return null;
  }
}
