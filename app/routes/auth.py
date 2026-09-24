from fastapi import APIRouter, HTTPException, status
from bson import ObjectId
from ..db import roles_collection, users_collection
from ..schemas import LoginRequest, TokenResponse, UserOut
from ..security import verify_password, create_token

router = APIRouter(prefix="/auth", tags=["auth"])


async def serialize(u: dict) -> UserOut:
    role_id = u.get("roleId") or ""
    role_name = ""
    if role_id:
        # One extra lookup, only on login (not on every request) — the
        # frontend persists this in localStorage, so it doesn't re-resolve
        # per page load either. Falls back to "" if the role was since
        # deleted or the id doesn't parse, rather than failing login.
        try:
            role_doc = await roles_collection.find_one({"_id": ObjectId(role_id)})
            role_name = role_doc.get("name", "") if role_doc else ""
        except Exception:
            role_name = ""
    return UserOut(
        id=str(u["_id"]),
        name=u["name"],
        email=u["email"],
        phone=u.get("phone"),
        role=u["role"],
        roleId=role_id,
        roleName=role_name,
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    user = await users_collection.find_one({"email": body.email.lower()})
    if not user or not verify_password(body.password, user["password"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    token = create_token(str(user["_id"]), user["role"])
    return TokenResponse(access_token=token, user=await serialize(user))
