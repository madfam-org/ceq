/** Tone-beep audio template input. All fields optional — defaults produce an 880Hz / 200ms gentle chime. */
export interface ToneBeepData {
  /** Sine wave frequency in Hz. Clamped to [20, 20000]. Default 880. */
  frequency_hz?: number;
  /** Tone duration in milliseconds. Clamped to [10, 5000]. Default 200. */
  duration_ms?: number;
  /** Amplitude envelope shape. Default "adsr-gentle". */
  envelope?: "adsr-gentle" | "adsr-sharp" | "linear" | "square";
  /** Peak amplitude in [0.0, 1.0]. Default 0.5. */
  volume?: number;
}

/** Card-plate 3D template input. Dimensions in millimeters. All fields optional — defaults are standard trading-card dimensions. */
export interface CardPlateData {
  /** Plate width in mm. Clamped to [10, 300]. Default 63.5 (standard card). */
  width_mm?: number;
  /** Plate height in mm. Clamped to [10, 300]. Default 88.9 (standard card). */
  height_mm?: number;
  /** Plate thickness in mm. Clamped to [0.5, 20]. Default 2.0. */
  thickness_mm?: number;
  /** Corner radius in mm. Clamped to [0, 20]; further reduced to min(width,height)/2. Default 4.0. */
  corner_radius_mm?: number;
  /** PBR baseColorFactor as hex (#RRGGBB or #RGB). Default "#3C8CFF". */
  accent_hex?: string;
}

/** Card template input. All fields except `title` are optional. */
export interface CardData {
  /** Card title — required. Rendered large at the top. */
  title: string;
  /** Short classifier shown under the title (e.g. "Elemental / Fire"). */
  subtitle?: string;
  /** Longer description wrapped at the bottom of the card. */
  description?: string;
  /** Hex color (#RRGGBB or #RGB) used for gradient, frame, and accents. */
  accent?: string;
  /** Single-char glyph rendered large in the center (emoji, letter, rune). */
  glyph?: string;
  /** Short rarity / tier badge ("R", "SR", "★★★") rendered in the top-right. */
  badge?: string;
}

/** Generic render request shape (matches the API 1:1). */
export interface RenderRequest<TData = Record<string, unknown>> {
  template: string;
  data: TData;
}

/** Render response — identical for cache hit and miss. */
export interface RenderResponse {
  /** Public URL for the rendered asset. Immutable (content-addressed). */
  url: string;
  /** Internal R2 URI (r2://bucket/key). */
  storage_uri: string;
  /** Deterministic input hash (sha256 hex). Same input → same hash → same URL. */
  hash: string;
  template: string;
  template_version: string;
  content_type: string;
  /** True if served from R2 cache (no re-render happened). */
  cached: boolean;
}

export interface TemplateInfo {
  name: string;
  version: string;
  content_type: string;
  extension: string;
}

/** Thrown when the API returns a non-2xx response. */
export class CeqApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
    public readonly response?: Response
  ) {
    super(`ceq api ${status}: ${detail}`);
    this.name = "CeqApiError";
  }
}
