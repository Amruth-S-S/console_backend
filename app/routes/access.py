from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from bson import ObjectId
from ..db import access_collection, users_collection
from ..deps import CurrentUser, get_current_user
from ..schemas import AccessOut, AccessUpdate
from .users import _effective_role_ids, require_admin, role_name_map

router = APIRouter(prefix="/access", tags=["access"])

# Only roles that actually gate a real CRUD feature get a section on the
# Access page — a role like "Team Lead" has its own separate, differently
# shaped booking-visibility rule (see routes/bookings.py's _is_team_lead)
# rather than a view/create/edit/delete grant, so it's deliberately left
# out here.
GOVERNED_ROLES = {"account", "currency"}


async def _build_access_out(user_id: str, user_doc: dict) -> AccessOut:
    roles_by_id = await role_name_map()
    role_names = [roles_by_id[rid] for rid in _effective_role_ids(user_doc) if roles_by_id.get(rid)]
    governed_names = [rn for rn in role_names if rn.strip().lower() in GOVERNED_ROLES]

    grants = []
    for role_name in governed_names:
        key = role_name.strip().lower()
        existing = await access_collection.find_one({"userId": user_id, "roleName": key})
        # No record yet means this role has never been restricted — full
        # access, matching how it behaved before this feature existed.
        grants.append(
            {
                "roleName": role_name,
                "view": existing.get("view", True) if existing else True,
                "create": existing.get("create", True) if existing else True,
                "edit": existing.get("edit", True) if existing else True,
                "delete": existing.get("delete", True) if existing else True,
            }
        )
    return AccessOut(userId=user_id, userName=user_doc.get("name", ""), grants=grants)


@router.get("/me", response_model=AccessOut)
async def get_my_access(user: CurrentUser = Depends(get_current_user)):
    # Self-service, no admin check — lets the Account/Currency pages hide
    # buttons for actions this login isn't actually granted, instead of
    # just letting the request 403 after the fact. Declared before
    # "/{user_id}" so FastAPI doesn't treat "me" as a user id.
    user_doc = await users_collection.find_one({"_id": ObjectId(user.id)})
    if not user_doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return await _build_access_out(user.id, user_doc)


@router.get("/{user_id}", response_model=AccessOut)
async def get_access(user_id: str, user: CurrentUser = Depends(get_current_user)):
    require_admin(user)
    user_doc = await users_collection.find_one({"_id": ObjectId(user_id)})
    if not user_doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return await _build_access_out(user_id, user_doc)


@router.put("/{user_id}", response_model=AccessOut)
async def set_access(user_id: str, body: AccessUpdate, user: CurrentUser = Depends(get_current_user)):
    require_admin(user)
    user_doc = await users_collection.find_one({"_id": ObjectId(user_id)})
    if not user_doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    for grant in body.grants:
        key = grant.roleName.strip().lower()
        if key not in GOVERNED_ROLES:
            continue
        await access_collection.update_one(
            {"userId": user_id, "roleName": key},
            {
                "$set": {
                    "view": grant.view,
                    "create": grant.create,
                    "edit": grant.edit,
                    "delete": grant.delete,
                    "updatedAt": datetime.now(timezone.utc).isoformat(),
                }
            },
            upsert=True,
        )
    return await _build_access_out(user_id, user_doc)
