from typing import Callable, Optional
from fastapi import HTTPException
from uuid import UUID
from app.services.storage import load_versions


def fetch_record(
    record_type: str,
    schema,
    record_id: UUID,
    *,
    permission_check: Optional[Callable[[dict], None]] = None,
    history: bool = False,
    page: dict | None = None,
    sort_by: str = "updated_at",
):
    """
    Fetch a resource by id (current or history), enforce permission on current,
    and optionally paginate history.

    - record_type: e.g., "accounts", "debts", "entries"
    - schema: your Pydantic storage schema (e.g., Debt, Entry)
    - record_id: id as string
    - permission_check: callable(row_dict) -> None (raise HTTPException if forbidden)
    - history: if True, return list[dict] of versions; else return the current row dict
    - page: {"limit": int, "offset": int} when history=True
    - sort_by: column to sort versions desc
    """
    df = load_versions(record_type, schema, record_id=record_id)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"{record_type[:-1].capitalize()} not found")

    current = df[(df["is_current"]) & (~df.get("is_deleted", False).fillna(False))]
    if current.empty:
        raise HTTPException(status_code=404, detail=f"{record_type[:-1].capitalize()} not found")

    # Permission check on the current row
    row = current.iloc[0].to_dict()
    if permission_check:
        permission_check(row)

    if not history:
        return row

    # History mode (sorted, paginated)
    versions = df.sort_values(by=sort_by, ascending=False)
    if page:
        start = page["offset"]
        end = start + page["limit"]
        versions = versions.iloc[start:end]
    return versions.to_dict(orient="records")
