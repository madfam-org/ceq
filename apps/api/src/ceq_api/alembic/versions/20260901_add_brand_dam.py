"""add brand DAM tables (client / brand_kit / brand_asset)

Introduces the curated, multi-tenant client-brand-asset layer that turns ceq
into a real DAM: a ``brand_clients`` tenant root, ``brand_kits`` structured
source-of-truth, and ``brand_assets`` R2-backed binaries. Tenant scoping is by
``janua_org_id`` on the client (resolved from the token, never the URL).

Revision ID: 20260901_brand_dam
Revises: 20260601_credit_ledger
Create Date: 2026-09-01 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260901_brand_dam"
down_revision: str | None = "20260601_credit_ledger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- brand_clients: the tenant root -------------------------------------
    op.create_table(
        "brand_clients",
        sa.Column(
            "janua_org_id",
            sa.UUID(),
            nullable=False,
            comment="Janua organization/tenant ID this client is bound to (from the token, not the URL)",
        ),
        sa.Column(
            "slug",
            sa.String(length=80),
            nullable=False,
            comment="URL/storage-safe stable key, e.g. 'crea-tu-mundo'",
        ),
        sa.Column(
            "display_name",
            sa.String(length=255),
            nullable=False,
            comment="Human-readable client/org name",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="Soft-deactivation flag; brand data is retained when False",
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("janua_org_id", name="uq_brand_clients_janua_org_id"),
        sa.UniqueConstraint("slug", name="uq_brand_clients_slug"),
    )
    op.create_index(op.f("ix_brand_clients_janua_org_id"), "brand_clients", ["janua_org_id"], unique=False)
    op.create_index(op.f("ix_brand_clients_slug"), "brand_clients", ["slug"], unique=False)

    # --- brand_kits: structured brand book ----------------------------------
    op.create_table(
        "brand_kits",
        sa.Column(
            "client_id",
            sa.UUID(),
            nullable=False,
            comment="Owning tenant (Client). Resolved from the Janua token, never the URL.",
        ),
        sa.Column("name", sa.String(length=120), nullable=False, comment="Kit name, unique within the client"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
            comment="Monotonic brand-book version; bumped on each structured update",
        ),
        sa.Column(
            "palette",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="Named color tokens: role -> hex | {light,dark}. Consumer-addressable.",
        ),
        sa.Column(
            "typography",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="Font roles (heading/body/mono) -> family, weights, optional scale.",
        ),
        sa.Column(
            "logos",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="Logical logo variant -> BrandAsset id. Resolved to URLs on export.",
        ),
        sa.Column(
            "guidelines",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="Usage rules: clear_space, min_size, tagline, voice, do/dont, notes.",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="Soft-deactivation flag; kit data is retained when False",
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["brand_clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_id", "name", name="uq_brand_kit_client_name"),
    )
    op.create_index(op.f("ix_brand_kits_client_id"), "brand_kits", ["client_id"], unique=False)

    # --- brand_assets: R2-backed binaries -----------------------------------
    op.create_table(
        "brand_assets",
        sa.Column("brand_kit_id", sa.UUID(), nullable=False, comment="Owning BrandKit"),
        sa.Column(
            "client_id",
            sa.UUID(),
            nullable=False,
            comment="Owning tenant (denormalized from the kit for join-free scoping)",
        ),
        sa.Column(
            "kind",
            sa.String(length=40),
            nullable=False,
            comment="Role: logo-primary | logo-inverse | font | guideline-pdf | photo | ...",
        ),
        sa.Column("variant", sa.String(length=60), nullable=True, comment="Optional colorway/variant"),
        sa.Column("filename", sa.String(length=255), nullable=False, comment="Sanitized original filename"),
        sa.Column("storage_uri", sa.String(length=2048), nullable=False, comment="R2 URI (r2://bucket/key)"),
        sa.Column(
            "content_type",
            sa.String(length=120),
            nullable=False,
            server_default=sa.text("'application/octet-stream'"),
            comment="MIME type of the stored bytes",
        ),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=True, comment="SHA256 hash of the uploaded bytes"),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="Soft-deactivation flag; asset row + bytes are retained when False",
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["brand_kit_id"], ["brand_kits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["client_id"], ["brand_clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_brand_assets_brand_kit_id"), "brand_assets", ["brand_kit_id"], unique=False)
    op.create_index(op.f("ix_brand_assets_client_id"), "brand_assets", ["client_id"], unique=False)
    op.create_index(op.f("ix_brand_assets_kind"), "brand_assets", ["kind"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_brand_assets_kind"), table_name="brand_assets")
    op.drop_index(op.f("ix_brand_assets_client_id"), table_name="brand_assets")
    op.drop_index(op.f("ix_brand_assets_brand_kit_id"), table_name="brand_assets")
    op.drop_table("brand_assets")

    op.drop_index(op.f("ix_brand_kits_client_id"), table_name="brand_kits")
    op.drop_table("brand_kits")

    op.drop_index(op.f("ix_brand_clients_slug"), table_name="brand_clients")
    op.drop_index(op.f("ix_brand_clients_janua_org_id"), table_name="brand_clients")
    op.drop_table("brand_clients")
