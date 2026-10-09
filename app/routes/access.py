from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from bson import ObjectId
from ..db import access_collection, users_collection
from ..deps import CurrentUser, get_current_user
from ..schemas import AccessOut, AccessUpdate, MenuAccessOut, MenuAccessUpdate
from ..menus import MENU_ACCESS, granted_menus, menu_labels
from .users import _effective_role_ids, require_admin, role_name_map

router = APIRouter(prefix="/access", tags=["access"])

async def _build_access_out(user_id: str, user_doc: dict) -> AccessOut:
    # Every role actually assigned to this person gets a section — not just
    # the ones a route currently enforces. A role like "Team Lead" has its
    # own separate, differently shaped booking-visibility rule (see
    # routes/bookings.py's _is_team_lead) rather than a view/create/edit/
    # delete grant, so its checkboxes are shown but currently unused;
    # "Account"/"Currency"/"Room List" are each enforced by their own route.
    roles_by_id = await role_name_map()
    role_names = [roles_by_id[rid] for rid in _effective_role_ids(user_doc) if roles_by_id.get(rid)]
    # Menus granted directly get a permission card too (same key as the role
    # of that name) — skipped if the user already holds that role.
    have = {n.strip().lower() for n in role_names}
    role_names += [label for label in menu_labels(user_doc) if label.strip().lower() not in have]

    grants = []
    for role_name in role_names:
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
        if not key:
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


@router.get("/{user_id}/menus", response_model=MenuAccessOut)
async def get_menu_access(user_id: str, user: CurrentUser = Depends(get_current_user)):
    require_admin(user)
    user_doc = await users_collection.find_one({"_id": ObjectId(user_id)})
    if not user_doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return MenuAccessOut(userId=user_id, menus=granted_menus(user_doc))


@router.put("/{user_id}/menus", response_model=MenuAccessOut)
async def set_menu_access(user_id: str, body: MenuAccessUpdate, user: CurrentUser = Depends(get_current_user)):
    require_admin(user)
    unknown = [m for m in body.menus if m not in MENU_ACCESS]
    if unknown:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown menu: {', '.join(unknown)}")
    menus = [k for k in MENU_ACCESS if k in set(body.menus)]
    updated = await users_collection.find_one_and_update(
        {"_id": ObjectId(user_id)},
        {"$set": {"menuAccess": menus}},
        return_document=True,
    )
    if not updated:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return MenuAccessOut(userId=user_id, menus=granted_menus(updated))
