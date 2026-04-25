/**
 * Feature key → i18n display labels for InterestGate.
 *
 * Keep keys in sync with `ALLOWED_FEATURES` in
 * `apps/api/src/ceq_api/routers/interest.py` — submitting an unknown key
 * will fail validation server-side.
 */

export type Lang = "en" | "es";

export type FeatureKey =
  | "premium_render"
  | "training_access"
  | "team_seats"
  | "early_access";

export const FEATURE_LABELS: Record<FeatureKey, Record<Lang, string>> = {
  premium_render: {
    en: "Premium templates",
    es: "Plantillas premium",
  },
  training_access: {
    en: "Custom model training",
    es: "Entrenamiento de modelos a medida",
  },
  team_seats: {
    en: "Team seats and collaboration",
    es: "Asientos de equipo y colaboración",
  },
  early_access: {
    en: "Early access",
    es: "Acceso anticipado",
  },
};

export function getFeatureLabel(featureKey: string, lang: Lang = "en"): string {
  const entry = FEATURE_LABELS[featureKey as FeatureKey];
  if (!entry) return featureKey;
  return entry[lang] ?? entry.en ?? featureKey;
}
