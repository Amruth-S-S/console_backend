from datetime import datetime, timezone
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, status
from bson import ObjectId
from pymongo import ReturnDocument
from ..db import access_collection, accounts_collection, users_collection
from ..deps import CurrentUser, get_current_user, user_role_names
from ..schemas import (
    AccountAttachmentMeta,
    AccountAttachmentOut,
    AccountAttachmentUpload,
    AccountEntryCreate,
    AccountEntryOut,
    ApprovalUpdate,
)

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


# Attachments live on the entry document (base64 data URLs), so they share
# MongoDB's 16 MB document cap — 5 MB per file and 12 MB per entry leaves
# headroom for the ledger fields and base64's ~33% overhead is counted.
MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
MAX_ENTRY_ATTACHMENT_BYTES = 12 * 1024 * 1024
ALLOWED_ATTACHMENT_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

# The list endpoint never renders file contents — same projection trick as
# bookings' ID documents (see routes/bookings.py's list_bookings).
LIST_PROJECTION = {"attachments.data": 0}


def attachment_meta(att: dict) -> AccountAttachmentMeta:
    return AccountAttachmentMeta(
        id=att.get("id", ""),
        name=att.get("name", ""),
        type=att.get("type", ""),
        size=int(att.get("size", 0) or 0),
        uploadedAt=att.get("uploadedAt", ""),
        uploadedBy=att.get("uploadedBy", ""),
        uploadedByName=att.get("uploadedByName", ""),
    )


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
        name=a.get("name", ""),
        destination=a.get("destination", ""),
        handOverTo=a.get("handOverTo", ""),
        debit=a.get("debit", ""),
        credit=a.get("credit", ""),
        balance=a.get("balance", ""),
        paymentMode=a.get("paymentMode", ""),
        description=a.get("description", ""),
        attachments=[attachment_meta(att) for att in a.get("attachments", [])],
    )


@router.get("", response_model=list[AccountEntryOut])
async def list_accounts(user: CurrentUser = Depends(get_current_user)):
    await require_account_permission(user, "view")
    items = await accounts_collection.find({}, LIST_PROJECTION).sort("_id", -1).to_list(1000)
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
        projection=LIST_PROJECTION,
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
        projection=LIST_PROJECTION,
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


def _oid(entry_id: str) -> ObjectId:
    if not ObjectId.is_valid(entry_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found")
    return ObjectId(entry_id)


@router.post("/{entry_id}/attachments", response_model=AccountEntryOut, status_code=201)
async def upload_attachment(
    entry_id: str, body: AccountAttachmentUpload, user: CurrentUser = Depends(get_current_user)
):
    # Anyone who can see the ledger can attach proof to a row — uploading a
    # receipt doesn't change any ledger figures, so it only needs "view".
    await require_account_permission(user, "view")
    if not body.data.startswith("data:") or "," not in body.data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "File must be a base64 data URL")
    mime = body.data[5 : body.data.index(";")] if ";" in body.data else ""
    if not (mime.startswith("image/") or mime in ALLOWED_ATTACHMENT_TYPES):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only PDF, Word documents and images are allowed")
    size = len(body.data.split(",", 1)[1]) * 3 // 4
    if size > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "File is larger than 5 MB")

    oid = _oid(entry_id)
    existing = await accounts_collection.find_one({"_id": oid}, {"attachments.size": 1})
    if not existing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found")
    used = sum(int(a.get("size", 0) or 0) for a in existing.get("attachments", []))
    if used + size > MAX_ENTRY_ATTACHMENT_BYTES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This entry's attachments would exceed 12 MB in total")

    # Name stored alongside the id so the View modal can show who uploaded
    # it without a users lookup (non-admins can't list users).
    uploader = await users_collection.find_one({"_id": ObjectId(user.id)}, {"name": 1})
    att = {
        "id": uuid4().hex,
        "name": body.name,
        "type": mime,
        "size": size,
        "data": body.data,
        "uploadedAt": datetime.now(timezone.utc).isoformat(),
        "uploadedBy": user.id,
        "uploadedByName": (uploader or {}).get("name", ""),
    }
    updated = await accounts_collection.find_one_and_update(
        {"_id": oid},
        {"$push": {"attachments": att}},
        return_document=ReturnDocument.AFTER,
        projection=LIST_PROJECTION,
    )
    if not updated:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found")
    return serialize(updated)


@router.get("/{entry_id}/attachments/{attachment_id}", response_model=AccountAttachmentOut)
async def get_attachment(
    entry_id: str, attachment_id: str, user: CurrentUser = Depends(get_current_user)
):
    await require_account_permission(user, "view")
    doc = await accounts_collection.find_one(
        {"_id": _oid(entry_id)}, {"attachments": {"$elemMatch": {"id": attachment_id}}}
    )
    atts = (doc or {}).get("attachments") or []
    if not atts:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attachment not found")
    att = atts[0]
    return AccountAttachmentOut(**attachment_meta(att).model_dump(), data=att.get("data", ""))


@router.delete("/{entry_id}/attachments/{attachment_id}", response_model=AccountEntryOut)
async def delete_attachment(
    entry_id: str, attachment_id: str, user: CurrentUser = Depends(get_current_user)
):
    # Removing proof is more sensitive than adding it — same gate as
    # deleting the ledger row itself.
    await require_account_permission(user, "delete")
    updated = await accounts_collection.find_one_and_update(
        {"_id": _oid(entry_id)},
        {"$pull": {"attachments": {"id": attachment_id}}},
        return_document=ReturnDocument.AFTER,
        projection=LIST_PROJECTION,
    )
    if not updated:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found")
    return serialize(updated)
