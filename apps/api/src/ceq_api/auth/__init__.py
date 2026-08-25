"""Authentication and authorization for ceq-api.

Two principal shapes reach the routers:

- ``get_current_user`` — a **human** Janua user (authorization_code grant).
  Service credentials are rejected with 403 here.
- ``get_service_or_user`` — a human user **or** a Janua service principal
  (``client_credentials`` grant, machine-to-machine). Used by the render, jobs
  and template surfaces so batch drivers can run without a browser session.
- ``get_worker_principal`` — a machine principal **only**, and only one holding
  the dedicated worker scope (``ceq:worker``). Backs ``/v1/worker/*``, the GPU
  job-lease surface. Humans are 403 here, and a ``ceq:render`` token is 403 too:
  submitting work and executing work are separate capabilities.

See ``ceq_api.auth.janua`` for the accepted claim shape.
"""

from ceq_api.auth.janua import (
    JanuaUser,
    get_current_user,
    get_service_or_user,
    get_worker_principal,
    require_admin,
    require_auth,
    service_principal_id,
)

__all__ = [
    "JanuaUser",
    "get_current_user",
    "get_service_or_user",
    "get_worker_principal",
    "require_admin",
    "require_auth",
    "service_principal_id",
]
