from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from bson import ObjectId
from pymongo import ReturnDocument
from ..db import accounts_collection, bookings_collection, packages_collection, users_collection
from ..deps import CurrentUser, get_current_user, user_role_names
from ..schemas import BookingCreate, BookingOut
from .accounts import compute_next_sl_no

router = APIRouter(prefix="/bookings", tags=["bookings"])

# Case-insensitive match against the custom role name on the Roles page —
# same pattern as ACCOUNT_ROLE_NAME/CURRENCY_ROLE_NAME. A Team Lead gets
# admin-like READ access to every booking (for oversight/reporting) but
# keeps a narrower edit/delete right than a regular staff account: only
# bookings they personally created, not ones merely assigned to them (see
# _is_team_lead's use in update_booking/delete_booking below).
TEAM_LEAD_ROLE_NAME = "team lead"


async def _is_team_lead(user: CurrentUser) -> bool:
    if user.role == "admin":
        return False
    # A user can hold several roles at once now — this is true if ANY of
    # them is "Team Lead", not just when it's their only role.
    return TEAM_LEAD_ROLE_NAME in await user_role_names(user.id)


def _to_float(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _compute_balance_due(doc: dict) -> str:
    # Mirrors lib/invoice.ts's computeInvoiceTotals exactly — the "Balance
    # Due" column on the bookings table is packagePrice (adults/children/
    # infants x their prices) minus total advance paid, NOT the booking's
    # own "amount" field (that's "Amount to collect now", the one-off figure
    # typed in just to generate a UPI QR code — unrelated to the running
    # balance, which is why the ledger showed the wrong number).
    package_price = (
        _to_float(doc.get("adults")) * _to_float(doc.get("adultPrice"))
        + _to_float(doc.get("children")) * _to_float(doc.get("childPrice"))
        + _to_float(doc.get("infants")) * _to_float(doc.get("infantPrice"))
    )
    total_advance = sum(_to_float(p.get("amount")) for p in (doc.get("advancePayments") or []))
    balance_due = package_price - total_advance
    return str(int(balance_due)) if balance_due == int(balance_due) else str(balance_due)


async def _sync_account_entry(booking_id: str, doc: dict, created_by: str, is_new: bool) -> None:
    # Keeps the Account ledger's Invoice No / Balance / Client Name / Date in
    # lockstep with whatever the booking form shows, per the admin's request
    # that booking data "automatically comes to account list" — same numbers
    # in both places instead of someone re-typing them into a ledger entry.
    # Linked via a plain "bookingId" field on the accounts doc, deliberately
    # left off AccountEntryCreate/Out so it's never exposed to the frontend
    # and a normal manual edit of the row (which round-trips the full
    # AccountEntryCreate model) can't accidentally wipe the link.
    fields = {
        "date": doc.get("invoiceDate") or doc.get("travelDate") or "",
        "invoiceNo": doc.get("invoiceNumber", ""),
        "agent": doc.get("userName", ""),
        "clientName": doc.get("clientName", ""),
        "destination": doc.get("location", ""),
        "balance": _compute_balance_due(doc),
    }
    if is_new:
        fields.update(
            {
                "slNo": await compute_next_sl_no(),
                "handOverTo": "",
                "debitCredit": "Credit",
                "paymentMode": "Cash",
                "createdAt": datetime.now(timezone.utc).isoformat(),
                "createdBy": created_by,
                "approved": False,
                "bookingId": booking_id,
            }
        )
        await accounts_collection.insert_one(fields)
    else:
        # Only touches the booking-derived fields — Hand Over To, Debit/
        # Credit, Payment Mode and Approval are ledger-specific and stay
        # whatever an admin/Account-role user already set on this row.
        await accounts_collection.update_one({"bookingId": booking_id}, {"$set": fields})


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
    # A Team Lead sees every booking, same as admin — see TEAM_LEAD_ROLE_NAME
    # above for why their edit rights don't get the same broadening.
    see_all = user.role == "admin" or await _is_team_lead(user)
    query = (
        {}
        if see_all
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


@router.get("/clients")
async def list_clients(user: CurrentUser = Depends(get_current_user)):
    # Name + phone only, across EVERY booking company-wide — unlike
    # list_bookings() above, deliberately NOT filtered to what this account
    # created/is assigned to. The Account and Currency ledgers' "pick an
    # existing client" dropdowns need to find any client at all, not just
    # ones this particular login can manage, and staff who only do
    # account/currency entry work typically have none of their own
    # bookings. Excludes every other field (pricing, documents, etc.) since
    # this is reachable by any authenticated user, not just admin.
    items = (
        await bookings_collection.find({}, {"clientName": 1, "clientPhone": 1})
        .sort("_id", -1)
        .to_list(2000)
    )
    seen: set[str] = set()
    result = []
    for b in items:
        name = (b.get("clientName") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        result.append({"clientName": name, "clientPhone": b.get("clientPhone", "")})
    return result


@router.get("/travel-list")
async def list_travel_entries(user: CurrentUser = Depends(get_current_user)):
    # The Travel List page is deliberately common to every logged-in
    # account, not just admin/Team Lead — same reasoning as /clients above:
    # unlike list_bookings() (scoped to what this account created/is
    # assigned to for a regular non-admin, non-Team-Lead user), a plain
    # "User" role checking the departure roster still needs to see every
    # trip company-wide, not just their own bookings. Only the handful of
    # fields that page actually renders are returned — no pricing,
    # contact details beyond the client's name, or documents.
    items = (
        await bookings_collection.find(
            {},
            {
                "travelDate": 1,
                "packageTitle": 1,
                "location": 1,
                "clientName": 1,
                "adults": 1,
                "children": 1,
                "infants": 1,
            },
        )
        .sort("_id", -1)
        .to_list(3000)
    )
    return [
        {
            "id": str(b["_id"]),
            "travelDate": b.get("travelDate", ""),
            "packageTitle": b.get("packageTitle", ""),
            "location": b.get("location", ""),
            "clientName": b.get("clientName", ""),
            "adults": b.get("adults", "0"),
            "children": b.get("children", "0"),
            "infants": b.get("infants", "0"),
        }
        for b in items
    ]


@router.get("/{booking_id}", response_model=BookingOut)
async def get_booking(booking_id: str, user: CurrentUser = Depends(get_current_user)):
    b = await bookings_collection.find_one({"_id": ObjectId(booking_id)})
    is_visible = (
        user.role == "admin"
        or b.get("createdBy") == user.id
        or b.get("userId") == user.id
        or await _is_team_lead(user)
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
    await _sync_account_entry(str(res.inserted_id), doc, user.id, is_new=True)
    return serialize(doc)


@router.put("/{booking_id}", response_model=BookingOut)
async def update_booking(
    booking_id: str, body: BookingCreate, user: CurrentUser = Depends(get_current_user)
):
    existing = await bookings_collection.find_one({"_id": ObjectId(booking_id)})
    if not existing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")

    if user.role != "admin":
        if await _is_team_lead(user):
            # Narrower than the regular rule below — a Team Lead can SEE
            # every booking but may only edit ones they personally created,
            # not ones just assigned to them, and not another team member's.
            is_owner = existing.get("createdBy") == user.id
        else:
            # createdBy OR userId, not createdBy alone. A booking admin
            # creates and assigns to a staff member (the normal flow: pick a
            # user from the dropdown) has createdBy = admin's id, userId =
            # that staff member's id. Checking only createdBy meant that
            # staff member could see and open the booking (the two GET
            # routes already use this same OR) but got "not found" the
            # moment they tried to save an edit.
            is_owner = existing.get("createdBy") == user.id or existing.get("userId") == user.id
        if not is_owner:
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
    await _sync_account_entry(booking_id, update, user.id, is_new=False)
    return serialize(res)


@router.delete("/{booking_id}", status_code=204)
async def delete_booking(booking_id: str, user: CurrentUser = Depends(get_current_user)):
    query = {"_id": ObjectId(booking_id)}
    if user.role != "admin":
        if await _is_team_lead(user):
            # Same narrower rule as update_booking — createdBy only.
            query["createdBy"] = user.id
        else:
            # Same createdBy-OR-userId ownership rule as update_booking
            # above — was createdBy-only here too, same "assigned to me but
            # I can't touch it" bug.
            query["$or"] = [{"createdBy": user.id}, {"userId": user.id}]
    res = await bookings_collection.delete_one(query)
    if res.deleted_count == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")
