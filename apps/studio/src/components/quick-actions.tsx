"use client";

import { Plus, Play, Command } from "lucide-react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

export function QuickActions() {
  const router = useRouter();

  const openCommandPalette = () => {
    window.dispatchEvent(new Event("ceq:open-command-palette"));
  };

  return (
    <TooltipProvider>
      <div className="flex items-center gap-2">
        {/* Command palette hint */}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="outline"
              size="sm"
              className="gap-2 text-muted-foreground"
              onClick={openCommandPalette}
            >
              <Command className="h-3 w-3" />
              <span className="text-xs">K</span>
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            Open command palette
          </TooltipContent>
        </Tooltip>

        {/* Run last */}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="outline" size="sm" className="gap-2">
              <Play className="h-4 w-4" />
              <span className="hidden sm:inline">Run Last</span>
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            Run last workflow (⌘↵)
          </TooltipContent>
        </Tooltip>

        {/* New workflow */}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              size="sm"
              className="gap-2"
              onClick={() => router.push("/templates")}
            >
              <Plus className="h-4 w-4" />
              <span className="hidden sm:inline">New</span>
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            Create new workflow (⌘N)
          </TooltipContent>
        </Tooltip>
      </div>
    </TooltipProvider>
  );
}
