from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from bson import ObjectId
from pymongo import ReturnDocument
from ..db import bookings_collection, packages_collection, users_collection
from ..deps import CurrentUser, get_current_user
from ..schemas import BookingCreate, BookingOut

router = APIRouter(prefix="/bookings", tags=["bookings"])


def _as_doc_list(v) -> list:
    # aadharDoc/panDoc/passportDoc were originally a single document (or
    # None) before multi-file upload was added — normalizes either shape to
    # a list so old bookings still validate against the new list[...] field
    # instead of erroring out.
    if not v:
        return []
    return v if isinstance(v, list) else [v]


def serialize(b: dict) -> BookingOut:
    return BookingOut(
        id=str(b["_id"]),
        createdAt=b["createdAt"],
        userId=b.get("userId", ""),
        userName=b.get("userName", ""),
        userEmail=b.get("userEmail", ""),
        clientName=b.get("clientName", ""),
        clientPhone=b.get("clientPhone", ""),
        clientEmail=b.get("clientEmail", ""),
        location=b.get("location", ""),
        packageType=b.get("packageType", "domestic"),
        packageId=b.get("packageId"),
        landPackage=b.get("landPackage", ""),
        packageTitle=b.get("packageTitle", ""),
        travelDate=b.get("travelDate", ""),
        finalPaymentDate=b.get("finalPaymentDate", ""),
        adults=b.get("adults", "1"),
        children=b.get("children", "0"),
        infants=b.get("infants", "0"),
        adultPrice=b.get("adultPrice", ""),
        childPrice=b.get("childPrice", ""),
        infantPrice=b.get("infantPrice", ""),
        flightAmount=b.get("flightAmount", ""),
        adultLandPrice=b.get("adultLandPrice", ""),
        childLandPrice=b.get("childLandPrice", ""),
        infantLandPrice=b.get("infantLandPrice", ""),
        advancePayments=b.get("advancePayments", []),
        invoiceNumber=b.get("invoiceNumber", ""),
        invoiceDate=b.get("invoiceDate", ""),
        amount=b.get("amount", ""),
        transactionId=b.get("transactionId", ""),
        specialRequirements=b.get("specialRequirements", ""),
        aadharDoc=_as_doc_list(b.get("aadharDoc")),
        panDoc=_as_doc_list(b.get("panDoc")),
        passportDoc=_as_doc_list(b.get("passportDoc")),
        otherDocs=b.get("otherDocs", []),
        createdBy=b.get("createdBy", ""),
    )


async def resolve_names(user_id: str, package_id: str | None) -> dict:
    user_doc = await users_collection.find_one({"_id": ObjectId(user_id)})
    if not user_doc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Selected user not found")

    package_title = ""
    if package_id:
        pkg_doc = await packages_collection.find_one({"_id": ObjectId(package_id)})
        if not pkg_doc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Selected package not found")
        package_title = pkg_doc.get("packageTitle", "")

    return {
        "userName": user_doc.get("name", ""),
        "userEmail": user_doc.get("email", ""),
        "packageTitle": package_title,
    }


@router.get("", response_model=list[BookingOut])
async def list_bookings(user: CurrentUser = Depends(get_current_user)):
    # Visible if this user made the booking OR it's assigned to them (userId)
    # — so a booking admin creates and assigns to a user shows up for that
    # user too. Editing/deleting stays restricted to the creator/admin below.
    query = (
        {}
        if user.role == "admin"
        else {"$or": [{"createdBy": user.id}, {"userId": user.id}]}
    )
    # ID document uploads are base64 and can each be a couple MB — same
    # story as day-images on the packages list (see that route's comment):
    # the bookings table never renders these, so they're excluded at the
    # query level rather than fetched and discarded. The edit form re-fetches
    # the full booking via GET /bookings/{id} before opening, which still
    # gets them (see the frontend's openEdit).
    items = (
        await bookings_collection.find(
            query, {"aadharDoc": 0, "panDoc": 0, "passportDoc": 0, "otherDocs": 0}
        )
        .sort("_id", -1)
        .to_list(500)
    )
    return [serialize(b) for b in items]


@router.get("/next-invoice-number")
async def next_invoice_number(user: CurrentUser = Depends(get_current_user)):
    # Invoice numbers must be unique across the whole business, not just
    # within whatever slice of bookings this particular account can see.
    # list_bookings() above filters non-admins down to their own bookings —
    # so a client-side "max invoice number + 1" computed from that filtered
    # list let two different staff accounts each land on "0001" the first
    # time they created a booking, colliding with numbers admin (or other
    # staff) had already used. Computed here against the *entire* collection
    # instead, unfiltered by role, so every account gets the same next
    # number in the one running sequence regardless of who's logged in.
    items = await bookings_collection.find({}, {"invoiceNumber": 1}).to_list(5000)
    nums: list[int] = []
    for b in items:
        try:
            nums.append(int(b.get("invoiceNumber", "")))
        except (TypeError, ValueError):
            continue
    next_num = (max(nums) + 1) if nums else 1
    return {"invoiceNumber": str(next_num).zfill(4)}


@router.get("/{booking_id}", response_model=BookingOut)
async def get_booking(booking_id: str, user: CurrentUser = Depends(get_current_user)):
    b = await bookings_collection.find_one({"_id": ObjectId(booking_id)})
    is_visible = (
        user.role == "admin" or b.get("createdBy") == user.id or b.get("userId") == user.id
    ) if b else False
    if not b or not is_visible:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")
    return serialize(b)


@router.post("", response_model=BookingOut, status_code=201)
async def create_booking(body: BookingCreate, user: CurrentUser = Depends(get_current_user)):
    # Non-admins can only ever assign a booking to themselves, regardless of
    # what the client sends — the dropdown is locked to "self" for them in
    # the UI, but the server stays authoritative.
    target_user_id = body.userId if user.role == "admin" else user.id

    doc = body.model_dump()
    doc["userId"] = target_user_id
    doc["createdBy"] = user.id
    doc.update(await resolve_names(target_user_id, body.packageId))
    doc["createdAt"] = datetime.now(timezone.utc).isoformat()
    res = await bookings_collection.insert_one(doc)
    doc["_id"] = res.inserted_id
    return serialize(doc)


@router.put("/{booking_id}", response_model=BookingOut)
async def update_booking(
    booking_id: str, body: BookingCreate, user: CurrentUser = Depends(get_current_user)
):
    existing = await bookings_collection.find_one({"_id": ObjectId(booking_id)})
    if not existing or (user.role != "admin" and existing.get("createdBy") != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")

    target_user_id = body.userId if user.role == "admin" else user.id
    update = body.model_dump()
    update["userId"] = target_user_id
    update.update(await resolve_names(target_user_id, body.packageId))

    res = await bookings_collection.find_one_and_update(
        {"_id": ObjectId(booking_id)},
        {"$set": update},
        return_document=ReturnDocument.AFTER,
    )
    return serialize(res)


@router.delete("/{booking_id}", status_code=204)
async def delete_booking(booking_id: str, user: CurrentUser = Depends(get_current_user)):
    query = {"_id": ObjectId(booking_id)}
    if user.role != "admin":
        query["createdBy"] = user.id
    res = await bookings_collection.delete_one(query)
    if res.deleted_count == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")
