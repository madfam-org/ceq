"""Keep the Prometheus exposition internal to the cluster.

prometheus_client's ASGI app is mounted at ``/metrics`` on the same port (5800)
that cloudflared publishes as ``api.ceq.lol``, so without a guard anyone on the
internet can read queue depth, dead letters and every other series.

Every public request arrives through cloudflared, which forwards the public
Host (``api.ceq.lol``) and always adds the Cloudflare edge headers. Both
in-cluster Prometheus instances scrape pod IPs directly: Host is
``<podIP>:5800`` (or a ``*.svc`` name) and no Cloudflare header is present. The
guard answers 404 -- not 403, so the route does not advertise itself -- to
anything that looks public, and leaves the scrape path (``/metrics/``, per the
Service annotation and ServiceMonitor) untouched for scrapers.
"""

from __future__ import annotations

import ipaddress

from starlette.types import ASGIApp, Receive, Scope, Send

# Headers Cloudflare's edge adds to every request it proxies.
CLOUDFLARE_EDGE_HEADERS = frozenset({b"cf-connecting-ip", b"cf-ray", b"cdn-loop"})

METRICS_PREFIX = "/metrics"


def _strip_port(host: str) -> str:
    """Return the host part of a Host header value, lower-cased, port removed."""
    host = host.strip().lower()
    if host.startswith("["):  # [::1]:5800
        end = host.find("]")
        return host[1:end] if end != -1 else host
    if host.count(":") == 1:  # name:port or ipv4:port
        return host.split(":", 1)[0]
    return host  # bare name, bare IPv4, or bare IPv6 literal


def is_internal_host(host: str) -> bool:
    """True for Hosts only an in-cluster caller would send.

    Allowed: IP literals, ``localhost``, ``*.svc`` / ``*.svc.cluster.local``
    Service names, and bare names without dots. Anything else -- in particular
    a public FQDN such as ``api.ceq.lol`` -- is treated as public.
    """
    name = _strip_port(host)
    if not name:
        return False
    try:
        ipaddress.ip_address(name)
        return True
    except ValueError:
        pass
    if name == "localhost":
        return True
    if name.endswith((".svc", ".svc.cluster.local")):
        return True
    return "." not in name


def is_internal_scrape(scope: Scope) -> bool:
    """True when an HTTP scope looks like an in-cluster scraper, not the tunnel."""
    host = ""
    for key, value in scope.get("headers") or []:
        if key in CLOUDFLARE_EDGE_HEADERS:
            return False
        if key == b"host":
            host = value.decode("latin-1")
    return is_internal_host(host)


def is_metrics_path(path: str) -> bool:
    """``/metrics`` itself (a 307 to ``/metrics/``) and everything under it."""
    return path == METRICS_PREFIX or path.startswith(METRICS_PREFIX + "/")


class InternalOnlyMetricsMiddleware:
    """Answer 404 on every ``/metrics`` path unless the caller is in-cluster.

    Pure ASGI (not ``BaseHTTPMiddleware``) so it adds no per-request overhead to
    the rest of the API and never buffers the exposition body.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and is_metrics_path(scope.get("path", ""))
            and not is_internal_scrape(scope)
        ):
            body = b'{"detail":"Not Found"}'
            await send(
                {
                    "type": "http.response.start",
                    "status": 404,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                        (b"cache-control", b"no-store"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)
