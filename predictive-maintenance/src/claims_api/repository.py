import uuid

from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import ClaimEntity
from .pagination import PageLink
from .schemas import ClaimCreate, ClaimOut, ClaimsPageData

SORTABLE_COLUMNS = {
    "name": ClaimEntity.name,
    "createdTime": ClaimEntity.created_time,
}


async def find_tenant_claims(
    db: AsyncSession, tenant_id: uuid.UUID, page_link: PageLink
) -> ClaimsPageData:
    """Equivalent of ClaimRepository.findClaims (ilike textSearch on name)."""
    stmt = select(ClaimEntity).where(ClaimEntity.tenant_id == tenant_id)
    count_stmt = (
        select(func.count())
        .select_from(ClaimEntity)
        .where(ClaimEntity.tenant_id == tenant_id)
    )

    if page_link.text_search:
        pattern = f"%{page_link.text_search}%"
        stmt = stmt.where(ClaimEntity.name.ilike(pattern))
        count_stmt = count_stmt.where(ClaimEntity.name.ilike(pattern))

    sort_col = SORTABLE_COLUMNS.get(page_link.sort_property, ClaimEntity.created_time)
    sort_fn = desc if (page_link.sort_order or "ASC").upper() == "DESC" else asc
    stmt = stmt.order_by(sort_fn(sort_col)).offset(page_link.offset).limit(page_link.page_size)

    total_elements = (await db.execute(count_stmt)).scalar_one()
    rows = (await db.execute(stmt)).scalars().all()

    total_pages = (
        (total_elements + page_link.page_size - 1) // page_link.page_size
        if page_link.page_size
        else 0
    )
    has_next = (page_link.page + 1) * page_link.page_size < total_elements

    return ClaimsPageData(
        data=[ClaimOut.model_validate(r) for r in rows],
        total_pages=total_pages,
        total_elements=total_elements,
        has_next=has_next,
    )


async def get_tenant_claim(
    db: AsyncSession, tenant_id: uuid.UUID, claim_id: uuid.UUID
) -> ClaimEntity | None:
    """Equivalent of ClaimRepository.findClaim."""
    stmt = select(ClaimEntity).where(
        ClaimEntity.tenant_id == tenant_id, ClaimEntity.id == claim_id
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def create_claim(
    db: AsyncSession, tenant_id: uuid.UUID, claim_in: ClaimCreate
) -> ClaimEntity:
    entity = ClaimEntity(
        tenant_id=tenant_id,
        name=claim_in.name,
        body=claim_in.body,
        done=False,
        tags=[t.model_dump(by_alias=True) for t in claim_in.tags] if claim_in.tags else None,
    )
    db.add(entity)
    await db.commit()
    await db.refresh(entity)
    return entity


async def delete_claim(db: AsyncSession, entity: ClaimEntity) -> None:
    await db.delete(entity)
    await db.commit()


async def toggle_claim(db: AsyncSession, entity: ClaimEntity) -> ClaimEntity:
    """Equivalent of JpaClaimDao.toggleClaim."""
    entity.done = not entity.done
    await db.commit()
    await db.refresh(entity)
    return entity


async def assign_claim(
    db: AsyncSession, entity: ClaimEntity, assignee_id: uuid.UUID
) -> ClaimEntity:
    """Equivalent of JpaClaimDao.assignClaim."""
    entity.assignee_id = assignee_id
    await db.commit()
    await db.refresh(entity)
    return entity
