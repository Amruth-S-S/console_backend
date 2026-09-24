from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from bson import ObjectId
from pymongo import ReturnDocument
from ..db import roles_collection
from ..deps import CurrentUser, get_current_user
from ..schemas import RoleCreate, RoleOut

router = APIRouter(prefix="/roles", tags=["roles"])


def require_admin(user: CurrentUser) -> None:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")


def serialize(r: dict) -> RoleOut:
    return RoleOut(id=str(r["_id"]), name=r.get("name", ""), createdAt=r.get("createdAt", ""))


@router.get("", response_model=list[RoleOut])
async def list_roles(user: CurrentUser = Depends(get_current_user)):
    require_admin(user)
    items = await roles_collection.find().sort("_id", -1).to_list(500)
    return [serialize(r) for r in items]


@router.post("", response_model=RoleOut, status_code=201)
async def create_role(body: RoleCreate, user: CurrentUser = Depends(get_current_user)):
    require_admin(user)
    name = body.name.strip()
    if await roles_collection.find_one({"name": name}):
        raise HTTPException(status.HTTP_409_CONFLICT, "A role with this name already exists")
    doc = {"name": name, "createdAt": datetime.now(timezone.utc).isoformat()}
    res = await roles_collection.insert_one(doc)
    doc["_id"] = res.inserted_id
    return serialize(doc)


@router.put("/{role_id}", response_model=RoleOut)
async def update_role(role_id: str, body: RoleCreate, user: CurrentUser = Depends(get_current_user)):
    require_admin(user)
    name = body.name.strip()
    existing = await roles_collection.find_one({"name": name, "_id": {"$ne": ObjectId(role_id)}})
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "A role with this name already exists")
    updated = await roles_collection.find_one_and_update(
        {"_id": ObjectId(role_id)},
        {"$set": {"name": name}},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")
    return serialize(updated)


@router.delete("/{role_id}", status_code=204)
async def delete_role(role_id: str, user: CurrentUser = Depends(get_current_user)):
    require_admin(user)
    res = await roles_collection.delete_one({"_id": ObjectId(role_id)})
    if res.deleted_count == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")
