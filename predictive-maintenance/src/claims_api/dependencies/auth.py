import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer()


@dataclass
class CurrentUser:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    authority: str


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> CurrentUser:
    """Stand-in for BaseController.getCurrentUser().

    Since you're planning to front this with the ThingsBoard Node API rather
    than hand-roll auth, this is intentionally left unimplemented. When you
    do need it standalone: decode/verify `credentials.credentials` (TB issues
    a standard JWT) and pull tenantId / userId / authority out of the claims.
    """
    raise NotImplementedError(
        "Wire this up to real JWT verification, or drop this dependency "
        "entirely if requests are coming in pre-authenticated via the "
        "ThingsBoard Node API gateway."
    )


def require_tenant_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.authority != "TENANT_ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    return user
