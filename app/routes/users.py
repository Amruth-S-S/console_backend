from fastapi import APIRouter, Depends, HTTPException, status
from bson import ObjectId
from pymongo import ReturnDocument
from ..db import users_collection
from ..deps import CurrentUser, get_current_user
from ..schemas import UserCreate, UserOut, UserUpdate
from ..security import hash_password

router = APIRouter(prefix="/users", tags=["users"])


def require_admin(user: CurrentUser) -> None:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")


def serialize(u: dict) -> UserOut:
    return UserOut(
        id=str(u["_id"]),
        name=u["name"],
        email=u["email"],
        phone=u.get("phone"),
        role=u["role"],
    )


@router.get("", response_model=list[UserOut])
async def list_users(user: CurrentUser = Depends(get_current_user)):
    # Any logged-in user (not just admins) — the booking form's "Booked by"
    # / user-assignment UI reads this list too, it just renders it read-only
    # for non-admins.
    items = await users_collection.find().sort("_id", -1).to_list(500)
    return [serialize(u) for u in items]


@router.post("", response_model=UserOut, status_code=201)
async def create_user(body: UserCreate, user: CurrentUser = Depends(get_current_user)):
    require_admin(user)
    email = body.email.lower()
    if await users_collection.find_one({"email": email}):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already exists")
    doc = {
        "name": body.name,
        "email": email,
        "phone": body.phone,
        "password": hash_password(body.password),
        "role": "user",
    }
    res = await users_collection.insert_one(doc)
    doc["_id"] = res.inserted_id
    return serialize(doc)


@router.put("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: str, body: UserUpdate, user: CurrentUser = Depends(get_current_user)
):
    require_admin(user)
    update = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
    if not update:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields to update")

    if "password" in update:
        update["password"] = hash_password(update["password"])

    if "email" in update:
        email = update["email"].lower()
        existing = await users_collection.find_one(
            {"email": email, "_id": {"$ne": ObjectId(user_id)}}
        )
        if existing:
            raise HTTPException(status.HTTP_409_CONFLICT, "Email already exists")
        update["email"] = email

    updated = await users_collection.find_one_and_update(
        {"_id": ObjectId(user_id)},
        {"$set": update},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return serialize(updated)


@router.delete("/{user_id}", status_code=204)
async def delete_user(user_id: str, user: CurrentUser = Depends(get_current_user)):
    require_admin(user)
    res = await users_collection.delete_one(
        {"_id": ObjectId(user_id), "role": "user"}
    )
    if res.deleted_count == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
