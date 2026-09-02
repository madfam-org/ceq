"""Tests for the multi-tenant brand-kit DAM.

Coverage priorities (in order):
1. Tenant isolation — the security guarantee. Tenant A cannot read, patch, or
   upload into tenant B's kit, and cannot even learn B's ids exist (404, not 403).
2. Route-tree invariant — no destructive verbs (no PUT, no DELETE) anywhere on
   the /v1/brand-kits surface.
3. Token-export shape — the consumer contract MAP/crea-frontend/renderer align on.
4. Tenant-from-token discipline — the tenant is resolved from the token's org,
   never taken from the URL; a tenant-less caller is refused.
"""

from uuid import uuid4

import pytest
from fastapi import status

from ceq_api.auth.janua import JanuaUser
from ceq_api.models import BrandAsset, BrandKit, Client

# --- Fixtures ---------------------------------------------------------------


def _make_user(org_id, roles=None):
    return JanuaUser(
        id=uuid4(),
        email=f"user-{uuid4().hex[:6]}@madfam.io",
        org_id=org_id,
        roles=roles or ["user"],
    )


@pytest.fixture
def tenant_a_org():
    return uuid4()


@pytest.fixture
def tenant_b_org():
    return uuid4()


@pytest.fixture
async def seed_tenants(db_session, tenant_a_org, tenant_b_org):
    """Two provisioned tenants, each with one kit; tenant A's kit has an asset."""
    client_a = Client(janua_org_id=tenant_a_org, slug="tenant-a", display_name="Tenant A")
    client_b = Client(janua_org_id=tenant_b_org, slug="tenant-b", display_name="Tenant B")
    db_session.add_all([client_a, client_b])
    await db_session.flush()

    kit_a = BrandKit(
        client_id=client_a.id,
        name="Primary",
        version=1,
        palette={"brand": "#7C5CFF"},
        typography={"heading": {"family": "Space Grotesk"}},
        logos={},
        guidelines={"tagline": "Crea tu mundo"},
        is_active=True,
    )
    kit_b = BrandKit(
        client_id=client_b.id,
        name="Primary",
        version=1,
        palette={"brand": "#00AA00"},
        typography={},
        logos={},
        guidelines={},
        is_active=True,
    )
    db_session.add_all([kit_a, kit_b])
    await db_session.flush()

    asset_a = BrandAsset(
        brand_kit_id=kit_a.id,
        client_id=client_a.id,
        kind="logo-primary",
        variant=None,
        filename="logo.png",
        storage_uri="r2://ceq-assets/brand-kits/tenant-a/1/logo-primary/x_logo.png",
        content_type="image/png",
        size_bytes=1234,
        checksum="deadbeef",
        tags=[],
        is_active=True,
    )
    db_session.add(asset_a)
    await db_session.flush()

    return {
        "client_a": client_a,
        "client_b": client_b,
        "kit_a": kit_a,
        "kit_b": kit_b,
        "asset_a": asset_a,
    }


def _auth_as(app, user):
    """Point the app's auth dependencies at ``user`` for the current test."""
    from ceq_api.auth import get_current_user

    async def _override():
        return user

    app.dependency_overrides[get_current_user] = _override


# === Tenant-from-token discipline ==========================================


class TestTenantResolution:
    async def test_caller_without_org_is_refused(self, app, async_client):
        """A token with no org claim has no tenant -> 403, not a silent default."""
        _auth_as(app, _make_user(org_id=None))
        resp = await async_client.get("/v1/brand-kits")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    async def test_unprovisioned_org_is_404(self, app, async_client):
        """A valid tenant claim with no provisioned client -> 404."""
        _auth_as(app, _make_user(org_id=uuid4()))
        resp = await async_client.get("/v1/brand-kits")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    async def test_me_client_reflects_token_org(self, app, async_client, seed_tenants, tenant_a_org):
        _auth_as(app, _make_user(org_id=tenant_a_org))
        resp = await async_client.get("/v1/brand-kits/me/client")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["slug"] == "tenant-a"


# === Tenant isolation (the core security tests) ============================


class TestTenantIsolation:
    async def test_list_returns_only_own_tenant_kits(
        self, app, async_client, seed_tenants, tenant_a_org
    ):
        _auth_as(app, _make_user(org_id=tenant_a_org))
        resp = await async_client.get("/v1/brand-kits")
        assert resp.status_code == status.HTTP_200_OK
        body = resp.json()
        ids = {k["id"] for k in body["kits"]}
        assert str(seed_tenants["kit_a"].id) in ids
        assert str(seed_tenants["kit_b"].id) not in ids
        assert body["client"]["slug"] == "tenant-a"

    async def test_cannot_read_other_tenant_kit(
        self, app, async_client, seed_tenants, tenant_a_org
    ):
        """A cross-tenant id is 404 (not 403) — the fence must not leak existence."""
        _auth_as(app, _make_user(org_id=tenant_a_org))
        resp = await async_client.get(f"/v1/brand-kits/{seed_tenants['kit_b'].id}")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    async def test_cannot_patch_other_tenant_kit(
        self, app, async_client, seed_tenants, tenant_a_org, db_session
    ):
        _auth_as(app, _make_user(org_id=tenant_a_org))
        resp = await async_client.patch(
            f"/v1/brand-kits/{seed_tenants['kit_b'].id}",
            json={"palette": {"brand": "#FF0000"}},
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        # And tenant B's kit is untouched.
        await db_session.refresh(seed_tenants["kit_b"])
        assert seed_tenants["kit_b"].palette == {"brand": "#00AA00"}
        assert seed_tenants["kit_b"].version == 1

    async def test_cannot_read_other_tenant_asset(
        self, app, async_client, seed_tenants, tenant_b_org
    ):
        """Tenant B cannot read tenant A's asset even naming both ids in the URL."""
        _auth_as(app, _make_user(org_id=tenant_b_org))
        resp = await async_client.get(
            f"/v1/brand-kits/{seed_tenants['kit_a'].id}/assets/{seed_tenants['asset_a'].id}"
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    async def test_cannot_upload_into_other_tenant_kit(
        self, app, async_client, seed_tenants, tenant_b_org
    ):
        _auth_as(app, _make_user(org_id=tenant_b_org))
        resp = await async_client.post(
            f"/v1/brand-kits/{seed_tenants['kit_a'].id}/assets",
            data={"kind": "logo-primary"},
            files={"file": ("evil.png", b"\x89PNG", "image/png")},
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    async def test_cannot_tokens_export_other_tenant_kit(
        self, app, async_client, seed_tenants, tenant_a_org
    ):
        _auth_as(app, _make_user(org_id=tenant_a_org))
        resp = await async_client.get(f"/v1/brand-kits/{seed_tenants['kit_b'].id}/tokens")
        assert resp.status_code == status.HTTP_404_NOT_FOUND


# === No destructive verbs (route-tree invariant) ==========================


class TestNoDestructiveVerbs:
    def test_no_put_or_delete_on_brand_kits_surface(self, app):
        """Route-tree invariant: nothing under /v1/brand-kits accepts PUT or DELETE.

        Mirrors acervo's 'append/soft-delete only' contract. Enforced against the
        real OpenAPI schema so a future destructive route cannot slip in unnoticed.
        """
        paths = app.openapi()["paths"]
        offenders = []
        for path, methods in paths.items():
            if not path.startswith("/v1/brand-kits"):
                continue
            for verb in methods:
                if verb.lower() in {"put", "delete"}:
                    offenders.append((path, verb))
        assert offenders == [], f"Destructive verbs found on brand-kit surface: {offenders}"

    def test_no_tenant_id_in_any_brand_kit_path(self, app):
        """No brand-kit route names a tenant/client/org in its path or query.

        The only client-id-bearing route is the admin /clients provisioning body,
        never a path segment — so a caller can't request another tenant by URL.
        """
        paths = app.openapi()["paths"]
        for path in paths:
            if not path.startswith("/v1/brand-kits"):
                continue
            lowered = path.lower()
            # A path param mentioning org/tenant/client would be a cross-tenant hole.
            assert "{client" not in lowered
            assert "{org" not in lowered
            assert "{tenant" not in lowered


# === Happy-path lifecycle + token export (consumer contract) ===============


class TestLifecycleAndTokens:
    async def test_create_get_patch_bumps_version(
        self, app, async_client, seed_tenants, tenant_a_org
    ):
        _auth_as(app, _make_user(org_id=tenant_a_org))
        # Create a second kit for tenant A.
        create = await async_client.post(
            "/v1/brand-kits",
            json={
                "name": "Sub-brand",
                "palette": {"brand": "#111111"},
                "typography": {"body": {"family": "Inter"}},
                "guidelines": {"voice": "Playful"},
            },
        )
        assert create.status_code == status.HTTP_201_CREATED
        kit = create.json()
        assert kit["version"] == 1
        assert kit["client_id"] == str(seed_tenants["client_a"].id)

        # Patch it; version must bump.
        patch = await async_client.patch(
            f"/v1/brand-kits/{kit['id']}",
            json={"palette": {"brand": "#222222", "accent": "#3CE0C0"}},
        )
        assert patch.status_code == status.HTTP_200_OK
        assert patch.json()["version"] == 2
        assert patch.json()["palette"]["accent"] == "#3CE0C0"

    async def test_duplicate_name_conflict(self, app, async_client, seed_tenants, tenant_a_org):
        _auth_as(app, _make_user(org_id=tenant_a_org))
        resp = await async_client.post("/v1/brand-kits", json={"name": "Primary"})
        assert resp.status_code == status.HTTP_409_CONFLICT

    async def test_soft_deactivate_hides_from_list(
        self, app, async_client, seed_tenants, tenant_a_org
    ):
        _auth_as(app, _make_user(org_id=tenant_a_org))
        kit_id = str(seed_tenants["kit_a"].id)
        deact = await async_client.patch(f"/v1/brand-kits/{kit_id}", json={"is_active": False})
        assert deact.status_code == status.HTTP_200_OK
        listing = await async_client.get("/v1/brand-kits")
        ids = {k["id"] for k in listing.json()["kits"]}
        assert kit_id not in ids
        # Reactivation is possible — nothing was destroyed.
        react = await async_client.patch(f"/v1/brand-kits/{kit_id}", json={"is_active": True})
        assert react.status_code == status.HTTP_200_OK

    async def test_tokens_export_shape(
        self, app, async_client, seed_tenants, tenant_a_org, db_session
    ):
        """The token export is the ecosystem contract: named palette, typography,
        resolved logos (with URLs), guidelines, and a pinnable version."""
        # Point kit_a's 'primary' logo at asset_a so the export resolves a URL.
        kit_a = seed_tenants["kit_a"]
        kit_a.logos = {"primary": str(seed_tenants["asset_a"].id)}
        await db_session.flush()

        _auth_as(app, _make_user(org_id=tenant_a_org))
        resp = await async_client.get(f"/v1/brand-kits/{kit_a.id}/tokens")
        assert resp.status_code == status.HTTP_200_OK
        body = resp.json()

        assert body["client_slug"] == "tenant-a"
        assert body["kit_id"] == str(kit_a.id)
        assert body["version"] == kit_a.version
        assert body["palette"]["brand"] == "#7C5CFF"
        assert body["typography"]["heading"]["family"] == "Space Grotesk"
        assert body["guidelines"]["tagline"] == "Crea tu mundo"
        assert "primary" in body["logos"]
        logo = body["logos"]["primary"]
        assert logo["asset_id"] == str(seed_tenants["asset_a"].id)
        assert logo["kind"] == "logo-primary"
        assert logo["url"]  # a fetchable URL was resolved
        assert "generated_at" in body

    async def test_tokens_export_skips_dangling_logo_ref(
        self, app, async_client, seed_tenants, tenant_a_org, db_session
    ):
        """A logo id that no longer resolves is skipped, not fatal."""
        kit_a = seed_tenants["kit_a"]
        kit_a.logos = {"primary": str(uuid4())}  # points at nothing
        await db_session.flush()
        _auth_as(app, _make_user(org_id=tenant_a_org))
        resp = await async_client.get(f"/v1/brand-kits/{kit_a.id}/tokens")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["logos"] == {}

    async def test_patch_logos_rejects_cross_kit_ref(
        self, app, async_client, seed_tenants, tenant_a_org
    ):
        """A kit cannot point its logos at an id that isn't its own asset."""
        _auth_as(app, _make_user(org_id=tenant_a_org))
        resp = await async_client.patch(
            f"/v1/brand-kits/{seed_tenants['kit_a'].id}",
            json={"logos": {"primary": str(uuid4())}},
        )
        assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# === Admin client provisioning =============================================


class TestClientProvisioning:
    async def test_provision_requires_admin(self, app, async_client, tenant_a_org):
        _auth_as(app, _make_user(org_id=tenant_a_org, roles=["user"]))
        resp = await async_client.post(
            "/v1/brand-kits/clients",
            json={"janua_org_id": str(uuid4()), "display_name": "New Co"},
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    async def test_admin_can_provision_and_slug_is_derived(self, app, async_client):
        _auth_as(app, _make_user(org_id=uuid4(), roles=["admin", "user"]))
        org = str(uuid4())
        resp = await async_client.post(
            "/v1/brand-kits/clients",
            json={"janua_org_id": org, "display_name": "Crea Tu Mundo"},
        )
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.json()["slug"] == "crea-tu-mundo"

    async def test_provision_rejects_duplicate_org(
        self, app, async_client, seed_tenants, tenant_a_org
    ):
        _auth_as(app, _make_user(org_id=uuid4(), roles=["admin"]))
        resp = await async_client.post(
            "/v1/brand-kits/clients",
            json={"janua_org_id": str(tenant_a_org), "display_name": "Dup"},
        )
        assert resp.status_code == status.HTTP_409_CONFLICT


# === Migration regression (offline, mirrors tests/test_migrations.py) =======


class TestBrandDamMigration:
    """Exercise the brand-DAM migration's op sequence offline.

    No live DB is used (the repo's migrations use ``postgresql.JSONB`` and target
    Postgres). This mirrors ``tests/test_migrations.py``: a fake ``op`` records
    calls so we can assert the three tables are created on upgrade and dropped on
    downgrade, and that downgrade is the exact inverse (drop children before the
    parent so the FKs unwind cleanly).
    """

    def _load_migration(self):
        import importlib

        return importlib.import_module("ceq_api.alembic.versions.20260901_add_brand_dam")

    def test_upgrade_creates_all_three_tables(self, monkeypatch):
        migration = self._load_migration()

        class FakeOp:
            def __init__(self):
                self.created: list[str] = []
                self.indexed: list[str] = []

            def create_table(self, name, *args, **kwargs):
                self.created.append(name)

            def create_index(self, name, table_name, *args, **kwargs):
                self.indexed.append(table_name)

            def f(self, name):
                return name

        fake = FakeOp()
        monkeypatch.setattr(migration, "op", fake)
        migration.upgrade()
        assert fake.created == ["brand_clients", "brand_kits", "brand_assets"]
        # Every table carries at least one index.
        assert set(fake.indexed) == {"brand_clients", "brand_kits", "brand_assets"}

    def test_downgrade_drops_children_before_parent(self, monkeypatch):
        migration = self._load_migration()

        class FakeOp:
            def __init__(self):
                self.dropped_tables: list[str] = []

            def drop_table(self, name):
                self.dropped_tables.append(name)

            def drop_index(self, name, table_name=None):
                pass

            def f(self, name):
                return name

        fake = FakeOp()
        monkeypatch.setattr(migration, "op", fake)
        migration.downgrade()
        # brand_assets and brand_kits (children) must drop before brand_clients.
        assert fake.dropped_tables == ["brand_assets", "brand_kits", "brand_clients"]

    def test_chains_from_current_head(self):
        migration = self._load_migration()
        assert migration.down_revision == "20260601_credit_ledger"
        assert migration.revision == "20260901_brand_dam"
