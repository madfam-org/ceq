"use client";

import { ArrowRight, Sparkles, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/contexts/auth-context";
import {
  DEMO_SIGNUP_RETURN_TO,
  startSignIn,
  trackLandingEvent,
} from "@/lib/landing-demo";

interface ConversionCtaBarProps {
  visible: boolean;
  onDismiss?: () => void;
}

export function ConversionCtaBar({ visible, onDismiss }: ConversionCtaBarProps) {
  const { login } = useAuth();

  if (!visible) return null;

  return (
    <div className="fixed bottom-0 left-0 right-0 z-40 border-t border-primary/30 bg-background/95 px-4 py-3 shadow-lg backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 sm:flex-row">
        <div className="flex items-center gap-3 text-center sm:text-left">
          <Sparkles className="hidden h-5 w-5 shrink-0 text-primary sm:block" />
          <div>
            <p className="font-mono text-sm font-semibold">
              You saw the render loop — ship your first workflow free.
            </p>
            <p className="text-xs text-muted-foreground">
              100 credits · no card · founding pricing still open
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            className="font-mono"
            onClick={() => {
              trackLandingEvent("sticky_cta_signup");
              startSignIn(DEMO_SIGNUP_RETURN_TO, login);
            }}
          >
            Start generating free
            <ArrowRight className="ml-2 h-3.5 w-3.5" />
          </Button>
          {onDismiss && (
            <Button
              size="icon"
              variant="ghost"
              className="h-8 w-8 shrink-0"
              aria-label="Dismiss"
              onClick={() => {
                trackLandingEvent("sticky_cta_dismiss");
                onDismiss();
              }}
            >
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
