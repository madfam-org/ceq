"use client";

/**
 * User Menu Component
 *
 * Displays user avatar with dropdown menu for profile and logout.
 * Shows login button when not authenticated.
 */

import { User, LogOut, Settings, Terminal } from "lucide-react";
import { useAuth } from "@/contexts/auth-context";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

export function UserMenu() {
  const { user, isAuthenticated, isLoading, login, logout } = useAuth();

  // Loading state
  if (isLoading) {
    return (
      <div className="flex h-10 w-10 items-center justify-center mx-auto">
        <Skeleton className="h-8 w-8 rounded-full" />
      </div>
    );
  }

  // Not authenticated - show login button
  if (!isAuthenticated || !user) {
    return (
      <Tooltip delayDuration={0}>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => login()}
            className="h-10 w-10 mx-auto text-muted-foreground hover:text-foreground"
          >
            <User className="h-5 w-5" />
          </Button>
        </TooltipTrigger>
        <TooltipContent side="right">Sign in</TooltipContent>
      </Tooltip>
    );
  }

  // Get initials for avatar fallback
  const initials = user.name
    ? user.name
        .split(" ")
        .map((n) => n[0])
        .join("")
        .toUpperCase()
        .slice(0, 2)
    : user.email.slice(0, 2).toUpperCase();

  return (
    <DropdownMenu>
      <Tooltip delayDuration={0}>
        <TooltipTrigger asChild>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="h-10 w-10 mx-auto rounded-full p-0"
            >
              <Avatar className="h-8 w-8">
                {user.avatar && <AvatarImage src={user.avatar} alt={user.name || user.email} />}
                <AvatarFallback className="text-xs bg-primary text-primary-foreground">
                  {initials}
                </AvatarFallback>
              </Avatar>
            </Button>
          </DropdownMenuTrigger>
        </TooltipTrigger>
        <TooltipContent side="right">Account</TooltipContent>
      </Tooltip>

      <DropdownMenuContent side="right" align="end" className="w-56">
        <DropdownMenuLabel className="font-normal">
          <div className="flex flex-col space-y-1">
            {user.name && (
              <p className="text-sm font-medium leading-none">{user.name}</p>
            )}
            <p className="text-xs leading-none text-muted-foreground">
              {user.email}
            </p>
          </div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />

        <DropdownMenuItem className="cursor-pointer" disabled>
          <Settings className="mr-2 h-4 w-4" />
          <span>Preferences</span>
        </DropdownMenuItem>

        <DropdownMenuItem className="cursor-pointer" disabled>
          <Terminal className="mr-2 h-4 w-4" />
          <span>API Keys</span>
        </DropdownMenuItem>

        <DropdownMenuSeparator />

        <DropdownMenuItem
          className="cursor-pointer text-destructive focus:text-destructive"
          onClick={logout}
        >
          <LogOut className="mr-2 h-4 w-4" />
          <span>Sign out</span>
        </DropdownMenuItem>

        <DropdownMenuSeparator />
        <div className="px-2 py-1.5">
          <p className="text-xs text-muted-foreground/70">
            via MADFAM Identity
          </p>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
