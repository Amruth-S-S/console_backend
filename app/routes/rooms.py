from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from bson import ObjectId
from pymongo import ReturnDocument
from ..db import access_collection, rooms_collection
from ..deps import CurrentUser, get_current_user, user_role_names
from ..schemas import RoomEntryCreate, RoomEntryOut

router = APIRouter(prefix="/rooms", tags=["rooms"])

# Case-insensitive match against whatever the admin named the role on the
# Roles page — "Room List", "room list", "ROOM LIST" all count. Same
# pattern as routes/accounts.py's "account" check.
ROOM_LIST_ROLE_NAME = "room list"


async def require_room_permission(user: CurrentUser, action: str) -> None:
    # action is one of "view"/"create"/"edit"/"delete" — the same four
    # switches admin sets on the Access page (routes/access.py). Holding
    # the Room List role is required first; the granular grant (which
    # defaults to fully-allowed if the admin never restricted it — see
    # access.py's get_access) then narrows it further. Same shape as
    # routes/accounts.py's require_account_permission.
    if user.role == "admin":
        return
    if ROOM_LIST_ROLE_NAME not in await user_role_names(user.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied")
    grant = await access_collection.find_one({"userId": user.id, "roleName": ROOM_LIST_ROLE_NAME})
    if grant is not None and not grant.get(action, True):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied")


def serialize(r: dict) -> RoomEntryOut:
    return RoomEntryOut(
        id=str(r["_id"]),
        createdAt=r.get("createdAt", ""),
        createdBy=r.get("createdBy", ""),
        slNo=r.get("slNo", ""),
        packageType=r.get("packageType", "domestic"),
        packageId=r.get("packageId", ""),
        packageTitle=r.get("packageTitle", ""),
        clientName=r.get("clientName", ""),
        invoiceNumber=r.get("invoiceNumber", ""),
        roomType=r.get("roomType", ""),
        numberOfRooms=r.get("numberOfRooms", ""),
        sharingPerRoom=r.get("sharingPerRoom", ""),
        travelers=r.get("travelers", []),
    )


@router.get("", response_model=list[RoomEntryOut])
async def list_rooms(user: CurrentUser = Depends(get_current_user)):
    await require_room_permission(user, "view")
    items = await rooms_collection.find().sort("_id", -1).to_list(1000)
    return [serialize(r) for r in items]


@router.get("/next-sl-no")
async def next_sl_no(user: CurrentUser = Depends(get_current_user)):
    await require_room_permission(user, "create")
    items = await rooms_collection.find({}, {"slNo": 1}).to_list(5000)
    nums: list[int] = []
    for r in items:
        try:
            nums.append(int(r.get("slNo", "")))
        except (TypeError, ValueError):
            continue
    next_num = (max(nums) + 1) if nums else 1
    return {"slNo": str(next_num)}


@router.post("", response_model=RoomEntryOut, status_code=201)
async def create_room(body: RoomEntryCreate, user: CurrentUser = Depends(get_current_user)):
    await require_room_permission(user, "create")
    doc = body.model_dump()
    doc["createdAt"] = datetime.now(timezone.utc).isoformat()
    doc["createdBy"] = user.id
    res = await rooms_collection.insert_one(doc)
    doc["_id"] = res.inserted_id
    return serialize(doc)


@router.put("/{entry_id}", response_model=RoomEntryOut)
async def update_room(
    entry_id: str, body: RoomEntryCreate, user: CurrentUser = Depends(get_current_user)
):
    await require_room_permission(user, "edit")
    updated = await rooms_collection.find_one_and_update(
        {"_id": ObjectId(entry_id)},
        {"$set": body.model_dump()},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found")
    return serialize(updated)


@router.delete("/{entry_id}", status_code=204)
async def delete_room(entry_id: str, user: CurrentUser = Depends(get_current_user)):
    await require_room_permission(user, "delete")
    res = await rooms_collection.delete_one({"_id": ObjectId(entry_id)})
    if res.deleted_count == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found")
