from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from bson import ObjectId
from pymongo import ReturnDocument
from ..db import access_collection, dmc_accounts_collection
from ..deps import CurrentUser, get_current_user, user_role_names
from ..schemas import ApprovalUpdate, DmcAccountCreate, DmcAccountOut

router = APIRouter(prefix="/dmc-accounts", tags=["dmc-accounts"])

# Case-insensitive match against whatever the admin named the role on the
# Roles page — "DMC Account", "dmc account", ... all count. Same pattern as
# routes/accounts.py and routes/currency_entries.py.
DMC_ROLE_NAME = "dmc account"


async def require_dmc_permission(user: CurrentUser, action: str) -> None:
    # Same shape as routes/accounts.py's require_account_permission.
    # action is "view"/"create"/"edit"/"delete" — the Access page switches.
    if user.role == "admin":
        return
    if DMC_ROLE_NAME not in await user_role_names(user.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied")
    grant = await access_collection.find_one({"userId": user.id, "roleName": DMC_ROLE_NAME})
    if grant is not None and not grant.get(action, True):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied")


def require_admin(user: CurrentUser) -> None:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")


def _oid(entry_id: str) -> ObjectId:
    if not ObjectId.is_valid(entry_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found")
    return ObjectId(entry_id)


def serialize(d: dict) -> DmcAccountOut:
    fields = {k: d.get(k, "") for k in DmcAccountCreate.model_fields}
    return DmcAccountOut(
        id=str(d["_id"]),
        createdAt=d.get("createdAt", ""),
        createdBy=d.get("createdBy", ""),
        approved=bool(d.get("approved", False)),
        **fields,
    )


@router.get("", response_model=list[DmcAccountOut])
async def list_dmc_accounts(user: CurrentUser = Depends(get_current_user)):
    await require_dmc_permission(user, "view")
    items = await dmc_accounts_collection.find().sort("_id", -1).to_list(1000)
    return [serialize(d) for d in items]


@router.get("/next-sl-no")
async def next_sl_no(user: CurrentUser = Depends(get_current_user)):
    await require_dmc_permission(user, "create")
    items = await dmc_accounts_collection.find({}, {"slNo": 1}).to_list(5000)
    nums: list[int] = []
    for d in items:
        try:
            nums.append(int(d.get("slNo", "")))
        except (TypeError, ValueError):
            continue
    return {"slNo": str((max(nums) + 1) if nums else 1)}


@router.post("", response_model=DmcAccountOut, status_code=201)
async def create_dmc_account(body: DmcAccountCreate, user: CurrentUser = Depends(get_current_user)):
    await require_dmc_permission(user, "create")
    doc = body.model_dump()
    doc["createdAt"] = datetime.now(timezone.utc).isoformat()
    doc["createdBy"] = user.id
    doc["approved"] = False
    res = await dmc_accounts_collection.insert_one(doc)
    doc["_id"] = res.inserted_id
    return serialize(doc)


@router.put("/{entry_id}/approval", response_model=DmcAccountOut)
async def set_approval(
    entry_id: str, body: ApprovalUpdate, user: CurrentUser = Depends(get_current_user)
):
    # Admin-only — the DMC Account role sees the status but can't flip it.
    require_admin(user)
    updated = await dmc_accounts_collection.find_one_and_update(
        {"_id": _oid(entry_id)},
        {"$set": {"approved": body.approved}},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found")
    return serialize(updated)


@router.put("/{entry_id}", response_model=DmcAccountOut)
async def update_dmc_account(
    entry_id: str, body: DmcAccountCreate, user: CurrentUser = Depends(get_current_user)
):
    # approved/createdBy/createdAt untouched, same as accounts.py.
    await require_dmc_permission(user, "edit")
    updated = await dmc_accounts_collection.find_one_and_update(
        {"_id": _oid(entry_id)},
        {"$set": body.model_dump()},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found")
    return serialize(updated)


@router.delete("/{entry_id}", status_code=204)
async def delete_dmc_account(entry_id: str, user: CurrentUser = Depends(get_current_user)):
    await require_dmc_permission(user, "delete")
    res = await dmc_accounts_collection.delete_one({"_id": _oid(entry_id)})
    if res.deleted_count == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found")
