from fastapi import APIRouter, Depends, HTTPException, status
from bson import ObjectId
from ..db import roles_collection, users_collection
from ..schemas import LoginRequest, TokenResponse, UserOut
from ..security import verify_password, create_token
from ..deps import CurrentUser, get_current_user
from ..menus import granted_menus

router = APIRouter(prefix="/auth", tags=["auth"])


def _effective_role_ids(u: dict) -> list[str]:
    # Same fallback as deps.py's user_role_names — a user can hold several
    # roles now (roleIds), but accounts saved before that change only have
    # the original singular "roleId" field.
    ids = u.get("roleIds")
    if ids is not None:
        return [i for i in ids if i]
    single = u.get("roleId")
    return [single] if single else []


async def serialize(u: dict) -> UserOut:
    role_ids = _effective_role_ids(u)
    role_names: list[str] = []
    if role_ids:
        # One extra lookup, only on login (not on every request) — the
        # frontend persists this in localStorage, so it doesn't re-resolve
        # per page load either. Ids that no longer resolve (role since
        # deleted, bad ObjectId) are silently skipped rather than failing
        # login.
        try:
            object_ids = [ObjectId(rid) for rid in role_ids]
            role_docs = await roles_collection.find({"_id": {"$in": object_ids}}).to_list(50)
            role_names = [r.get("name", "") for r in role_docs if r.get("name")]
        except Exception:
            role_names = []
    return UserOut(
        id=str(u["_id"]),
        name=u["name"],
        email=u["email"],
        phone=u.get("phone"),
        role=u["role"],
        roleIds=role_ids,
        roleNames=role_names,
        menuAccess=granted_menus(u),
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    user = await users_collection.find_one({"email": body.email.lower()})
    if not user or not verify_password(body.password, user["password"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    token = create_token(str(user["_id"]), user["role"])
    return TokenResponse(access_token=token, user=await serialize(user))


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser = Depends(get_current_user)):
    # The frontend re-reads this on every page load, so role and menu
    # changes made by an admin apply on the user's next refresh instead of
    # only after they log out and back in.
    u = await users_collection.find_one({"_id": ObjectId(user.id)})
    if not u:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return await serialize(u)
