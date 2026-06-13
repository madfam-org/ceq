export interface MockJwtClaims {
  sub?: string;
  email?: string;
  name?: string;
  picture?: string;
  aud?: string;
  exp?: number;
}

function base64Url(value: object): string {
  return Buffer.from(JSON.stringify(value))
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

/** Build an unsigned JWT suitable for Studio session/bootstrap tests. */
export function createMockJwt(claims: MockJwtClaims): string {
  const header = base64Url({ alg: "none", typ: "JWT" });
  const payload = base64Url({
    sub: "user-e2e-1",
    email: "studio-e2e@madfam.io",
    name: "Studio E2E",
    aud: "ceq-api",
    exp: Math.floor(Date.now() / 1000) + 3600,
    ...claims,
  });
  return `${header}.${payload}.sig`;
}

export function expiredMockJwt(): string {
  return createMockJwt({
    exp: Math.floor(Date.now() / 1000) - 3600,
  });
}

export function freshMockJwt(): string {
  return createMockJwt({
    exp: Math.floor(Date.now() / 1000) + 3600,
  });
}
