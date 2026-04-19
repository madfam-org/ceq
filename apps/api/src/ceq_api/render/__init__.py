"""
ceq render pipeline.

Deterministic template-based asset generation with R2 caching.

Input (template + data) is hashed; identical inputs map to identical R2 keys,
so repeated calls return the cached URL without re-rendering.

The API is stateless — renders are not persisted in the DB. Callers who need
to associate a render with a domain record (e.g. a Rondelio card) should
cache the returned URL on their own record.
"""

from ceq_api.render.cache import RenderCache
from ceq_api.render.hash import render_hash
from ceq_api.render.renderers import registry

__all__ = ["RenderCache", "registry", "render_hash"]
