from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from bson import ObjectId
from pymongo import ReturnDocument
from ..db import access_collection, accounts_collection
from ..deps import CurrentUser, get_current_user, user_role_names
from ..schemas import AccountEntryCreate, AccountEntryOut, ApprovalUpdate

router = APIRouter(prefix="/accounts", tags=["accounts"])

# Case-insensitive match against whatever the admin named the role on the
# Roles page — "Account", "account", "ACCOUNT" all count.
ACCOUNT_ROLE_NAME = "account"


async def require_account_permission(user: CurrentUser, action: str) -> None:
    # action is one of "view"/"create"/"edit"/"delete" — the same four
    # switches admin sets on the Access page (routes/access.py). Holding
    # the Account role is still required first; the granular grant (which
    # defaults to fully-allowed if the admin never restricted it — see
    # access.py's get_access) then narrows it further.
    if user.role == "admin":
        return
    if ACCOUNT_ROLE_NAME not in await user_role_names(user.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied")
    grant = await access_collection.find_one({"userId": user.id, "roleName": ACCOUNT_ROLE_NAME})
    if grant is not None and not grant.get(action, True):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied")


def require_admin(user: CurrentUser) -> None:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")


def serialize(a: dict) -> AccountEntryOut:
    return AccountEntryOut(
        id=str(a["_id"]),
        createdAt=a.get("createdAt", ""),
        createdBy=a.get("createdBy", ""),
        approved=bool(a.get("approved", False)),
        slNo=a.get("slNo", ""),
        date=a.get("date", ""),
        invoiceNo=a.get("invoiceNo", ""),
        agent=a.get("agent", ""),
        clientName=a.get("clientName", ""),
        destination=a.get("destination", ""),
        handOverTo=a.get("handOverTo", ""),
        debitCredit=a.get("debitCredit", ""),
        balance=a.get("balance", ""),
        paymentMode=a.get("paymentMode", ""),
        description=a.get("description", ""),
    )


@router.get("", response_model=list[AccountEntryOut])
async def list_accounts(user: CurrentUser = Depends(get_current_user)):
    await require_account_permission(user, "view")
    items = await accounts_collection.find().sort("_id", -1).to_list(1000)
    return [serialize(a) for a in items]


async def compute_next_sl_no() -> str:
    # Shared by the endpoint below (manual "+ Add Entry") and by
    # routes/bookings.py's auto-sync (a new booking auto-creates a ledger
    # row) — one running sequence regardless of which path created the row.
    items = await accounts_collection.find({}, {"slNo": 1}).to_list(5000)
    nums: list[int] = []
    for a in items:
        try:
            nums.append(int(a.get("slNo", "")))
        except (TypeError, ValueError):
            continue
    next_num = (max(nums) + 1) if nums else 1
    return str(next_num)


@router.get("/next-sl-no")
async def next_sl_no(user: CurrentUser = Depends(get_current_user)):
    # Same reasoning as bookings' next-invoice-number — computed against the
    # whole collection so every account/admin login continues one running
    # sequence instead of colliding.
    await require_account_permission(user, "create")
    return {"slNo": await compute_next_sl_no()}


@router.post("", response_model=AccountEntryOut, status_code=201)
async def create_account(
    body: AccountEntryCreate, user: CurrentUser = Depends(get_current_user)
):
    await require_account_permission(user, "create")
    doc = body.model_dump()
    doc["createdAt"] = datetime.now(timezone.utc).isoformat()
    doc["createdBy"] = user.id
    doc["approved"] = False
    res = await accounts_collection.insert_one(doc)
    doc["_id"] = res.inserted_id
    return serialize(doc)


@router.put("/{entry_id}/approval", response_model=AccountEntryOut)
async def set_approval(
    entry_id: str, body: ApprovalUpdate, user: CurrentUser = Depends(get_current_user)
):
    # Admin-only, unlike list/create above — the Account role can see the
    # green/grey status but never flips it themselves.
    require_admin(user)
    updated = await accounts_collection.find_one_and_update(
        {"_id": ObjectId(entry_id)},
        {"$set": {"approved": body.approved}},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found")
    return serialize(updated)


@router.put("/{entry_id}", response_model=AccountEntryOut)
async def update_account(
    entry_id: str, body: AccountEntryCreate, user: CurrentUser = Depends(get_current_user)
):
    # Same gate as create — anyone who can add a ledger entry can also fix
    # one they (or a teammate) mistyped. approved/createdBy/createdAt are
    # untouched so editing fields doesn't reset an already-approved entry.
    await require_account_permission(user, "edit")
    updated = await accounts_collection.find_one_and_update(
        {"_id": ObjectId(entry_id)},
        {"$set": body.model_dump()},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found")
    return serialize(updated)


@router.delete("/{entry_id}", status_code=204)
async def delete_account(entry_id: str, user: CurrentUser = Depends(get_current_user)):
    await require_account_permission(user, "delete")
    res = await accounts_collection.delete_one({"_id": ObjectId(entry_id)})
    if res.deleted_count == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found")
