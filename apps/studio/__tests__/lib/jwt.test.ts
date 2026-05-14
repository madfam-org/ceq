import { describe, expect, it } from "vitest";
import { decodeJwtPayload, isJwtExpired, parseJwtUser } from "@/lib/jwt";

function base64Url(value: object): string {
  return btoa(JSON.stringify(value))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

function createJwt(payload: object): string {
  return `${base64Url({ alg: "none", typ: "JWT" })}.${base64Url(payload)}.sig`;
}

describe("JWT helpers", () => {
  it("decodes a JWT payload", () => {
    const token = createJwt({ sub: "user-1", email: "ada@example.com" });

    expect(decodeJwtPayload(token)).toMatchObject({
      sub: "user-1",
      email: "ada@example.com",
    });
  });

  it("parses a CEQ user from Janua claims", () => {
    const token = createJwt({
      sub: "user-1",
      email: "ada@example.com",
      name: "Ada Lovelace",
      picture: "https://example.com/ada.png",
    });

    expect(parseJwtUser(token)).toEqual({
      id: "user-1",
      email: "ada@example.com",
      name: "Ada Lovelace",
      avatar: "https://example.com/ada.png",
    });
  });

  it("rejects payloads without a stable user identity", () => {
    expect(parseJwtUser(createJwt({ email: "ada@example.com" }))).toBeNull();
    expect(parseJwtUser(createJwt({ sub: "user-1" }))).toBeNull();
  });

  it("checks expiration with a one minute skew", () => {
    const valid = createJwt({
      sub: "user-1",
      email: "ada@example.com",
      exp: Math.floor(Date.now() / 1000) + 3600,
    });
    const expiringSoon = createJwt({
      sub: "user-1",
      email: "ada@example.com",
      exp: Math.floor(Date.now() / 1000) + 30,
    });

    expect(isJwtExpired(valid)).toBe(false);
    expect(isJwtExpired(expiringSoon)).toBe(true);
    expect(isJwtExpired("not-a-jwt")).toBe(true);
  });
});
