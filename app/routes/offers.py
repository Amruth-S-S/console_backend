from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from bson import ObjectId
from pymongo import ReturnDocument
from ..db import bookings_collection, offers_collection
from ..deps import CurrentUser, get_current_user, user_role_names
from ..schemas import MyOfferProgress, OfferBulkCreate, OfferCreate, OfferOut

router = APIRouter(prefix="/offers", tags=["offers"])


# Every route except /my-progress needs admin, or a user granted the
# "Offer Section" menu on the Access page (or holding a role with that name).
async def require_manager(user: CurrentUser) -> None:
    if user.role == "admin":
        return
    if "offer section" not in await user_role_names(user.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied")


def _oid(entry_id: str) -> ObjectId:
    if not ObjectId.is_valid(entry_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Offer not found")
    return ObjectId(entry_id)


def serialize(d: dict) -> OfferOut:
    return OfferOut(
        id=str(d["_id"]),
        createdAt=d.get("createdAt", ""),
        packageName=d.get("packageName", ""),
        targetAmount=d.get("targetAmount", ""),
        fromDate=d.get("fromDate", ""),
        toDate=d.get("toDate", ""),
    )


@router.get("", response_model=list[OfferOut])
async def list_offers(user: CurrentUser = Depends(get_current_user)):
    await require_manager(user)
    items = await offers_collection.find().sort("_id", -1).to_list(1000)
    return [serialize(d) for d in items]


def _num(v) -> float:
    try:
        return float(str(v or "").replace(",", "").strip() or 0)
    except ValueError:
        return 0.0


def _norm(title: str) -> str:
    return " ".join((title or "").lower().split())


def _package_price(b: dict) -> float:
    # Same formula as the frontend's computeInvoiceTotals().packagePrice, so
    # a user's percentage matches what admin sees on the Overview panel.
    return (
        _num(b.get("adults")) * _num(b.get("adultPrice"))
        + _num(b.get("children")) * _num(b.get("childPrice"))
        + _num(b.get("infants")) * _num(b.get("infantPrice"))
    )


@router.get("/my-progress", response_model=list[MyOfferProgress])
async def my_progress(user: CurrentUser = Depends(get_current_user)):
    # Any logged-in user: how far *they* are toward each running offer's
    # individual target, as a percentage. Bookings count for the user they're
    # assigned to (userId) and only within the offer's From/To dates — the
    # same rules as admin's "Offer targets" panel (Offer dates view).
    today = datetime.now(timezone.utc).date().isoformat()
    offers = await offers_collection.find().sort("_id", -1).to_list(1000)
    running = [o for o in offers if not o.get("toDate") or o["toDate"] >= today]
    if not running:
        return []

    mine = await bookings_collection.find(
        {"userId": user.id},
        {"packageTitle": 1, "invoiceDate": 1, "createdAt": 1, "adults": 1, "children": 1,
         "infants": 1, "adultPrice": 1, "childPrice": 1, "infantPrice": 1},
    ).to_list(5000)

    out: list[MyOfferProgress] = []
    for o in running:
        name = _norm(o.get("packageName", ""))
        start, end = o.get("fromDate", ""), o.get("toDate", "")
        count, booked = 0, 0.0
        for b in mine:
            if _norm(b.get("packageTitle", "")) != name:
                continue
            made = (b.get("invoiceDate") or b.get("createdAt") or "")[:10]
            if made:
                if (start and made < start) or (end and made > end):
                    continue
            elif start or end:
                continue
            count += 1
            booked += _package_price(b)
        target = _num(o.get("targetAmount"))
        percent = min(int(round(booked / target * 100)), 100) if target > 0 else 0
        out.append(
            MyOfferProgress(
                id=str(o["_id"]),
                packageName=o.get("packageName", ""),
                fromDate=start,
                toDate=end,
                bookings=count,
                percent=percent,
                met=target > 0 and booked >= target,
            )
        )
    return out


@router.post("/bulk", response_model=list[OfferOut], status_code=201)
async def create_offers(body: OfferBulkCreate, user: CurrentUser = Depends(get_current_user)):
    # All rows from the modal in one request — saved together or not at all
    # (validation runs on the whole list before anything is inserted).
    await require_manager(user)
    now = datetime.now(timezone.utc).isoformat()
    docs = [{**o.model_dump(), "createdAt": now, "createdBy": user.id} for o in body.offers]
    res = await offers_collection.insert_many(docs)
    for doc, oid in zip(docs, res.inserted_ids):
        doc["_id"] = oid
    return [serialize(d) for d in docs]


@router.put("/{entry_id}", response_model=OfferOut)
async def update_offer(entry_id: str, body: OfferCreate, user: CurrentUser = Depends(get_current_user)):
    await require_manager(user)
    updated = await offers_collection.find_one_and_update(
        {"_id": _oid(entry_id)},
        {"$set": body.model_dump()},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Offer not found")
    return serialize(updated)


@router.delete("/{entry_id}", status_code=204)
async def delete_offer(entry_id: str, user: CurrentUser = Depends(get_current_user)):
    await require_manager(user)
    res = await offers_collection.delete_one({"_id": _oid(entry_id)})
    if res.deleted_count == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Offer not found")
