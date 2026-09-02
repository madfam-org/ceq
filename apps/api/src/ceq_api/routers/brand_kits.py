"""Brand-kit DAM endpoints — the curated, multi-tenant client-brand store.

This router makes ceq the ecosystem's designated **client-brand DAM**: the
system-of-record for a client's source brand book (palette, typography, logos,
usage rules) plus the binary brand assets behind it. It is the storage half;
ceq's existing ``/v1/render`` is the generation half that will later consume
these kits.

Tenancy discipline (security-critical — mirrors acervo's contract)
------------------------------------------------------------------
- The tenant is derived from the **Janua token**, never the URL. No route names a
  tenant in its path/query/header. The caller's ``JanuaUser.org_id`` resolves to
  exactly one :class:`Client`, and every read/write is fenced to that client. A
  caller authenticated for tenant A therefore cannot address tenant B's kit —
  ``{id}`` that belongs to another tenant returns 404 (indistinguishable from a
  non-existent id, so the fence does not leak existence).
- **No destructive verbs.** There is no ``PUT`` and no ``DELETE`` on this router.
  Updates are soft (``PATCH`` bumps a version and updates in place); removal is a
  soft-deactivate via ``PATCH``. Brand history is append/curate-only.
- Management requires an **authenticated human** with a tenant. ``get_current_user``
  already rejects Janua service principals (403), and this router additionally
  requires a non-null ``org_id`` — a person with no tenant has no brand kit to
  manage. (Machine callers consume the read-only ``/tokens`` contract through
  their own tenant once that lane is wired; it is intentionally not opened here.)

The ``/tokens`` export is the deliberate contract surface consumers align on.
"""

import hashlib
import logging
import re
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ceq_api.auth import JanuaUser, get_current_user, require_admin
from ceq_api.db import get_db
from ceq_api.models import BRAND_ASSET_KINDS, BrandAsset, BrandKit, Client
from ceq_api.storage import get_storage

logger = logging.getLogger(__name__)

router = APIRouter()

# Per-file upload ceiling for brand assets. Brand books carry logos, fonts, and
# guideline PDFs — not multi-GB model checkpoints — so a tight cap is correct and
# protects the API from oversized multipart bodies.
MAX_BRAND_ASSET_BYTES = 64 * 1024 * 1024  # 64 MiB


# === Helpers ===============================================================


def _slugify(value: str) -> str:
    """Derive a stable, URL/storage-safe slug from a display name.

    Lowercase, non-alphanumerics collapsed to single dashes, trimmed. Falls back
    to a synthetic slug when the name has no usable characters (e.g. all emoji),
    so a client always has a non-empty key.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug[:80] or f"client-{uuid4().hex[:8]}"


def sanitize_filename(filename: str) -> str:
    """Sanitize an upload filename (path-traversal safe, bounded length).

    Same intent as ``routers.assets.sanitize_filename`` — kept local so this
    router owns its input hardening without importing across router modules.
    """
    filename = filename.replace("/", "_").replace("\\", "_").replace("\x00", "")
    filename = re.sub(r"[^a-zA-Z0-9_.-]", "_", filename).lstrip(".")
    if len(filename) > 200:
        name, ext = filename.rsplit(".", 1) if "." in filename else (filename, "")
        filename = f"{name[:195]}.{ext}" if ext else name[:200]
    return filename or "brand_asset"


async def resolve_tenant(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[JanuaUser, Depends(get_current_user)],
) -> Client:
    """Resolve the caller's active :class:`Client` from the Janua token.

    This is the single choke point that turns a token into a tenant scope. It
    reads ``user.org_id`` (the verified Janua org/tenant claim) — the caller
    never supplies a client id — and returns the active ``Client`` bound to it.

    A caller with no ``org_id`` has no tenant and is refused (403): brand-kit
    management is a tenant capability. An unknown or deactivated org is 404,
    since there is nothing this caller may act on.
    """
    if user.org_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "No tenant on your token. Brand-kit management requires a Janua "
                "organization; ask an admin to provision a brand client for your org."
            ),
        )

    result = await db.execute(
        select(Client).where(
            Client.janua_org_id == user.org_id,
            Client.is_active == True,  # noqa: E712
        )
    )
    client = result.scalar_one_or_none()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active brand client is provisioned for your tenant.",
        )
    return client


async def _load_owned_kit(
    kit_id: UUID,
    db: AsyncSession,
    client: Client,
    *,
    require_active: bool = True,
) -> BrandKit:
    """Load a kit by id, fenced to the caller's tenant.

    A kit that exists but belongs to another tenant returns **404**, not 403 —
    the fence must not reveal that another tenant's id exists. This is the core
    cross-tenant isolation guarantee.
    """
    query = select(BrandKit).where(
        BrandKit.id == kit_id,
        BrandKit.client_id == client.id,
    )
    if require_active:
        query = query.where(BrandKit.is_active == True)  # noqa: E712
    result = await db.execute(query)
    kit = result.scalar_one_or_none()
    if kit is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand kit not found for your tenant.",
        )
    return kit


# === Pydantic models =======================================================


class ClientResponse(BaseModel):
    """The caller's resolved tenant (safe subset — no cross-tenant fields)."""

    id: UUID
    slug: str
    display_name: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ClientProvisionRequest(BaseModel):
    """Admin request to onboard a tenant (bind a Janua org to a brand client).

    This is the one place a ``janua_org_id`` is accepted from the request body —
    and it is **admin-only**. It is tenant provisioning, not tenant-scoped access:
    an operator onboards a client (e.g. CTM) by binding its Janua org. Regular
    brand-kit routes never take an org/client id from the caller; they derive it
    from the token.
    """

    janua_org_id: UUID = Field(description="Janua organization/tenant ID to bind")
    display_name: str = Field(min_length=1, max_length=255)
    slug: str | None = Field(
        default=None,
        description="Optional explicit slug; derived from display_name when omitted",
        max_length=80,
    )


class BrandKitCreate(BaseModel):
    """Initialize a brand kit for the caller's tenant."""

    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    palette: dict[str, Any] = Field(default_factory=dict)
    typography: dict[str, Any] = Field(default_factory=dict)
    guidelines: dict[str, Any] = Field(default_factory=dict)


class BrandKitPatch(BaseModel):
    """Soft update of a kit's structured brand data.

    Every field is optional; only provided fields are applied. Any applied
    change bumps ``version``. ``is_active=False`` soft-deactivates the kit (the
    non-destructive stand-in for delete). ``logos`` maps a logical variant name
    to a BrandAsset id (as a string).
    """

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    palette: dict[str, Any] | None = None
    typography: dict[str, Any] | None = None
    logos: dict[str, str] | None = None
    guidelines: dict[str, Any] | None = None
    is_active: bool | None = None


class BrandKitResponse(BaseModel):
    """Full structured kit (management view)."""

    id: UUID
    client_id: UUID
    name: str
    description: str | None
    version: int
    palette: dict[str, Any]
    typography: dict[str, Any]
    logos: dict[str, Any]
    guidelines: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BrandKitList(BaseModel):
    """The caller tenant's kits."""

    client: ClientResponse
    kits: list[BrandKitResponse]
    total: int


class BrandAssetResponse(BaseModel):
    """A brand binary asset with a resolvable download URL."""

    id: UUID
    brand_kit_id: UUID
    kind: str
    variant: str | None
    filename: str
    content_type: str
    size_bytes: int
    checksum: str | None
    tags: list[str]
    download_url: str = Field(description="Presigned/public URL for the bytes")
    is_active: bool
    created_at: datetime


class BrandAssetList(BaseModel):
    assets: list[BrandAssetResponse]
    total: int


# --- Token export (the consumer contract) ----------------------------------


class TokenLogo(BaseModel):
    """A resolved logo entry in the token export."""

    asset_id: UUID
    kind: str
    variant: str | None
    content_type: str
    url: str = Field(description="Fetchable URL (presigned/public) for the logo bytes")


class BrandTokens(BaseModel):
    """Resolved, consumer-ready brand token document.

    This is the contract MAP, crea-frontend, and the renderer align on. It is
    intentionally flat and self-describing: named palette tokens, typography
    roles, and logos already resolved to fetchable URLs — no R2 knowledge
    required on the consumer side. ``version`` lets a consumer pin the exact
    brand book it aligned against.
    """

    client_slug: str
    kit_id: UUID
    kit_name: str
    version: int
    palette: dict[str, Any] = Field(
        description="role -> hex | {light,dark}. Address by name, e.g. palette['brand']."
    )
    typography: dict[str, Any] = Field(
        description="role (heading/body/mono) -> {family, weights, ...}"
    )
    logos: dict[str, TokenLogo] = Field(
        description="logical variant -> resolved logo (url + metadata)"
    )
    guidelines: dict[str, Any]
    generated_at: datetime


# === Response builders =====================================================


async def _asset_to_response(asset: BrandAsset) -> BrandAssetResponse:
    storage = await get_storage()
    # Presigned URL when R2 is configured; public URL otherwise (dev/mock).
    if storage.is_configured:
        url = await storage.generate_download_url(asset.storage_uri, filename=asset.filename)
    else:
        url = storage.get_public_url(asset.storage_uri)
    return BrandAssetResponse(
        id=asset.id,
        brand_kit_id=asset.brand_kit_id,
        kind=asset.kind,
        variant=asset.variant,
        filename=asset.filename,
        content_type=asset.content_type,
        size_bytes=asset.size_bytes,
        checksum=asset.checksum,
        tags=list(asset.tags or []),
        download_url=url,
        is_active=asset.is_active,
        created_at=asset.created_at,
    )


# === Endpoints =============================================================


@router.post(
    "/clients",
    response_model=ClientResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def provision_client(
    data: ClientProvisionRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ClientResponse:
    """Onboard a tenant: bind a Janua org to a brand :class:`Client` (admin only).

    Idempotent-ish by binding: re-provisioning an already-bound org is a 409, so a
    Janua org maps to exactly one client. Slug collisions are also 409. This is
    the only route that reads an org id from the body, and it is admin-gated;
    every tenant-scoped route derives the tenant from the token instead.
    """
    clash = await db.execute(
        select(Client).where(
            Client.janua_org_id == data.janua_org_id
        )
    )
    if clash.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A brand client is already provisioned for that Janua org.",
        )

    slug = _slugify(data.slug or data.display_name)
    slug_clash = await db.execute(select(Client).where(Client.slug == slug))
    if slug_clash.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Slug {slug!r} is already in use; pass an explicit unique slug.",
        )

    client = Client(
        janua_org_id=data.janua_org_id,
        slug=slug,
        display_name=data.display_name,
        is_active=True,
    )
    db.add(client)
    await db.flush()
    await db.refresh(client)
    return ClientResponse.model_validate(client)


@router.get("/me/client", response_model=ClientResponse)
async def get_my_client(
    client: Annotated[Client, Depends(resolve_tenant)],
) -> ClientResponse:
    """Return the caller's resolved tenant (derived from the token)."""
    return ClientResponse.model_validate(client)


@router.get("", response_model=BrandKitList)
async def list_brand_kits(
    db: Annotated[AsyncSession, Depends(get_db)],
    client: Annotated[Client, Depends(resolve_tenant)],
) -> BrandKitList:
    """List the caller tenant's active brand kits.

    Scoped entirely by the resolved tenant — there is no way to ask for another
    tenant's kits.
    """
    result = await db.execute(
        select(BrandKit)
        .where(BrandKit.client_id == client.id, BrandKit.is_active == True)  # noqa: E712
        .order_by(BrandKit.created_at.desc())
    )
    kits = list(result.scalars().all())
    return BrandKitList(
        client=ClientResponse.model_validate(client),
        kits=[BrandKitResponse.model_validate(k) for k in kits],
        total=len(kits),
    )


@router.post("", response_model=BrandKitResponse, status_code=status.HTTP_201_CREATED)
async def create_brand_kit(
    data: BrandKitCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    client: Annotated[Client, Depends(resolve_tenant)],
) -> BrandKitResponse:
    """Create/initialize a brand kit for the caller's tenant.

    The kit is bound to the resolved ``client_id`` — the caller cannot create a
    kit under another tenant. Name collisions within the tenant are 409.
    """
    existing = await db.execute(
        select(func.count())
        .select_from(BrandKit)
        .where(
            BrandKit.client_id == client.id,
            BrandKit.name == data.name,
            BrandKit.is_active == True,  # noqa: E712
        )
    )
    if (existing.scalar() or 0) > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A brand kit named {data.name!r} already exists for your tenant.",
        )

    kit = BrandKit(
        client_id=client.id,
        name=data.name,
        description=data.description,
        version=1,
        palette=data.palette,
        typography=data.typography,
        logos={},
        guidelines=data.guidelines,
        is_active=True,
    )
    db.add(kit)
    await db.flush()
    await db.refresh(kit)
    return BrandKitResponse.model_validate(kit)


@router.get("/{kit_id}", response_model=BrandKitResponse)
async def get_brand_kit(
    kit_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    client: Annotated[Client, Depends(resolve_tenant)],
) -> BrandKitResponse:
    """Get one structured kit — 404 unless it belongs to the caller's tenant."""
    kit = await _load_owned_kit(kit_id, db, client)
    return BrandKitResponse.model_validate(kit)


@router.patch("/{kit_id}", response_model=BrandKitResponse)
async def patch_brand_kit(
    kit_id: UUID,
    data: BrandKitPatch,
    db: Annotated[AsyncSession, Depends(get_db)],
    client: Annotated[Client, Depends(resolve_tenant)],
) -> BrandKitResponse:
    """Soft-update a kit's structured brand data (no destructive replace).

    Only provided fields are applied; any applied change bumps ``version``.
    ``is_active=False`` soft-deactivates the kit — the non-destructive stand-in
    for delete. A deactivated kit can still be reactivated via this same route,
    so nothing is lost.
    """
    # require_active=False so a soft-deactivated kit can be reactivated/edited.
    kit = await _load_owned_kit(kit_id, db, client, require_active=False)

    changed = False
    if data.name is not None and data.name != kit.name:
        # Enforce the per-tenant name uniqueness on rename.
        clash = await db.execute(
            select(func.count())
            .select_from(BrandKit)
            .where(
                BrandKit.client_id == client.id,
                BrandKit.name == data.name,
                BrandKit.id != kit.id,
            )
        )
        if (clash.scalar() or 0) > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A brand kit named {data.name!r} already exists for your tenant.",
            )
        kit.name = data.name
        changed = True
    if data.description is not None:
        kit.description = data.description
        changed = True
    if data.palette is not None:
        kit.palette = data.palette
        changed = True
    if data.typography is not None:
        kit.typography = data.typography
        changed = True
    if data.logos is not None:
        # Validate each referenced logo id belongs to THIS kit (tenant fence on
        # references, so a kit can't point its logos at another tenant's asset).
        await _validate_logo_refs(data.logos, kit, db, client)
        kit.logos = dict(data.logos)
        changed = True
    if data.guidelines is not None:
        kit.guidelines = data.guidelines
        changed = True
    if data.is_active is not None:
        kit.is_active = data.is_active
        changed = True

    if changed:
        kit.version += 1

    await db.flush()
    await db.refresh(kit)
    return BrandKitResponse.model_validate(kit)


async def _validate_logo_refs(
    logos: dict[str, str],
    kit: BrandKit,
    db: AsyncSession,
    client: Client,
) -> None:
    """Ensure every logo id in the mapping is an asset of this kit + tenant."""
    for variant, asset_id_str in logos.items():
        try:
            asset_id = UUID(asset_id_str)
        except (ValueError, AttributeError, TypeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"logos[{variant!r}] must be a BrandAsset UUID string.",
            ) from exc
        result = await db.execute(
            select(func.count())
            .select_from(BrandAsset)
            .where(
                BrandAsset.id == asset_id,
                BrandAsset.brand_kit_id == kit.id,
                BrandAsset.client_id == client.id,
            )
        )
        if (result.scalar() or 0) == 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"logos[{variant!r}] references {asset_id_str} which is not an "
                    "asset of this kit."
                ),
            )


@router.post(
    "/{kit_id}/assets",
    response_model=BrandAssetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_brand_asset(
    kit_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    client: Annotated[Client, Depends(resolve_tenant)],
    file: UploadFile = File(...),  # noqa: B008
    kind: str = Form(...),
    variant: str | None = Form(None),
    tags: str = Form(""),
) -> BrandAssetResponse:
    """Upload a binary brand asset (logo, font, guideline PDF, photo) to R2.

    Mirrors ``routers.assets.upload_asset`` but tenant-scoped: the object key is
    fenced under the client slug and kit version, and the row records both the
    kit and (denormalized) tenant. Only the caller's own kit can be targeted.
    """
    if kind not in BRAND_ASSET_KINDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid kind. Must be one of: {', '.join(BRAND_ASSET_KINDS)}",
        )

    kit = await _load_owned_kit(kit_id, db, client)

    storage = await get_storage()
    if not storage.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage not configured. The vault is offline.",
        )

    content = await file.read()
    size_bytes = len(content)
    if size_bytes == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty upload.",
        )
    if size_bytes > MAX_BRAND_ASSET_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum brand asset size is {MAX_BRAND_ASSET_BYTES} bytes.",
        )

    checksum = hashlib.sha256(content).hexdigest()
    asset_id = uuid4()
    safe_filename = sanitize_filename(file.filename or f"{kind}_{asset_id.hex[:8]}")
    content_type = file.content_type or "application/octet-stream"

    # Tenant-scoped, versioned R2 key.
    key = f"brand-kits/{client.slug}/{kit.version}/{kind}/{asset_id.hex}_{safe_filename}"

    try:
        storage_uri = await storage.put_object(
            key=key,
            body=content,
            content_type=content_type,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to upload brand asset to R2: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload to storage.",
        ) from exc

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    asset = BrandAsset(
        id=asset_id,
        brand_kit_id=kit.id,
        client_id=client.id,
        kind=kind,
        variant=variant,
        filename=safe_filename,
        storage_uri=storage_uri,
        content_type=content_type,
        size_bytes=size_bytes,
        checksum=checksum,
        tags=tag_list,
        is_active=True,
    )
    db.add(asset)
    await db.flush()
    await db.refresh(asset)
    return await _asset_to_response(asset)


@router.get("/{kit_id}/assets", response_model=BrandAssetList)
async def list_brand_assets(
    kit_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    client: Annotated[Client, Depends(resolve_tenant)],
    kind: str | None = Query(None, description="Filter by asset kind"),
) -> BrandAssetList:
    """List a kit's active binary assets (tenant-fenced)."""
    kit = await _load_owned_kit(kit_id, db, client)
    query = select(BrandAsset).where(
        BrandAsset.brand_kit_id == kit.id,
        BrandAsset.client_id == client.id,
        BrandAsset.is_active == True,  # noqa: E712
    )
    if kind is not None:
        query = query.where(BrandAsset.kind == kind)
    query = query.order_by(BrandAsset.created_at.desc())
    result = await db.execute(query)
    assets = list(result.scalars().all())
    return BrandAssetList(
        assets=[await _asset_to_response(a) for a in assets],
        total=len(assets),
    )


@router.get("/{kit_id}/assets/{asset_id}", response_model=BrandAssetResponse)
async def get_brand_asset(
    kit_id: UUID,
    asset_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    client: Annotated[Client, Depends(resolve_tenant)],
) -> BrandAssetResponse:
    """Get one brand asset with a fresh download URL (tenant-fenced)."""
    kit = await _load_owned_kit(kit_id, db, client)
    result = await db.execute(
        select(BrandAsset).where(
            BrandAsset.id == asset_id,
            BrandAsset.brand_kit_id == kit.id,
            BrandAsset.client_id == client.id,
            BrandAsset.is_active == True,  # noqa: E712
        )
    )
    asset = result.scalar_one_or_none()
    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand asset not found for your tenant.",
        )
    return await _asset_to_response(asset)


@router.get("/{kit_id}/tokens", response_model=BrandTokens)
async def export_brand_tokens(
    kit_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    client: Annotated[Client, Depends(resolve_tenant)],
) -> BrandTokens:
    """Resolved, consumer-ready brand token document — the ecosystem contract.

    This is what MAP, crea-frontend, and ceq's renderer pull to align on brand.
    It flattens the kit into named palette tokens, typography roles, and logos
    already resolved to fetchable URLs, plus the ``version`` to pin against. No
    R2 knowledge is required on the consumer side.

    Logo resolution: each entry in ``kit.logos`` maps a logical variant name to a
    BrandAsset id; here that id is resolved to a live asset (of this tenant/kit)
    and its download URL. A dangling or deactivated reference is skipped rather
    than failing the whole export, so a half-populated kit still yields usable
    tokens.
    """
    kit = await _load_owned_kit(kit_id, db, client)

    logos: dict[str, TokenLogo] = {}
    if kit.logos:
        # Resolve all referenced ids in one query, then filter to this kit/tenant.
        ref_ids: dict[str, UUID] = {}
        for variant, asset_id_str in kit.logos.items():
            try:
                ref_ids[variant] = UUID(str(asset_id_str))
            except (ValueError, AttributeError, TypeError):
                logger.debug("Kit %s has non-UUID logo ref %r; skipping", kit.id, asset_id_str)
        if ref_ids:
            result = await db.execute(
                select(BrandAsset).where(
                    BrandAsset.id.in_(list(ref_ids.values())),
                    BrandAsset.brand_kit_id == kit.id,
                    BrandAsset.client_id == client.id,
                    BrandAsset.is_active == True,  # noqa: E712
                )
            )
            by_id = {a.id: a for a in result.scalars().all()}
            storage = await get_storage()
            for variant, asset_id in ref_ids.items():
                asset = by_id.get(asset_id)
                if asset is None:
                    continue  # dangling/deactivated ref — skip, don't fail
                if storage.is_configured:
                    url = await storage.generate_download_url(
                        asset.storage_uri, filename=asset.filename
                    )
                else:
                    url = storage.get_public_url(asset.storage_uri)
                logos[variant] = TokenLogo(
                    asset_id=asset.id,
                    kind=asset.kind,
                    variant=asset.variant,
                    content_type=asset.content_type,
                    url=url,
                )

    return BrandTokens(
        client_slug=client.slug,
        kit_id=kit.id,
        kit_name=kit.name,
        version=kit.version,
        palette=dict(kit.palette or {}),
        typography=dict(kit.typography or {}),
        logos=logos,
        guidelines=dict(kit.guidelines or {}),
        generated_at=datetime.utcnow(),
    )
