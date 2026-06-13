"use client";

import { useEffect, type ReactNode } from "react";
import { AlertCircle } from "lucide-react";
import { Sidebar } from "./sidebar";
import { CommandPalette } from "../command-palette";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/contexts/auth-context";

interface MainLayoutProps {
  children: ReactNode;
}

export function MainLayout({ children }: MainLayoutProps) {
  const { isAuthenticated, isLoading, isApiAuthorized, login } = useAuth();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      const returnTo = `${window.location.pathname}${window.location.search}`;
      login(returnTo);
    }
  }, [isAuthenticated, isLoading, login]);

  if (isLoading || !isAuthenticated) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="font-mono text-sm text-muted-foreground">
          <span className="text-primary">›</span>{" "}
          {isLoading ? "validating session…" : "redirecting to Janua…"}
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col">
      {isApiAuthorized === false ? (
        <div className="border-b border-destructive/30 bg-destructive/10 px-4 py-3">
          <div className="ml-16 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-start gap-3 text-sm">
              <AlertCircle className="h-4 w-4 mt-0.5 text-destructive shrink-0" />
              <p className="text-muted-foreground">
                Janua login succeeded, but CEQ API rejected the session token.
                Workflows, queue, billing, and job submission stay offline until
                API auth is restored. If you opened an old Janua sign-in link,
                return to{" "}
                <a href="/login" className="underline text-foreground">
                  app.ceq.lol/login
                </a>{" "}
                and sign in again.
              </p>
            </div>
            <Button size="sm" variant="outline" onClick={() => login()}>
              Sign in again
            </Button>
          </div>
        </div>
      ) : null}

      <div className="flex flex-1 min-h-0">
      {/* Sidebar */}
      <Sidebar />

      {/* Main content */}
      <main className="flex-1 ml-16 pb-10">
        {children}
      </main>

      {/* Command palette (⌘K) */}
      <CommandPalette />
      </div>
    </div>
  );
}
