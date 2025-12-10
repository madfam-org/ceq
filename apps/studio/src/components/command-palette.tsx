"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import {
  Workflow,
  Image,
  Video,
  Box,
  Settings,
  FolderOpen,
  Clock,
  Sparkles,
  Plus,
  Play,
  Search,
} from "lucide-react";

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const router = useRouter();

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((open) => !open);
      }

      // Number shortcuts for navigation
      if (e.metaKey || e.ctrlKey) {
        switch (e.key) {
          case "1":
            e.preventDefault();
            router.push("/");
            break;
          case "2":
            e.preventDefault();
            router.push("/workflows");
            break;
          case "3":
            e.preventDefault();
            router.push("/templates");
            break;
          case "4":
            e.preventDefault();
            router.push("/gallery");
            break;
          case "5":
            e.preventDefault();
            router.push("/queue");
            break;
        }
      }
    };

    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, [router]);

  const runCommand = (command: () => void) => {
    setOpen(false);
    command();
  };

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput placeholder="Seek the signal..." />
      <CommandList>
        <CommandEmpty>No signal found in the noise.</CommandEmpty>

        <CommandGroup heading="Actions">
          <CommandItem
            onSelect={() => runCommand(() => router.push("/workflows/new"))}
          >
            <Plus className="mr-2 h-4 w-4" />
            <span>New Workflow</span>
            <span className="ml-auto text-xs text-muted-foreground">⌘N</span>
          </CommandItem>
          <CommandItem
            onSelect={() => runCommand(() => console.log("Run last workflow"))}
          >
            <Play className="mr-2 h-4 w-4" />
            <span>Run Last Workflow</span>
            <span className="ml-auto text-xs text-muted-foreground">⌘↵</span>
          </CommandItem>
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading="Navigate">
          <CommandItem onSelect={() => runCommand(() => router.push("/"))}>
            <Sparkles className="mr-2 h-4 w-4" />
            <span>Dashboard</span>
            <span className="ml-auto text-xs text-muted-foreground">⌘1</span>
          </CommandItem>
          <CommandItem
            onSelect={() => runCommand(() => router.push("/workflows"))}
          >
            <Workflow className="mr-2 h-4 w-4" />
            <span>Workflows</span>
            <span className="ml-auto text-xs text-muted-foreground">⌘2</span>
          </CommandItem>
          <CommandItem
            onSelect={() => runCommand(() => router.push("/templates"))}
          >
            <FolderOpen className="mr-2 h-4 w-4" />
            <span>Templates</span>
            <span className="ml-auto text-xs text-muted-foreground">⌘3</span>
          </CommandItem>
          <CommandItem
            onSelect={() => runCommand(() => router.push("/gallery"))}
          >
            <Image className="mr-2 h-4 w-4" />
            <span>Gallery</span>
            <span className="ml-auto text-xs text-muted-foreground">⌘4</span>
          </CommandItem>
          <CommandItem onSelect={() => runCommand(() => router.push("/queue"))}>
            <Clock className="mr-2 h-4 w-4" />
            <span>Queue</span>
            <span className="ml-auto text-xs text-muted-foreground">⌘5</span>
          </CommandItem>
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading="Templates">
          <CommandItem
            onSelect={() => runCommand(() => router.push("/templates/social"))}
          >
            <Image className="mr-2 h-4 w-4" />
            <span>Social Media</span>
          </CommandItem>
          <CommandItem
            onSelect={() => runCommand(() => router.push("/templates/video"))}
          >
            <Video className="mr-2 h-4 w-4" />
            <span>Video Clone</span>
          </CommandItem>
          <CommandItem
            onSelect={() => runCommand(() => router.push("/templates/3d"))}
          >
            <Box className="mr-2 h-4 w-4" />
            <span>3D Render</span>
          </CommandItem>
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading="Settings">
          <CommandItem
            onSelect={() => runCommand(() => router.push("/settings"))}
          >
            <Settings className="mr-2 h-4 w-4" />
            <span>Settings</span>
            <span className="ml-auto text-xs text-muted-foreground">⌘,</span>
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
