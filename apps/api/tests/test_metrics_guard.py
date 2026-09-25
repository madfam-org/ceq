"""The Prometheus exposition is served to in-cluster scrapers only.

api.ceq.lol reaches port 5800 through cloudflared, which forwards the public
Host and adds Cloudflare edge headers. The in-cluster Prometheus scrapes the pod
IP with no Cloudflare headers. Public requests must see 404 on every /metrics
variant; the scrape path (/metrics/, per the ServiceMonitor and the
prometheus.io/path annotation) must keep returning exposition text.
"""

import pytest
from fastapi.testclient import TestClient

from ceq_api.metrics_guard import is_internal_host, is_metrics_path

SCRAPER_HOST = "10.42.1.2:5800"
PUBLIC_HOST = "api.ceq.lol"
METRICS_PATHS = ["/metrics", "/metrics/"]


@pytest.mark.parametrize("path", METRICS_PATHS)
def test_public_host_gets_404(client: TestClient, path: str) -> None:
    response = client.get(path, headers={"host": PUBLIC_HOST}, follow_redirects=False)

    assert response.status_code == 404
    assert "ceq_queue_depth" not in response.text


@pytest.mark.parametrize("path", METRICS_PATHS)
def test_cloudflare_header_gets_404_even_with_internal_host(
    client: TestClient, path: str
) -> None:
    # A spoofed internal Host does not help once the request crossed the edge.
    response = client.get(
        path,
        headers={"host": SCRAPER_HOST, "cf-connecting-ip": "203.0.113.7"},
        follow_redirects=False,
    )

    assert response.status_code == 404


@pytest.mark.parametrize("header", ["cf-ray", "cdn-loop"])
def test_other_cloudflare_edge_headers_get_404(client: TestClient, header: str) -> None:
    response = client.get("/metrics/", headers={"host": SCRAPER_HOST, header: "x"})

    assert response.status_code == 404


def test_scraper_gets_exposition_text_on_scrape_path(client: TestClient) -> None:
    response = client.get("/metrics/", headers={"host": SCRAPER_HOST})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    # The series the ceq-api-stability-alerts PrometheusRule reads.
    assert "# TYPE ceq_queue_depth gauge" in response.text
    assert "# TYPE ceq_completion_dead_letters gauge" in response.text


def test_scraper_bare_metrics_still_redirects_to_scrape_path(client: TestClient) -> None:
    response = client.get("/metrics", headers={"host": SCRAPER_HOST}, follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"].endswith("/metrics/")


@pytest.mark.parametrize(
    "host",
    ["ceq-api.ceq.svc:80", "ceq-api.ceq.svc.cluster.local", "localhost:5800", "[::1]:5800"],
)
def test_other_internal_hosts_get_exposition(client: TestClient, host: str) -> None:
    response = client.get("/metrics/", headers={"host": host})

    assert response.status_code == 200
    assert "# TYPE ceq_queue_depth gauge" in response.text


def test_guard_leaves_the_rest_of_the_public_api_alone(client: TestClient) -> None:
    response = client.get(
        "/health", headers={"host": PUBLIC_HOST, "cf-connecting-ip": "203.0.113.7"}
    )

    assert response.status_code == 200


@pytest.mark.parametrize(
    ("host", "internal"),
    [
        ("10.42.1.2:5800", True),
        ("10.42.1.2", True),
        ("[fd00::1]:5800", True),
        ("fd00::1", True),
        ("localhost", True),
        ("LOCALHOST:5800", True),
        ("ceq-api", True),
        ("ceq-api.ceq.svc", True),
        ("ceq-api.ceq.svc.cluster.local:80", True),
        ("api.ceq.lol", False),
        ("api.ceq.lol:443", False),
        ("api.ceq.lol.", False),
        ("evil.svc.example.com", False),
        ("", False),
    ],
)
def test_is_internal_host(host: str, internal: bool) -> None:
    assert is_internal_host(host) is internal


@pytest.mark.parametrize(
    ("path", "guarded"),
    [
        ("/metrics", True),
        ("/metrics/", True),
        ("/metrics/anything", True),
        ("/metricsx", False),
        ("/v1/jobs", False),
    ],
)
def test_is_metrics_path(path: str, guarded: bool) -> None:
    assert is_metrics_path(path) is guarded
