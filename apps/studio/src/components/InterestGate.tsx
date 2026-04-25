"use client";

/**
 * InterestGate — pre-monetization "email capture instead of paywall".
 *
 * Wrap any Pro feature with <InterestGate featureKey="..." variant="overlay">
 * so free users see an email-capture form instead of a 403. When real billing
 * arrives, swap the overlay for a checkout flow; the captured emails become
 * the warm waitlist.
 *
 * Variants:
 *   - inline   : compact banner, fits inline with surrounding content.
 *   - overlay  : blurred backdrop over wrapped children (use to gate a Pro card).
 *   - card     : standalone announcement card with optional benefits list.
 *   - toast    : fixed bottom-right slide-in (good for "tried to use Pro" hints).
 *
 * Backend contract: POST /v1/interest/ -> 201 (new) | 200 (already_registered) | 4xx.
 * See `apps/api/src/ceq_api/routers/interest.py`.
 */

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Bell, Check, Loader2, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/contexts/auth-context";
import { cn } from "@/lib/utils";
import { getFeatureLabel, type Lang } from "@/lib/feature-labels";

type Variant = "inline" | "overlay" | "card" | "toast";
type SubmitState = "idle" | "submitting" | "success" | "already_registered" | "error";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5800";

const COPY: Record<Lang, {
  comingSoon: string;
  notifyMe: string;
  submit: string;
  success: string;
  alreadyRegistered: string;
  error: string;
  emailPlaceholder: string;
  wishlistPlaceholder: string;
  wishlistAria: string;
  dismiss: string;
}> = {
  en: {
    comingSoon: "Coming soon",
    notifyMe: "Drop your email and we'll let you know.",
    submit: "Notify me",
    success: "Done. We'll be in touch.",
    alreadyRegistered: "You're already on the list.",
    error: "Couldn't register that. Try again?",
    emailPlaceholder: "you@email.com",
    wishlistPlaceholder: "What would unlock this for you?",
    wishlistAria: "Wishlist",
    dismiss: "Dismiss",
  },
  es: {
    comingSoon: "Disponible pronto",
    notifyMe: "Déjanos tu correo y te avisamos.",
    submit: "Avísame",
    success: "Listo. Te avisaremos.",
    alreadyRegistered: "Ya estás en la lista.",
    error: "No pudimos registrarlo. ¿Intentas otra vez?",
    emailPlaceholder: "tu@correo.com",
    wishlistPlaceholder: "¿Qué desbloquearía esto para ti?",
    wishlistAria: "Lista de deseos",
    dismiss: "Cerrar",
  },
};

export interface InterestGateProps {
  /** Feature identifier — must match `ALLOWED_FEATURES` server-side. */
  featureKey: string;
  /** Visual variant. `overlay` wraps `children` with a blur backdrop. */
  variant?: Variant;
  /** Override the auto-resolved feature label. */
  featureLabel?: string;
  /** Bullet list rendered in the `card` variant. */
  benefits?: string[];
  /** Show the wishlist textarea (only in `card` and `overlay`). */
  showWishlist?: boolean;
  /** Free-text page identifier sent to the backend (helps WTP analysis). */
  sourcePage?: string;
  /** Language for copy. Defaults to `en`. */
  lang?: Lang;
  /** Wrapped content — only used by the `overlay` variant. */
  children?: ReactNode;
  /** Optional CSS class for the wrapper. */
  className?: string;
  /** Called after a successful submit (new or duplicate). */
  onSubmitted?: () => void;
}

export function InterestGate({
  featureKey,
  variant = "inline",
  featureLabel,
  benefits,
  showWishlist = false,
  sourcePage = "",
  lang = "en",
  children,
  className,
  onSubmitted,
}: InterestGateProps) {
  const t = COPY[lang];
  const auth = useAuth();
  const userEmail = auth.user?.email ?? "";
  const userId = auth.user?.id ?? "";

  const [email, setEmail] = useState(userEmail);
  const [wishlist, setWishlist] = useState("");
  const [state, setState] = useState<SubmitState>("idle");
  const [dismissed, setDismissed] = useState(false);

  // Sync email from auth once it loads.
  useEffect(() => {
    if (userEmail && !email) setEmail(userEmail);
  }, [userEmail, email]);

  const label = useMemo(
    () => featureLabel ?? getFeatureLabel(featureKey, lang),
    [featureLabel, featureKey, lang]
  );

  const isComplete = state === "success" || state === "already_registered";
  const successMessage =
    state === "already_registered" ? t.alreadyRegistered : t.success;

  if (dismissed && variant === "toast") return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || state === "submitting") return;

    setState("submitting");

    let res: Response | null = null;
    try {
      res = await fetch(`${API_BASE}/v1/interest/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          feature_key: featureKey,
          wishlist: wishlist.trim() || null,
          janua_user_id: userId || null,
          source_page: sourcePage || null,
        }),
      });
    } catch {
      setState("error");
      return;
    }

    if (res.status === 201) {
      setState("success");
      onSubmitted?.();
    } else if (res.status === 200) {
      setState("already_registered");
      onSubmitted?.();
    } else {
      setState("error");
    }
  };

  // ---- Shared form pieces ----

  const emailInput = (
    <Input
      type="email"
      value={email}
      onChange={(e) => setEmail(e.target.value)}
      placeholder={t.emailPlaceholder}
      required
      className="flex-1 min-w-0"
      aria-label="Email"
    />
  );

  const wishlistTextarea =
    showWishlist && (variant === "card" || variant === "overlay") ? (
      <Textarea
        value={wishlist}
        onChange={(e) => setWishlist(e.target.value)}
        placeholder={t.wishlistPlaceholder}
        maxLength={2000}
        rows={2}
        className="w-full"
        aria-label={t.wishlistAria}
      />
    ) : null;

  const submitButton = (
    <Button
      type="submit"
      size="sm"
      disabled={state === "submitting" || !email}
      className="gap-1 shrink-0"
    >
      {state === "submitting" ? (
        <Loader2 className="h-3 w-3 animate-spin" />
      ) : (
        <Bell className="h-3 w-3" />
      )}
      {t.submit}
    </Button>
  );

  // ---- Variants ----

  if (variant === "toast") {
    return (
      <div
        className={cn(
          "fixed bottom-4 right-4 z-50 max-w-[min(24rem,calc(100vw-2rem))]",
          className
        )}
        role="status"
      >
        <Card className="border-primary/30 shadow-lg">
          <CardContent className="p-4">
            <div className="flex items-start gap-3">
              <div className="rounded-full bg-primary/10 p-2 shrink-0">
                <Bell className="h-4 w-4 text-primary" />
              </div>
              <div className="flex-1 min-w-0">
                <Badge variant="outline" className="text-xs mb-1">
                  {t.comingSoon}
                </Badge>
                <p className="text-sm font-medium mb-2">{label}</p>
                {isComplete ? (
                  <div className="flex items-center gap-1.5 text-sm text-primary">
                    <Check className="h-3.5 w-3.5" />
                    {successMessage}
                  </div>
                ) : (
                  <form onSubmit={handleSubmit} className="flex gap-2">
                    {emailInput}
                    {submitButton}
                  </form>
                )}
                {state === "error" && (
                  <p className="text-xs text-destructive mt-1">{t.error}</p>
                )}
              </div>
              <button
                type="button"
                onClick={() => setDismissed(true)}
                className="text-muted-foreground hover:text-foreground shrink-0 p-1.5"
                aria-label={t.dismiss}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (variant === "inline") {
    return (
      <div
        className={cn(
          "rounded-lg border border-primary/20 bg-gradient-to-r from-primary/5 to-primary/10 p-4",
          className
        )}
      >
        <div className="flex items-center gap-2 mb-2">
          <Bell className="h-4 w-4 text-primary shrink-0" />
          <Badge variant="outline" className="text-xs">
            {t.comingSoon}
          </Badge>
          <span className="text-sm font-medium">{label}</span>
        </div>
        {isComplete ? (
          <div className="flex items-center gap-1.5 text-sm text-primary">
            <Check className="h-3.5 w-3.5" />
            {successMessage}
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="flex flex-col sm:flex-row gap-2">
            {emailInput}
            {submitButton}
          </form>
        )}
        {state === "error" && (
          <p className="text-xs text-destructive mt-1">{t.error}</p>
        )}
      </div>
    );
  }

  if (variant === "card") {
    return (
      <Card className={cn("border-primary/20 overflow-hidden relative", className)}>
        <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-transparent to-primary/10 pointer-events-none" />
        <CardContent className="relative p-6 sm:p-8 text-center">
          <div className="mx-auto rounded-full bg-primary/10 p-3 w-fit mb-4">
            <Bell className="h-6 w-6 text-primary" />
          </div>
          <Badge variant="outline" className="text-xs mb-3">
            {t.comingSoon}
          </Badge>
          <h3 className="text-lg font-bold mb-2">{label}</h3>
          <p className="text-sm text-muted-foreground mb-4 max-w-md mx-auto">
            {t.notifyMe}
          </p>

          {benefits && benefits.length > 0 && (
            <ul className="text-sm text-left max-w-xs mx-auto space-y-1.5 mb-5">
              {benefits.map((b, i) => (
                <li key={i} className="flex items-start gap-2">
                  <span className="text-primary mt-0.5">✓</span>
                  <span className="text-muted-foreground">{b}</span>
                </li>
              ))}
            </ul>
          )}

          {isComplete ? (
            <div className="flex items-center justify-center gap-1.5 text-sm text-primary">
              <Check className="h-4 w-4" />
              {successMessage}
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="max-w-sm mx-auto space-y-3">
              {emailInput}
              {wishlistTextarea}
              {submitButton}
            </form>
          )}
          {state === "error" && (
            <p className="text-xs text-destructive mt-2">{t.error}</p>
          )}
        </CardContent>
      </Card>
    );
  }

  // variant === "overlay"
  return (
    <div className={cn("relative rounded-lg overflow-hidden", className)}>
      {/* Render wrapped content underneath, blurred */}
      {children ? (
        <div aria-hidden="true" className="pointer-events-none">
          {children}
        </div>
      ) : null}

      <div className="absolute inset-0 bg-background/80 backdrop-blur-sm z-10 flex items-center justify-center">
        <div className="text-center p-6 max-w-sm">
          <div className="mx-auto rounded-full bg-primary/10 p-3 w-fit mb-3">
            <Bell className="h-5 w-5 text-primary" />
          </div>
          <Badge variant="outline" className="text-xs mb-2">
            {t.comingSoon}
          </Badge>
          <h3 className="text-base font-bold mb-1">{label}</h3>
          <p className="text-sm text-muted-foreground mb-4">{t.notifyMe}</p>
          {isComplete ? (
            <div className="flex items-center justify-center gap-1.5 text-sm text-primary">
              <Check className="h-4 w-4" />
              {successMessage}
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-2">
              {emailInput}
              {wishlistTextarea}
              {submitButton}
            </form>
          )}
          {state === "error" && (
            <p className="text-xs text-destructive mt-1">{t.error}</p>
          )}
        </div>
      </div>
    </div>
  );
}

export default InterestGate;
