"use client";

import { useEffect, type ReactNode } from "react";
import { Sidebar } from "./sidebar";
import { CommandPalette } from "../command-palette";
import { useAuth } from "@/contexts/auth-context";

interface MainLayoutProps {
  children: ReactNode;
}

export function MainLayout({ children }: MainLayoutProps) {
  const { isAuthenticated, isLoading, login } = useAuth();

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
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <Sidebar />

      {/* Main content */}
      <main className="flex-1 ml-16 pb-10">
        {children}
      </main>

      {/* Command palette (⌘K) */}
      <CommandPalette />
    </div>
  );
}
