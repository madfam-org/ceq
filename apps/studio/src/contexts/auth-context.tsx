"use client";

/**
 * CEQ Auth Context
 *
 * React context for authentication state management with Janua OIDC.
 */

import {
  createContext,
  useContext,
  useCallback,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import {
  type User,
  setAuth,
  clearAuth,
  isTokenExpired,
  refreshAccessToken,
  getLoginUrl,
  getLogoutUrl,
  parseJwt,
  getSessionAuth,
  sanitizeReturnPath,
  probeApiSession,
} from "@/lib/auth";

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  isApiAuthorized: boolean | null;
  token: string | null;
  login: (returnTo?: string) => void;
  logout: () => void;
  refreshToken: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isApiAuthorized, setIsApiAuthorized] = useState<boolean | null>(null);

  const verifyApiSession = useCallback(async (): Promise<boolean> => {
    let authorized = await probeApiSession();
    if (!authorized) {
      const refreshedToken = await refreshAccessToken();
      if (refreshedToken) {
        setToken(refreshedToken);
        const refreshedUser = parseJwt(refreshedToken);
        if (refreshedUser) {
          setUser(refreshedUser);
          setAuth(refreshedToken, null, refreshedUser);
        }
        authorized = await probeApiSession();
      }
    }
    setIsApiAuthorized(authorized);
    return authorized;
  }, []);

  // Initialize auth state from HTTP-only cookie session.
  useEffect(() => {
    const initAuth = async () => {
      const session = await getSessionAuth();
      if (!session) {
        clearAuth();
        setUser(null);
        setToken(null);
        setIsApiAuthorized(null);
        setIsLoading(false);
        return;
      }

      if (isTokenExpired(session.accessToken)) {
        const refreshedToken = await refreshAccessToken();
        if (!refreshedToken) {
          clearAuth();
          setUser(null);
          setToken(null);
          setIsApiAuthorized(false);
          setIsLoading(false);
          return;
        }

        const refreshedUser = parseJwt(refreshedToken) || session.user;
        if (refreshedUser) {
          setAuth(refreshedToken, null, refreshedUser);
        }
        setToken(refreshedToken);
        setUser(refreshedUser);
      } else {
        setToken(session.accessToken);
        setUser(session.user);
        setAuth(session.accessToken, null, session.user);
      }

      await verifyApiSession();
      setIsLoading(false);
    };

    initAuth();
  }, [verifyApiSession]);

  // Login - redirect to Janua
  const login = useCallback((returnTo?: string) => {
    const loginUrl = getLoginUrl(sanitizeReturnPath(returnTo || window.location.pathname));
    window.location.href = loginUrl;
  }, []);

  // Logout - clear local state and redirect to Janua logout
  const logout = useCallback(() => {
    const logoutUrl = getLogoutUrl();
    clearAuth();
    setUser(null);
    setToken(null);
    void fetch("/api/auth/logout", {
      method: "POST",
      keepalive: true,
    })
      .catch(() => undefined)
      .finally(() => {
        window.location.href = logoutUrl;
      });
  }, []);

  // Refresh token
  const refreshToken = useCallback(async () => {
    const newToken = await refreshAccessToken();
    if (newToken) {
      setToken(newToken);
      const newUser = parseJwt(newToken);
      setUser(newUser);
      if (newUser) {
        setAuth(newToken, null, newUser);
      }
    } else {
      clearAuth();
      setUser(null);
      setToken(null);
    }
  }, []);

  // Set up token refresh interval
  useEffect(() => {
    if (!token) return;

    // Check token every 5 minutes
    const interval = setInterval(
      async () => {
        if (isTokenExpired(token)) {
          await refreshToken();
        }
      },
      5 * 60 * 1000
    );

    return () => clearInterval(interval);
  }, [token, refreshToken]);

  const value: AuthContextType = {
    user,
    isAuthenticated: !!user && !!token,
    isLoading,
    isApiAuthorized,
    token,
    login,
    logout,
    refreshToken,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/**
 * Hook to access auth context
 */
export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}

/**
 * Hook to require authentication - redirects to login if not authenticated
 */
export function useRequireAuth(redirectTo?: string): AuthContextType {
  const auth = useAuth();

  useEffect(() => {
    if (!auth.isLoading && !auth.isAuthenticated) {
      auth.login(redirectTo);
    }
  }, [auth, redirectTo]);

  return auth;
}
