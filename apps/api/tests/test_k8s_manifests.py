"""Kubernetes manifest contract tests."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
K8S_DIR = REPO_ROOT / "infrastructure/k8s"

# Every long-running workload must declare BOTH probes. Kyverno's
# `require-probes` ClusterPolicy matches `kind: Pod` and excludes only
# namespaces labelled enclii.dev/type in [infrastructure, build, data]; `ceq`
# is `application`, so every CEQ pod is evaluated. Bounded Jobs (migration,
# seed) are covered by infrastructure/k8s/policy-exceptions.yaml instead —
# a probe on a container designed to exit is meaningless.
PROBED_DEPLOYMENT_MANIFESTS = (
    "api-deployment.yaml",
    "studio-deployment.yaml",
    "worker-deployment.yaml",
    "worker-orchestrator-deployment.yaml",
)

JANUA_JWT_ENV = (
    "JANUA_JWKS_URL",
    "JANUA_ISSUER",
    "JANUA_AUDIENCE",
)

JANUA_JWT_VALUES = (
    'value: "http://janua-api.janua.svc.cluster.local/.well-known/jwks.json"',
    'value: "https://auth.madfam.io"',
    'value: "ceq-api"',
)


def test_api_deployment_has_janua_jwt_validation_env() -> None:
    manifest = (REPO_ROOT / "infrastructure/k8s/api-deployment.yaml").read_text()

    for name in JANUA_JWT_ENV:
        assert f"- name: {name}" in manifest

    for value in JANUA_JWT_VALUES:
        assert value in manifest


def test_external_secret_includes_janua_client_secret() -> None:
    manifest = (REPO_ROOT / "infrastructure/k8s/external-secret.yaml").read_text()

    assert "name: ceq-janua-client-secret" in manifest
    assert "secretKey: JANUA_CLIENT_SECRET" in manifest
    assert "property: JANUA_CLIENT_SECRET" in manifest


def test_external_secret_orchestrator_reads_vast_from_vault() -> None:
    manifest = (REPO_ROOT / "infrastructure/k8s/external-secret.yaml").read_text()

    assert "name: ceq-orchestrator-secrets" in manifest
    assert "name: vault-store" in manifest
    assert "secretKey: VAST_API_KEY" in manifest
    assert "key: secret/ceq" in manifest
    assert "property: vast_api_key" in manifest


def test_orchestrator_deployment_uses_vast_control_plane() -> None:
    manifest = (
        REPO_ROOT / "infrastructure/k8s/worker-orchestrator-deployment.yaml"
    ).read_text()

    assert "name: ceq-orchestrator" in manifest
    assert "ceq_worker.orchestrator" in manifest
    assert "CEQ_GPU_PROVIDER" in manifest
    assert 'value: "vast"' in manifest
    assert "CEQ_WORKER_API_URL" in manifest
    assert "VAST_API_KEY" in manifest
    assert "nvidia.com/gpu" not in manifest


def test_worker_deployment_stays_blocked_without_gpu_nodes() -> None:
    manifest = (REPO_ROOT / "infrastructure/k8s/worker-deployment.yaml").read_text()

    assert "replicas: 0" in manifest
    assert "no-gpu-nodes-on-hetzner-cluster" in manifest
    assert "nvidia.com/gpu" in manifest


def test_migration_job_has_full_production_runtime_env() -> None:
    manifest = (REPO_ROOT / "infrastructure/k8s/db-migrate-job.yaml").read_text()

    for name in (
        "ENVIRONMENT",
        "DATABASE_URL",
        "REDIS_URL",
        "R2_ENDPOINT",
        "R2_ACCESS_KEY",
        "R2_SECRET_KEY",
        "R2_BUCKET_NAME",
        "JOB_COMPLETION_CALLBACK_TOKEN",
        "JOB_WEBHOOK_SECRET",
        "JANUA_API_URL",
        *JANUA_JWT_ENV,
        "FURNACE_API_URL",
    ):
        assert f"- name: {name}" in manifest

    assert 'value: "http://janua-api.janua.svc.cluster.local"' in manifest
    assert "optional: true" not in manifest


def test_network_policy_allows_janua_egress() -> None:
    manifest = (REPO_ROOT / "infrastructure/k8s/network-policies.yaml").read_text()

    assert "name: allow-janua-egress" in manifest
    assert "kubernetes.io/metadata.name: janua" in manifest
    assert "port: 8080" in manifest


# --------------------------------------------------------------------------
# Kyverno probe + image-pin contract (R7, docs/DOCS_EVIDENCE_AUDIT_2026-06-02)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("manifest_name", PROBED_DEPLOYMENT_MANIFESTS)
def test_every_deployment_declares_both_probes(manifest_name: str) -> None:
    """Each Deployment manifest must declare readiness AND liveness probes.

    Regression guard for the `require-probes` violations counted in the
    2026-06-02 evidence audit. ceq-worker was the offender: it sits at
    replicas: 0 pending GPU nodes, which made the gap easy to miss, but the
    policy validates the pod template, so it would fail the instant KEDA
    scaled it up.
    """
    manifest = (K8S_DIR / manifest_name).read_text()

    assert "readinessProbe:" in manifest, f"{manifest_name} lacks a readinessProbe"
    assert "livenessProbe:" in manifest, f"{manifest_name} lacks a livenessProbe"


def test_worker_probes_are_exec_not_http() -> None:
    """The queue consumer has no HTTP listener, so probes must be exec.

    `python -m ceq_worker.queue` is a headless Redis DB-14 consumer (see the
    Dockerfile CMD and the explicit `ports: []`). An httpGet probe would fail
    permanently and CrashLoop the pod once it scales. Kyverno's
    `require-probes` accepts exec probes (anyPattern includes exec.command),
    so this satisfies the policy without inventing an HTTP surface.
    """
    yaml = pytest.importorskip("yaml", reason="PyYAML not installed in this lane")

    raw = (K8S_DIR / "worker-deployment.yaml").read_text()
    # Assert on parsed structure, not raw text: the manifest's comments
    # legitimately mention httpGet when explaining why it is not used here.
    deployment = next(
        d
        for d in yaml.safe_load_all(raw)
        if d and d.get("kind") == "Deployment" and d["metadata"]["name"] == "ceq-worker"
    )
    containers = deployment["spec"]["template"]["spec"]["containers"]
    assert containers, "ceq-worker declares no containers"

    for container in containers:
        # No HTTP listener at all — the explicit empty list is also what keeps
        # the autogen host-ports rule evaluating a concrete shape.
        assert container.get("ports") == []
        for probe_name in ("readinessProbe", "livenessProbe"):
            probe = container[probe_name]
            assert "httpGet" not in probe, (
                f"{probe_name}: worker has no HTTP listener; probes must be exec"
            )
            # The Redis reachability check the consumer itself performs.
            assert "redis" in " ".join(probe["exec"]["command"])


def test_batch_jobs_have_a_probe_policy_exception() -> None:
    """Run-to-completion Jobs are exempted rather than given fake probes."""
    manifest = (K8S_DIR / "policy-exceptions.yaml").read_text()

    assert "kind: PolicyException" in manifest
    assert "policyName: require-probes" in manifest
    # The autogen variant must be listed too, or the Job-owned pods stay
    # reported even though the Job itself is excepted.
    assert "autogen-require-readiness-probe" in manifest
    for job_glob in ('"ceq-db-migrate*"', '"ceq-seed-templates*"'):
        assert job_glob in manifest

    # The exception must never widen to cover the long-running Deployments.
    for workload in ("ceq-api", "ceq-studio", "ceq-worker", "ceq-orchestrator"):
        assert f'"{workload}*"' not in manifest

    # And it must be wired into the bundle, or it never reaches the cluster.
    kustomization = (K8S_DIR / "kustomization.yaml").read_text()
    assert "- policy-exceptions.yaml" in kustomization


def test_every_image_is_digest_pinned_in_kustomization() -> None:
    """The digest pins are what make the rendered Pods policy-clean.

    Kyverno's `disallow-latest-tag` and `require-image-digest` both match
    `kind: Pod`, i.e. the image AFTER kustomize applies these pins — not the
    `:latest` placeholder text in the Deployment files. This test pins the
    thing that actually matters: every image entry carries a sha256 digest.
    """
    kustomization = (K8S_DIR / "kustomization.yaml").read_text()

    for image in (
        "ghcr.io/madfam-org/ceq-api",
        "ghcr.io/madfam-org/ceq-studio",
        "ghcr.io/madfam-org/ceq-worker",
    ):
        assert f"name: {image}" in kustomization, f"{image} missing from images:"

    digests = re.findall(r"^- digest: (sha256:[0-9a-f]{64})$", kustomization, re.M)
    assert len(digests) == 3, f"expected 3 pinned digests, found {len(digests)}"


def test_deployment_images_stay_dash_form_placeholders() -> None:
    """Deployment files must keep the mutable ref kustomize rewrites.

    Hardcoding a digest here would be dead-but-authoritative config: kustomize
    overrides it anyway, so it becomes a second place digests live that the
    GitOps workflow never updates. Keep the placeholder; the pin lives in
    kustomization.yaml (and is asserted above).
    """
    for manifest_name, image in (
        ("api-deployment.yaml", "ghcr.io/madfam-org/ceq-api"),
        ("studio-deployment.yaml", "ghcr.io/madfam-org/ceq-studio"),
        ("worker-deployment.yaml", "ghcr.io/madfam-org/ceq-worker"),
    ):
        manifest = (K8S_DIR / manifest_name).read_text()
        assert f"image: {image}:latest" in manifest, (
            f"{manifest_name} must reference {image}:latest so "
            "`kustomize edit set image` can rewrite it to a digest"
        )


def test_rendered_manifests_are_probe_and_digest_clean() -> None:
    """End-to-end check on what ArgoCD actually applies.

    The string assertions above guard the source files; this one renders the
    bundle and asserts the property Kyverno evaluates. Skipped when neither
    PyYAML nor kustomize is available (CI's api lane installs an explicit
    dependency list that does not include PyYAML).
    """
    yaml = pytest.importorskip("yaml", reason="PyYAML not installed in this lane")

    import shutil
    import subprocess

    kustomize = shutil.which("kustomize")
    cmd = (
        [kustomize, "build", str(K8S_DIR)]
        if kustomize
        else [shutil.which("kubectl") or "", "kustomize", str(K8S_DIR)]
    )
    if not cmd[0]:
        pytest.skip("neither kustomize nor kubectl available")

    rendered = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if rendered.returncode != 0:
        pytest.skip(f"kustomize build unavailable: {rendered.stderr[:200]}")

    docs = [d for d in yaml.safe_load_all(rendered.stdout) if d]
    assert docs, "kustomize produced no documents"

    deployments = 0
    for doc in docs:
        if doc.get("kind") != "Deployment":
            continue
        deployments += 1
        name = doc["metadata"]["name"]
        for container in doc["spec"]["template"]["spec"]["containers"]:
            assert "readinessProbe" in container, f"{name} readiness probe missing"
            assert "livenessProbe" in container, f"{name} liveness probe missing"
            image = container["image"]
            assert "@sha256:" in image, f"{name} image not digest-pinned: {image}"
            assert not image.endswith(":latest"), f"{name} renders a :latest tag"

    assert deployments == 4, f"expected 4 Deployments, rendered {deployments}"


# --------------------------------------------------------------------------
# enclii.yaml service spec (R8, docs/DOCS_EVIDENCE_AUDIT_2026-06-02)
# --------------------------------------------------------------------------


def test_enclii_manifest_declares_all_three_services() -> None:
    """enclii.yaml must be a full spec, not status-only.

    While it was status-only, every Enclii verb that parses a Service document
    failed with `spec.build.type: must be one of: auto, dockerfile, buildpack`,
    which is why `enclii service-secret` could not operate on CEQ during the
    2026-06-02 audit.
    """
    yaml = pytest.importorskip("yaml", reason="PyYAML not installed in this lane")

    docs = [d for d in yaml.safe_load_all((REPO_ROOT / "enclii.yaml").read_text()) if d]
    by_kind: dict[str, list[dict]] = {}
    for doc in docs:
        by_kind.setdefault(doc["kind"], []).append(doc)

    # switchyard's ParseEncliiYAML reads ONLY the first document and returns
    # early on kind: Project — so status/domains must live there or
    # status.madfam.io silently loses CEQ.
    assert docs[0]["kind"] == "Project", "first document must be kind: Project"
    project_spec = docs[0]["spec"]
    status_urls = {e["url"] for e in project_spec["status"]["entries"]}
    assert "https://ceq.lol" in status_urls
    assert "https://api.ceq.lol/health" in status_urls

    services = {s["metadata"]["name"]: s["spec"] for s in by_kind["Service"]}
    assert set(services) == {"ceq-api", "ceq-studio", "ceq-worker"}

    expected_ports = {"ceq-api": 5800, "ceq-studio": 5801, "ceq-worker": 5810}
    for name, port in expected_ports.items():
        assert services[name]["runtime"]["port"] == port
        # Every service must carry a build block — its absence is the exact
        # schema failure that made CEQ unusable from Enclii tooling.
        assert services[name]["build"]["type"] == "dockerfile"

    # The worker is not routable: no ingress, no domain.
    worker_net = next(
        s for s in project_spec["network"]["services"] if s["name"] == "ceq-worker"
    )
    assert "ingress" not in worker_net
    domain_hosts = {
        d["host"] for s in project_spec["services"] for d in s.get("domains", [])
    }
    assert domain_hosts == {"ceq.lol", "app.ceq.lol", "api.ceq.lol", "ws.ceq.lol"}


def test_enclii_health_paths_match_k8s_probes() -> None:
    """enclii.yaml healthCheck must match the probe the cluster actually runs.

    A drifting healthCheck is worse than none: Enclii would report a service
    healthy from a path Kubernetes never probes.
    """
    yaml = pytest.importorskip("yaml", reason="PyYAML not installed in this lane")

    docs = [d for d in yaml.safe_load_all((REPO_ROOT / "enclii.yaml").read_text()) if d]
    services = {
        d["metadata"]["name"]: d["spec"] for d in docs if d["kind"] == "Service"
    }

    assert services["ceq-api"]["runtime"]["healthCheck"] == "/health"
    assert services["ceq-studio"]["runtime"]["healthCheck"] == "/"
    # The worker has no HTTP surface, so it must declare no healthCheck rather
    # than a path that does not exist.
    assert "healthCheck" not in services["ceq-worker"]["runtime"]
