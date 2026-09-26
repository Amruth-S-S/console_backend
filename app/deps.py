from bson import ObjectId
from fastapi import Header, HTTPException, status
from jose import JWTError
from .security import decode_token


class CurrentUser:
    def __init__(self, id: str, role: str):
        self.id = id
        self.role = role


async def get_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing or invalid authorization header")
    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_token(token)
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    sub = payload.get("sub")
    role = payload.get("role")
    if not sub or not role:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token payload")
    return CurrentUser(id=sub, role=role)


def _effective_role_ids(user_doc: dict) -> list[str]:
    # A user can now be assigned several custom roles at once (roleIds) —
    # older accounts saved before that change only have the original
    # singular "roleId" field, so fall back to that as a one-item list
    # rather than requiring a migration script.
    ids = user_doc.get("roleIds")
    if ids is not None:
        return [i for i in ids if i]
    single = user_doc.get("roleId")
    return [single] if single else []


async def user_role_names(user_id: str) -> set[str]:
    # Shared by every "does this account have custom role X" check
    # (routes/accounts.py, routes/currency_entries.py, routes/bookings.py's
    # Team Lead gate) — case-insensitive/trimmed, returned as a set so a
    # caller can just do `TARGET_NAME in names`.
    from .db import roles_collection, users_collection  # local import avoids a cycle at module load

    user_doc = await users_collection.find_one({"_id": ObjectId(user_id)})
    role_ids = _effective_role_ids(user_doc) if user_doc else []
    if not role_ids:
        return set()
    object_ids = []
    for rid in role_ids:
        try:
            object_ids.append(ObjectId(rid))
        except Exception:
            continue
    if not object_ids:
        return set()
    role_docs = await roles_collection.find({"_id": {"$in": object_ids}}).to_list(50)
    return {(r.get("name", "") or "").strip().lower() for r in role_docs}
