from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from bson import ObjectId
from pymongo import ReturnDocument
from ..db import access_collection, hotel_vouchers_collection
from ..deps import CurrentUser, get_current_user, user_role_names
from ..schemas import HotelVoucherCreate, HotelVoucherOut

router = APIRouter(prefix="/hotel-vouchers", tags=["hotel-vouchers"])

# Case-insensitive match against the role name admin creates on the Roles
# page — "Hotel Voucher", "hotel voucher", … all count. Same pattern as
# routes/dmc_accounts.py.
VOUCHER_ROLE_NAME = "hotel voucher"


async def require_voucher_permission(user: CurrentUser, action: str) -> None:
    # action is "view"/"create"/"edit"/"delete" — the Access page switches.
    if user.role == "admin":
        return
    if VOUCHER_ROLE_NAME not in await user_role_names(user.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied")
    grant = await access_collection.find_one({"userId": user.id, "roleName": VOUCHER_ROLE_NAME})
    if grant is not None and not grant.get(action, True):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied")


def _oid(entry_id: str) -> ObjectId:
    if not ObjectId.is_valid(entry_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Voucher not found")
    return ObjectId(entry_id)


def serialize(d: dict) -> HotelVoucherOut:
    fields = {k: d[k] for k in HotelVoucherCreate.model_fields if k in d}
    return HotelVoucherOut(
        id=str(d["_id"]),
        createdAt=d.get("createdAt", ""),
        createdBy=d.get("createdBy", ""),
        **fields,
    )


@router.get("", response_model=list[HotelVoucherOut])
async def list_vouchers(user: CurrentUser = Depends(get_current_user)):
    await require_voucher_permission(user, "view")
    items = await hotel_vouchers_collection.find().sort("_id", -1).to_list(1000)
    return [serialize(d) for d in items]


@router.get("/next-voucher-no")
async def next_voucher_no(user: CurrentUser = Depends(get_current_user)):
    await require_voucher_permission(user, "create")
    items = await hotel_vouchers_collection.find({}, {"voucherNo": 1}).to_list(5000)
    nums: list[int] = []
    for d in items:
        try:
            nums.append(int(d.get("voucherNo", "")))
        except (TypeError, ValueError):
            continue
    return {"voucherNo": str((max(nums) + 1) if nums else 1)}


@router.post("", response_model=HotelVoucherOut, status_code=201)
async def create_voucher(body: HotelVoucherCreate, user: CurrentUser = Depends(get_current_user)):
    await require_voucher_permission(user, "create")
    doc = body.model_dump()
    doc["createdAt"] = datetime.now(timezone.utc).isoformat()
    doc["createdBy"] = user.id
    res = await hotel_vouchers_collection.insert_one(doc)
    doc["_id"] = res.inserted_id
    return serialize(doc)


@router.put("/{entry_id}", response_model=HotelVoucherOut)
async def update_voucher(
    entry_id: str, body: HotelVoucherCreate, user: CurrentUser = Depends(get_current_user)
):
    await require_voucher_permission(user, "edit")
    updated = await hotel_vouchers_collection.find_one_and_update(
        {"_id": _oid(entry_id)},
        {"$set": body.model_dump()},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Voucher not found")
    return serialize(updated)


@router.delete("/{entry_id}", status_code=204)
async def delete_voucher(entry_id: str, user: CurrentUser = Depends(get_current_user)):
    await require_voucher_permission(user, "delete")
    res = await hotel_vouchers_collection.delete_one({"_id": _oid(entry_id)})
    if res.deleted_count == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Voucher not found")
