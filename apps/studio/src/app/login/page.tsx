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
    <div className="min-h-screen flex flex-col bg-background">
      <div className="flex-1 flex flex-col items-center justify-center p-8">
        {/* Logo/Brand */}
        <div className="flex items-center gap-3">
          <Terminal className="h-10 w-10 text-primary" />
          <span className="text-3xl font-bold tracking-tight">ceq</span>
        </div>

        {/* Hero section */}
        <h1 className="mt-6 text-xl font-semibold text-foreground text-center">
          CEQ Studio — Generative AI Image Pipeline
        </h1>

        {/* Tagline */}
        <p className="mt-2 text-sm text-muted-foreground text-center max-w-sm">
          Creative Entropy Quantized
          <br />
          <span className="text-xs opacity-75">
            The skunkworks terminal for the generative avant-garde
          </span>
        </p>

        {/* Loading indicator */}
        <div className="flex items-center gap-2 text-muted-foreground mt-6">
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
      </div>

      {/* Footer */}
      <footer className="border-t border-border px-6 py-6">
        <div className="flex flex-col items-center gap-2">
          <p className="text-xs text-muted-foreground">
            &copy; {new Date().getFullYear()} CEQ Studio. By{" "}
            <a
              href="https://madfam.io"
              className="text-muted-foreground hover:text-foreground transition-colors"
              target="_blank"
              rel="noopener noreferrer"
            >
              Innovaciones MADFAM
            </a>
            .
          </p>
          <div className="flex items-center gap-3 text-xs text-muted-foreground/70">
            <a href="https://madfam.io/privacy" className="hover:text-foreground transition-colors">Privacy Policy</a>
            <span aria-hidden="true">&middot;</span>
            <a href="https://madfam.io/terms" className="hover:text-foreground transition-colors">Terms of Service</a>
            <span aria-hidden="true">&middot;</span>
            <a href="https://status.madfam.io" className="hover:text-foreground transition-colors">Status</a>
          </div>
          <p className="text-xs text-muted-foreground/50">
            Authenticated via{" "}
            <span className="font-medium">MADFAM Identity</span>
          </p>
        </div>
      </footer>
    </div>
  );
}
