"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Workflow,
  Image,
  Video,
  Box,
  Settings,
  FolderOpen,
  Clock,
  Sparkles,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

const navItems = [
  { href: "/", icon: Sparkles, label: "Dashboard", shortcut: "⌘1" },
  { href: "/workflows", icon: Workflow, label: "Workflows", shortcut: "⌘2" },
  { href: "/templates", icon: FolderOpen, label: "Templates", shortcut: "⌘3" },
  { href: "/gallery", icon: Image, label: "Gallery", shortcut: "⌘4" },
  { href: "/queue", icon: Clock, label: "Queue", shortcut: "⌘5" },
];

const categoryItems = [
  { href: "/templates/social", icon: Image, label: "Social Media" },
  { href: "/templates/video", icon: Video, label: "Video Clone" },
  { href: "/templates/3d", icon: Box, label: "3D Render" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <TooltipProvider>
      <aside className="fixed left-0 top-0 z-40 h-screen w-16 bg-card border-r border-border flex flex-col">
        {/* Logo */}
        <div className="flex h-16 items-center justify-center border-b border-border">
          <Link href="/" className="text-xl font-bold gradient-text">
            ⚡
          </Link>
        </div>

        {/* Main nav */}
        <nav className="flex-1 flex flex-col gap-1 p-2">
          {navItems.map((item) => {
            const isActive = pathname === item.href;
            return (
              <Tooltip key={item.href} delayDuration={0}>
                <TooltipTrigger asChild>
                  <Link
                    href={item.href}
                    className={cn(
                      "flex h-10 w-10 items-center justify-center rounded-md transition-colors mx-auto",
                      isActive
                        ? "bg-primary text-primary-foreground"
                        : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                    )}
                  >
                    <item.icon className="h-5 w-5" />
                  </Link>
                </TooltipTrigger>
                <TooltipContent side="right" className="flex items-center gap-2">
                  {item.label}
                  <span className="text-xs text-muted-foreground">
                    {item.shortcut}
                  </span>
                </TooltipContent>
              </Tooltip>
            );
          })}

          {/* Divider */}
          <div className="my-2 mx-2 border-t border-border" />

          {/* Category shortcuts */}
          {categoryItems.map((item) => {
            const isActive = pathname === item.href;
            return (
              <Tooltip key={item.href} delayDuration={0}>
                <TooltipTrigger asChild>
                  <Link
                    href={item.href}
                    className={cn(
                      "flex h-10 w-10 items-center justify-center rounded-md transition-colors mx-auto",
                      isActive
                        ? "bg-secondary text-secondary-foreground"
                        : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                    )}
                  >
                    <item.icon className="h-4 w-4" />
                  </Link>
                </TooltipTrigger>
                <TooltipContent side="right">
                  {item.label}
                </TooltipContent>
              </Tooltip>
            );
          })}
        </nav>

        {/* Settings */}
        <div className="p-2 border-t border-border">
          <Tooltip delayDuration={0}>
            <TooltipTrigger asChild>
              <Link
                href="/settings"
                className="flex h-10 w-10 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors mx-auto"
              >
                <Settings className="h-5 w-5" />
              </Link>
            </TooltipTrigger>
            <TooltipContent side="right">
              Settings <span className="text-xs text-muted-foreground">⌘,</span>
            </TooltipContent>
          </Tooltip>
        </div>
      </aside>
    </TooltipProvider>
  );
}
