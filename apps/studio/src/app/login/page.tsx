"use client";

/**
 * Login Page
 *
 * Redirects to Janua for authentication via OIDC flow.
 */

import { useEffect } from "react";
import { useAuth } from "@/contexts/auth-context";
import { useSearchParams } from "next/navigation";
import { Terminal, Loader2 } from "lucide-react";

export default function LoginPage() {
  const { isAuthenticated, isLoading, login } = useAuth();
  const searchParams = useSearchParams();
  const returnTo = searchParams.get("returnTo") || "/";

  useEffect(() => {
    // If already authenticated, redirect to return destination
    if (!isLoading && isAuthenticated) {
      window.location.href = returnTo;
      return;
    }

    // Auto-redirect to Janua login after brief display
    if (!isLoading && !isAuthenticated) {
      const timer = setTimeout(() => {
        login(returnTo);
      }, 1500);
      return () => clearTimeout(timer);
    }
  }, [isAuthenticated, isLoading, login, returnTo]);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-background">
      <div className="flex flex-col items-center gap-6 p-8">
        {/* Logo/Brand */}
        <div className="flex items-center gap-3">
          <Terminal className="h-10 w-10 text-primary" />
          <span className="text-3xl font-bold tracking-tight">ceq</span>
        </div>

        {/* Tagline */}
        <p className="text-sm text-muted-foreground text-center max-w-sm">
          Creative Entropy Quantized
          <br />
          <span className="text-xs opacity-75">
            The skunkworks terminal for the generative avant-garde
          </span>
        </p>

        {/* Loading indicator */}
        <div className="flex items-center gap-2 text-muted-foreground mt-4">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span className="text-sm">Initiating secure channel...</span>
        </div>

        {/* Manual login button (fallback) */}
        <button
          onClick={() => login(returnTo)}
          className="mt-8 px-6 py-2 text-sm border border-border rounded hover:bg-accent transition-colors"
        >
          Enter the Terminal
        </button>

        {/* Footer */}
        <p className="text-xs text-muted-foreground/50 mt-8">
          Authenticated via{" "}
          <span className="font-medium">MADFAM Identity</span>
        </p>
      </div>
    </div>
  );
}
