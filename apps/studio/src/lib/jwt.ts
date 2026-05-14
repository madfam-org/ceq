import type { User } from "@/lib/auth";

type JwtPayload = Record<string, unknown>;

function decodeBase64Url(value: string): string {
  const base64 = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), "=");
  return globalThis.atob(padded);
}

export function decodeJwtPayload(token: string): JwtPayload | null {
  try {
    const [, payload] = token.split(".");
    if (!payload) return null;
    return JSON.parse(decodeBase64Url(payload)) as JwtPayload;
  } catch {
    return null;
  }
}

function asString(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

export function parseJwtUser(token: string): User | null {
  const payload = decodeJwtPayload(token);
  if (!payload) return null;

  const id = asString(payload.sub) || asString(payload.id);
  const email = asString(payload.email);

  if (!id || !email) return null;

  return {
    id,
    email,
    name: asString(payload.name) || email.split("@")[0],
    avatar: asString(payload.picture) || asString(payload.avatar),
  };
}

export function isJwtExpired(token: string, skewMs = 60_000): boolean {
  const payload = decodeJwtPayload(token);
  const exp = typeof payload?.exp === "number" ? payload.exp * 1000 : null;
  if (!exp) return true;
  return Date.now() >= exp - skewMs;
}
