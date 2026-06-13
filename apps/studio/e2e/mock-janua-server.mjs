#!/usr/bin/env node
/**
 * Minimal Janua OIDC mock for Studio Playwright auth tests.
 *
 * Studio API routes call Janua server-side; browser route interception is not
 * enough. Point NEXT_PUBLIC_JANUA_URL at this server during e2e runs.
 */

import http from "node:http";
import { URL } from "node:url";

const PORT = Number(process.env.MOCK_JANUA_PORT || 5999);
const HOST = process.env.MOCK_JANUA_HOST || "127.0.0.1";

function base64Url(value) {
  return Buffer.from(JSON.stringify(value))
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

function createMockJwt(claims = {}) {
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

function sendJson(res, status, body) {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(body));
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on("data", (chunk) => chunks.push(chunk));
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    req.on("error", reject);
  });
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url || "/", `http://${HOST}:${PORT}`);

  if (url.pathname === "/health") {
    sendJson(res, 200, { status: "ok" });
    return;
  }

  if (url.pathname === "/api/v1/oauth/authorize" && req.method === "GET") {
    const redirectUri = url.searchParams.get("redirect_uri");
    const state = url.searchParams.get("state") || "/";
    const code = url.searchParams.get("force_error") === "1"
      ? "e2e-fail-code"
      : "e2e-auth-code";

    if (!redirectUri) {
      sendJson(res, 400, { error: "missing redirect_uri" });
      return;
    }

    const callback = new URL(redirectUri);
    callback.searchParams.set("code", code);
    callback.searchParams.set("state", state);

    res.writeHead(302, { Location: callback.toString() });
    res.end();
    return;
  }

  if (url.pathname === "/api/v1/oauth/token" && req.method === "POST") {
    const body = await readBody(req);
    const params = new URLSearchParams(body);
    const grantType = params.get("grant_type");
    const code = params.get("code");

    if (code === "e2e-fail-code") {
      sendJson(res, 401, {
        error: "invalid_client",
        error_description: "invalid_client: Unknown client_id",
      });
      return;
    }

    if (grantType === "refresh_token") {
      sendJson(res, 200, {
        access_token: createMockJwt({
          name: "Studio E2E Refreshed",
          exp: Math.floor(Date.now() / 1000) + 7200,
        }),
        refresh_token: params.get("refresh_token") || "e2e-refresh-token",
        expires_in: 7200,
        token_type: "Bearer",
      });
      return;
    }

    sendJson(res, 200, {
      access_token: createMockJwt(),
      refresh_token: "e2e-refresh-token",
      expires_in: 3600,
      token_type: "Bearer",
    });
    return;
  }

  if (url.pathname === "/logout" && req.method === "GET") {
    const postLogout = url.searchParams.get("post_logout_redirect_uri");
    res.writeHead(302, {
      Location: postLogout || `http://${HOST}:5801/login`,
    });
    res.end();
    return;
  }

  sendJson(res, 404, { error: "not_found", path: url.pathname });
});

server.listen(PORT, HOST, () => {
  console.log(`[mock-janua] listening on http://${HOST}:${PORT}`);
});
