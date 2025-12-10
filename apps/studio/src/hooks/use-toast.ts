"use client";

/**
 * use-toast hook
 *
 * Wraps sonner toast API to provide useToast pattern compatible with shadcn/ui.
 */

import { toast as sonnerToast } from "sonner";

interface ToastProps {
  title?: string;
  description?: string;
  variant?: "default" | "destructive";
}

export function useToast() {
  const toast = ({ title, description, variant }: ToastProps) => {
    if (variant === "destructive") {
      sonnerToast.error(title, {
        description,
      });
    } else {
      sonnerToast(title, {
        description,
      });
    }
  };

  return { toast };
}

export { sonnerToast as toast };
