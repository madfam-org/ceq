"""Kubernetes manifest contract tests."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


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
        "FURNACE_API_URL",
    ):
        assert f"- name: {name}" in manifest

    assert 'value: "http://janua-api.janua.svc.cluster.local:4100"' in manifest
    assert "optional: true" not in manifest
