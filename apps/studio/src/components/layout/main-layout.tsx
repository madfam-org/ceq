"use client";

import { type ReactNode } from "react";
import { Sidebar } from "./sidebar";
import { CommandPalette } from "../command-palette";

interface MainLayoutProps {
  children: ReactNode;
}

export function MainLayout({ children }: MainLayoutProps) {
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
