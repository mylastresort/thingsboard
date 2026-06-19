import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Base model that emits/accepts camelCase JSON (tenantId, createdTime, ...)
    so the existing ui-ngx Claim widgets don't need any changes."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class ClaimTag(CamelModel):
    # Adjust to match your actual ClaimTags shape from the Java side.
    key: str
    value: str


class ClaimBase(CamelModel):
    name: str | None = Field(default=None, max_length=255)
    body: str = Field(..., max_length=10000)
    tags: list[ClaimTag] | None = None


class ClaimCreate(ClaimBase):
    """Body for POST /api/claims. id / tenantId / done are server-assigned,
    same as saveClaim() ignoring the incoming id and forcing done=False."""


class ClaimOut(ClaimBase):
    id: uuid.UUID
    created_time: datetime
    tenant_id: uuid.UUID
    done: bool
    assignee_id: uuid.UUID | None = None


class ClaimsPageData(CamelModel):
    """Same shape as org.thingsboard.server.common.data.page.PageData."""

    data: list[ClaimOut]
    total_pages: int
    total_elements: int
    has_next: bool


class AssignClaimRequest(CamelModel):
    assignee_id: uuid.UUID
