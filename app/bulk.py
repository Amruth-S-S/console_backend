"""CSV bulk import shared by every list page (POST /<resource>/bulk-import).

The whole file arrives as one request. Pydantic validates every row first —
a single invalid row rejects the request (422) before anything is saved.
Valid rows are then created one by one through the resource's normal create
function, so numbering, syncing (e.g. booking -> account ledger) and
permission checks behave exactly as when adding a record by hand. Rows the
create function itself refuses (e.g. a duplicate email) are reported back
with their row number instead of aborting the rest.
"""
from typing import Awaitable, Callable, Generic, TypeVar
from fastapi import HTTPException
from pydantic import BaseModel, Field

from .deps import CurrentUser

T = TypeVar("T", bound=BaseModel)

MAX_IMPORT_ROWS = 1000


class BulkImport(BaseModel, Generic[T]):
    items: list[T] = Field(min_length=1, max_length=MAX_IMPORT_ROWS)


class BulkRowError(BaseModel):
    row: int  # 1-based data row in the CSV (header row not counted)
    error: str


class BulkImportResult(BaseModel):
    created: int
    errors: list[BulkRowError] = Field(default_factory=list)


async def run_bulk(
    items: list[T],
    create: Callable[[T, CurrentUser], Awaitable[object]],
    user: CurrentUser,
) -> BulkImportResult:
    created = 0
    errors: list[BulkRowError] = []
    for i, item in enumerate(items, start=1):
        try:
            await create(item, user)
            created += 1
        except HTTPException as e:
            errors.append(BulkRowError(row=i, error=str(e.detail)))
    return BulkImportResult(created=created, errors=errors)
