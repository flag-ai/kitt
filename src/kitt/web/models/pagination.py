"""Pagination and filtering models."""

from pydantic import BaseModel, Field


class FilterParams(BaseModel):
    """Common filter parameters for list endpoints."""

    model: str = ""
    engine: str = ""
    status: str = ""
    suite_name: str = ""
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=25, ge=1, le=100)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page


class PaginatedResponse(BaseModel):
    """Wrapper for paginated list responses."""

    items: list = Field(default_factory=list)
    total: int = 0
    page: int = 1
    per_page: int = 25
    pages: int = 0
