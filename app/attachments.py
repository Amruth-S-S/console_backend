"""File attachments stored on a ledger entry document (Account, DMC Account).

Files are base64 data URLs in the entry's `attachments` array, so they share
MongoDB's 16 MB document cap — 5 MB per file and 12 MB per entry leaves
headroom for the ledger fields, with base64's ~33% overhead counted.
"""
from datetime import datetime, timezone
from uuid import uuid4
from bson import ObjectId
from fastapi import HTTPException, status
from pymongo import ReturnDocument
from .db import users_collection
from .deps import CurrentUser
from .schemas import AccountAttachmentMeta, AccountAttachmentOut, AccountAttachmentUpload

MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
MAX_ENTRY_ATTACHMENT_BYTES = 12 * 1024 * 1024
ALLOWED_ATTACHMENT_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

# List endpoints never render file contents — same projection trick as
# bookings' ID documents (see routes/bookings.py's list_bookings).
LIST_PROJECTION = {"attachments.data": 0}


def oid_or_404(entry_id: str) -> ObjectId:
    if not ObjectId.is_valid(entry_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found")
    return ObjectId(entry_id)


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


def attachments_meta(doc: dict) -> list[AccountAttachmentMeta]:
    return [attachment_meta(a) for a in doc.get("attachments", [])]


async def add_attachment(collection, entry_id: str, body: AccountAttachmentUpload, user: CurrentUser) -> dict:
    """Validates and pushes one file; returns the updated entry (without file data)."""
    if not body.data.startswith("data:") or "," not in body.data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "File must be a base64 data URL")
    mime = body.data[5 : body.data.index(";")] if ";" in body.data else ""
    if not (mime.startswith("image/") or mime in ALLOWED_ATTACHMENT_TYPES):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only PDF, Word documents and images are allowed")
    size = len(body.data.split(",", 1)[1]) * 3 // 4
    if size > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "File is larger than 5 MB")

    oid = oid_or_404(entry_id)
    existing = await collection.find_one({"_id": oid}, {"attachments.size": 1})
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
    updated = await collection.find_one_and_update(
        {"_id": oid},
        {"$push": {"attachments": att}},
        return_document=ReturnDocument.AFTER,
        projection=LIST_PROJECTION,
    )
    if not updated:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found")
    return updated


async def get_attachment(collection, entry_id: str, attachment_id: str) -> AccountAttachmentOut:
    doc = await collection.find_one(
        {"_id": oid_or_404(entry_id)}, {"attachments": {"$elemMatch": {"id": attachment_id}}}
    )
    atts = (doc or {}).get("attachments") or []
    if not atts:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attachment not found")
    att = atts[0]
    return AccountAttachmentOut(**attachment_meta(att).model_dump(), data=att.get("data", ""))


async def remove_attachment(collection, entry_id: str, attachment_id: str) -> dict:
    """Pulls one file; returns the updated entry (without file data)."""
    updated = await collection.find_one_and_update(
        {"_id": oid_or_404(entry_id)},
        {"$pull": {"attachments": {"id": attachment_id}}},
        return_document=ReturnDocument.AFTER,
        projection=LIST_PROJECTION,
    )
    if not updated:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found")
    return updated
