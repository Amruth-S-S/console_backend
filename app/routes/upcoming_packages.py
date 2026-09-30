from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from bson import ObjectId
from pymongo import ReturnDocument
from ..db import upcoming_packages_collection
from ..deps import CurrentUser, get_current_user
from ..schemas import UpcomingPackageCreate, UpcomingPackageOut

router = APIRouter(prefix="/upcoming-packages", tags=["upcoming-packages"])


def require_admin(user: CurrentUser) -> None:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")


def _oid(entry_id: str) -> ObjectId:
    if not ObjectId.is_valid(entry_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found")
    return ObjectId(entry_id)


def serialize(d: dict) -> UpcomingPackageOut:
    return UpcomingPackageOut(
        id=str(d["_id"]),
        createdAt=d.get("createdAt", ""),
        month=d.get("month", ""),
        dates=d.get("dates", ""),
        packageName=d.get("packageName", ""),
        landCost=d.get("landCost", ""),
    )


@router.get("", response_model=list[UpcomingPackageOut])
async def list_upcoming(user: CurrentUser = Depends(get_current_user)):
    # Every logged-in user reads this (Overview dashboard strip); only admin
    # can change it. Soonest month first.
    items = await upcoming_packages_collection.find().sort([("month", 1), ("_id", 1)]).to_list(500)
    return [serialize(d) for d in items]


@router.post("", response_model=UpcomingPackageOut, status_code=201)
async def create_upcoming(body: UpcomingPackageCreate, user: CurrentUser = Depends(get_current_user)):
    require_admin(user)
    doc = body.model_dump()
    doc["createdAt"] = datetime.now(timezone.utc).isoformat()
    res = await upcoming_packages_collection.insert_one(doc)
    doc["_id"] = res.inserted_id
    return serialize(doc)


@router.put("/{entry_id}", response_model=UpcomingPackageOut)
async def update_upcoming(
    entry_id: str, body: UpcomingPackageCreate, user: CurrentUser = Depends(get_current_user)
):
    require_admin(user)
    updated = await upcoming_packages_collection.find_one_and_update(
        {"_id": _oid(entry_id)},
        {"$set": body.model_dump()},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found")
    return serialize(updated)


@router.delete("/{entry_id}", status_code=204)
async def delete_upcoming(entry_id: str, user: CurrentUser = Depends(get_current_user)):
    require_admin(user)
    res = await upcoming_packages_collection.delete_one({"_id": _oid(entry_id)})
    if res.deleted_count == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found")
