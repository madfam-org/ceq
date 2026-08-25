"""Kubernetes manifest contract tests."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

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


# --- pgbouncer adoption (move 2) contracts -------------------------------
#
# Backstop for the 2026-08-24 outage. The runtime DATABASE_URL is rendered
# through the pooler while DDL must stay on a direct 5432 session.


def test_migration_job_receives_direct_database_url() -> None:
    """Alembic prefers DIRECT_DATABASE_URL; the Job must actually supply it.

    Without this env the PreSync migrate Job would fall through to the pooled
    DATABASE_URL and run DDL through transaction pooling.
    """
    manifest = (REPO_ROOT / "infrastructure/k8s/db-migrate-job.yaml").read_text()

    assert "- name: DIRECT_DATABASE_URL" in manifest
    assert "key: DIRECT_DATABASE_URL" in manifest


def test_external_secret_renders_both_pooled_and_direct_urls() -> None:
    manifest = (REPO_ROOT / "infrastructure/k8s/external-secret.yaml").read_text()

    assert "DIRECT_DATABASE_URL:" in manifest
    assert "pgbouncer.data.svc.cluster.local:6432" in manifest
    # mergePolicy must stay Merge or the non-templated keys vanish.
    assert "mergePolicy: Merge" in manifest


def test_external_secret_host_rewrite_is_namespace_agnostic() -> None:
    """A plain string `replace` silently no-op'd on other host spellings.

    The rewrite must anchor on the postgres service host pattern so a Vault
    value in any namespace (or without an explicit port) still flips.
    """
    manifest = (REPO_ROOT / "infrastructure/k8s/external-secret.yaml").read_text()

    assert "regexReplaceAll" in manifest
    assert 'replace "postgres.data.svc.cluster.local:5432"' not in manifest
