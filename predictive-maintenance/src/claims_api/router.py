import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from . import repository
from .database import get_db
from .dependencies.auth import CurrentUser, require_tenant_admin
from .pagination import PageLink
from .schemas import AssignClaimRequest, ClaimCreate, ClaimOut, ClaimsPageData

router = APIRouter(prefix="/api", tags=["claims"])


@router.get("/claims", response_model=ClaimsPageData)
async def get_claims(
    page_size: int = Query(..., alias="pageSize", description="The number of items to return"),
    page: int = Query(..., description="The page number"),
    sort_property: Literal["name", "createdTime"] | None = Query(None, alias="sortProperty"),
    sort_order: Literal["ASC", "DESC"] | None = Query(None, alias="sortOrder"),
    text_search: str | None = Query(None, alias="textSearch"),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_tenant_admin),
):
    """Equivalent of getClaims(): gets all claims per tenant."""
    page_link = PageLink(
        page_size=page_size,
        page=page,
        text_search=text_search,
        sort_property=sort_property,
        sort_order=sort_order,
    )
    return await repository.find_tenant_claims(db, user.tenant_id, page_link)


@router.post("/claims", response_model=ClaimOut, status_code=status.HTTP_201_CREATED)
async def save_claim(
    claim_in: ClaimCreate,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_tenant_admin),
):
    """Equivalent of saveClaim(): create new claim, always starts done=False."""
    return await repository.create_claim(db, user.tenant_id, claim_in)


@router.delete("/claims/{claim_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_claim(
    claim_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_tenant_admin),
):
    """Equivalent of deleteClaim()."""
    entity = await repository.get_tenant_claim(db, user.tenant_id, claim_id)
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")
    await repository.delete_claim(db, entity)


@router.patch("/claims/{claim_id}/switch", response_model=ClaimOut)
async def toggle_claim(
    claim_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_tenant_admin),
):
    """Equivalent of toggleClaim(): flips done/not-done."""
    entity = await repository.get_tenant_claim(db, user.tenant_id, claim_id)
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")
    return await repository.toggle_claim(db, entity)


@router.patch("/claims/{claim_id}/assign", response_model=ClaimOut)
async def assign_claim(
    claim_id: uuid.UUID,
    body: AssignClaimRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_tenant_admin),
):
    """Equivalent of assignClaim(). Pydantic gives us 422 validation for free
    instead of the manual `assigneeId` null-check / IllegalArgumentException."""
    entity = await repository.get_tenant_claim(db, user.tenant_id, claim_id)
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")
    return await repository.assign_claim(db, entity, body.assignee_id)
