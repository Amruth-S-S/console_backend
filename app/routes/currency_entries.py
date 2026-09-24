from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument
from ..db import currency_entries_collection, roles_collection, users_collection
from ..deps import CurrentUser, get_current_user
from ..schemas import ApprovalUpdate, CurrencyEntryCreate, CurrencyEntryOut

router = APIRouter(prefix="/currency-entries", tags=["currency-entries"])

# Case-insensitive match against whatever the admin named the role on the
# Roles page — "Currency", "currency", "CURRENCY" all count. Same pattern
# as routes/accounts.py's "account" check, different role name.
CURRENCY_ROLE_NAME = "currency"


async def require_admin_or_currency_role(user: CurrentUser) -> None:
    if user.role == "admin":
        return
    try:
        user_doc = await users_collection.find_one({"_id": ObjectId(user.id)})
        role_id = user_doc.get("roleId") if user_doc else None
        role_doc = await roles_collection.find_one({"_id": ObjectId(role_id)}) if role_id else None
    except InvalidId:
        role_doc = None
    role_name = (role_doc.get("name", "") if role_doc else "").strip().lower()
    if role_name != CURRENCY_ROLE_NAME:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied")


def require_admin(user: CurrentUser) -> None:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")


def serialize(c: dict) -> CurrencyEntryOut:
    return CurrencyEntryOut(
        id=str(c["_id"]),
        createdAt=c.get("createdAt", ""),
        createdBy=c.get("createdBy", ""),
        approved=bool(c.get("approved", False)),
        slNo=c.get("slNo", ""),
        travelDate=c.get("travelDate", ""),
        passportNumber=c.get("passportNumber", ""),
        clientName=c.get("clientName", ""),
        phoneNumber=c.get("phoneNumber", ""),
        currency=c.get("currency", ""),
        amount=c.get("amount", ""),
        clientAmount=c.get("clientAmount", ""),
        currencyConversion=c.get("currencyConversion", ""),
        handOverTo=c.get("handOverTo", ""),
    )


@router.get("", response_model=list[CurrencyEntryOut])
async def list_currency_entries(user: CurrentUser = Depends(get_current_user)):
    await require_admin_or_currency_role(user)
    items = await currency_entries_collection.find().sort("_id", -1).to_list(1000)
    return [serialize(c) for c in items]


@router.get("/next-sl-no")
async def next_sl_no(user: CurrentUser = Depends(get_current_user)):
    await require_admin_or_currency_role(user)
    items = await currency_entries_collection.find({}, {"slNo": 1}).to_list(5000)
    nums: list[int] = []
    for c in items:
        try:
            nums.append(int(c.get("slNo", "")))
        except (TypeError, ValueError):
            continue
    next_num = (max(nums) + 1) if nums else 1
    return {"slNo": str(next_num)}


@router.post("", response_model=CurrencyEntryOut, status_code=201)
async def create_currency_entry(
    body: CurrencyEntryCreate, user: CurrentUser = Depends(get_current_user)
):
    await require_admin_or_currency_role(user)
    doc = body.model_dump()
    doc["createdAt"] = datetime.now(timezone.utc).isoformat()
    doc["createdBy"] = user.id
    doc["approved"] = False
    res = await currency_entries_collection.insert_one(doc)
    doc["_id"] = res.inserted_id
    return serialize(doc)


@router.put("/{entry_id}/approval", response_model=CurrencyEntryOut)
async def set_approval(
    entry_id: str, body: ApprovalUpdate, user: CurrentUser = Depends(get_current_user)
):
    # Admin-only, unlike list/create above — the Currency role can see the
    # green/grey status but never flips it themselves.
    require_admin(user)
    updated = await currency_entries_collection.find_one_and_update(
        {"_id": ObjectId(entry_id)},
        {"$set": {"approved": body.approved}},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found")
    return serialize(updated)


@router.put("/{entry_id}", response_model=CurrencyEntryOut)
async def update_currency_entry(
    entry_id: str, body: CurrencyEntryCreate, user: CurrentUser = Depends(get_current_user)
):
    # Same gate as create — same reasoning as accounts.py's update_account.
    await require_admin_or_currency_role(user)
    updated = await currency_entries_collection.find_one_and_update(
        {"_id": ObjectId(entry_id)},
        {"$set": body.model_dump()},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found")
    return serialize(updated)


@router.delete("/{entry_id}", status_code=204)
async def delete_currency_entry(entry_id: str, user: CurrentUser = Depends(get_current_user)):
    await require_admin_or_currency_role(user)
    res = await currency_entries_collection.delete_one({"_id": ObjectId(entry_id)})
    if res.deleted_count == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found")
