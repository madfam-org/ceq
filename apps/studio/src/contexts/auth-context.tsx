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
  getToken,
  getStoredUser,
  setAuth,
  clearAuth,
  isTokenExpired,
  refreshAccessToken,
  getLoginUrl,
  getLogoutUrl,
  parseJwt,
} from "@/lib/auth";

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
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

  // Initialize auth state from storage
  useEffect(() => {
    const initAuth = async () => {
      const storedToken = getToken();
      const storedUser = getStoredUser();

      if (storedToken && storedUser) {
        // Check if token is expired
        if (isTokenExpired(storedToken)) {
          // Try to refresh
          const newToken = await refreshAccessToken();
          if (newToken) {
            setToken(newToken);
            const newUser = parseJwt(newToken);
            setUser(newUser);
          } else {
            clearAuth();
          }
        } else {
          setToken(storedToken);
          setUser(storedUser);
        }
      }

      setIsLoading(false);
    };

    initAuth();
  }, []);

  // Login - redirect to Janua
  const login = useCallback((returnTo?: string) => {
    const loginUrl = getLoginUrl(returnTo || window.location.pathname);
    window.location.href = loginUrl;
  }, []);

  // Logout - clear local state and redirect to Janua logout
  const logout = useCallback(() => {
    clearAuth();
    setUser(null);
    setToken(null);
    window.location.href = getLogoutUrl();
  }, []);

  // Refresh token
  const refreshToken = useCallback(async () => {
    const newToken = await refreshAccessToken();
    if (newToken) {
      setToken(newToken);
      const newUser = parseJwt(newToken);
      setUser(newUser);
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
