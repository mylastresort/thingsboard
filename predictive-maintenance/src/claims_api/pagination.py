from dataclasses import dataclass
from typing import Literal


@dataclass
class PageLink:
    """Equivalent of org.thingsboard.server.common.data.page.PageLink,
    trimmed to what the claims endpoints actually use."""

    page_size: int
    page: int
    text_search: str | None = None
    sort_property: Literal["name", "createdTime"] | None = None
    sort_order: Literal["ASC", "DESC"] | None = None

    @property
    def offset(self) -> int:
        return self.page * self.page_size
