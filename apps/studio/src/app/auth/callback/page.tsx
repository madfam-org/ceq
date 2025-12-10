"use client";

/**
 * Auth Callback Page
 *
 * Handles the OIDC callback from Janua after successful authentication.
 * Exchanges the authorization code for tokens and redirects to the app.
 */

import { useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { setAuth, parseJwt, AUTH_CONFIG } from "@/lib/auth";
import { Terminal, Loader2, AlertCircle } from "lucide-react";

export default function AuthCallbackPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState("Establishing secure connection...");

  useEffect(() => {
    const handleCallback = async () => {
      const code = searchParams.get("code");
      const state = searchParams.get("state") || "/";
      const errorParam = searchParams.get("error");
      const errorDescription = searchParams.get("error_description");

      // Handle OAuth errors
      if (errorParam) {
        setError(errorDescription || errorParam);
        return;
      }

      if (!code) {
        setError("No authorization code received. Signal lost in the noise.");
        return;
      }

      try {
        setStatus("Decrypting signal...");

        // Exchange code for tokens via our API route
        const response = await fetch("/api/auth/token", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code }),
        });

        if (!response.ok) {
          const data = await response.json();
          throw new Error(data.error || "Token exchange failed");
        }

        setStatus("Materializing session...");

        const data = await response.json();
        const user = parseJwt(data.access_token);

        if (!user) {
          throw new Error("Failed to parse user from token");
        }

        // Store auth data
        setAuth(data.access_token, data.refresh_token, user);

        setStatus("Signal acquired. Entering the terminal...");

        // Redirect to destination
        setTimeout(() => {
          router.push(state);
        }, 500);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Chaos won this round. Retry?"
        );
      }
    };

    handleCallback();
  }, [searchParams, router]);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-background">
      <div className="flex flex-col items-center gap-6 p-8">
        {/* Logo/Brand */}
        <div className="flex items-center gap-3">
          <Terminal className="h-10 w-10 text-primary" />
          <span className="text-3xl font-bold tracking-tight">ceq</span>
        </div>

        {error ? (
          <>
            {/* Error state */}
            <div className="flex items-center gap-2 text-destructive">
              <AlertCircle className="h-5 w-5" />
              <span className="text-sm font-medium">Authentication Error</span>
            </div>
            <p className="text-sm text-muted-foreground text-center max-w-sm">
              {error}
            </p>
            <button
              onClick={() => router.push("/login")}
              className="mt-4 px-6 py-2 text-sm border border-border rounded hover:bg-accent transition-colors"
            >
              Try Again
            </button>
          </>
        ) : (
          <>
            {/* Loading state */}
            <div className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span className="text-sm">{status}</span>
            </div>
          </>
        )}

        {/* Footer */}
        <p className="text-xs text-muted-foreground/50 mt-8">
          Authenticated via{" "}
          <span className="font-medium">MADFAM Identity</span>
        </p>
      </div>
    </div>
  );
}
