from pydantic import BaseModel, EmailStr, Field, model_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=20)
    password: str = Field(min_length=6, max_length=128)
    # Admin-assigned custom roles (from the Roles page) — labels, distinct
    # from the "role" access-control field below (still hardcoded
    # admin/user for actual permissions). One person can hold several at
    # once (e.g. both "Account" and "Currency"); empty means unassigned.
    roleIds: list[str] = Field(default_factory=list)


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=20)
    # Admin-only password reset — omit the field entirely to leave the
    # password unchanged (see exclude_unset in the update route).
    password: str | None = Field(default=None, min_length=6, max_length=128)
    roleIds: list[str] | None = None


class UserOut(BaseModel):
    id: str
    name: str
    email: EmailStr
    phone: str | None = None
    role: str
    roleIds: list[str] = Field(default_factory=list)
    # Resolved server-side from roleIds (see routes/users.py, routes/auth.py)
    # so the frontend can gate UI on role NAMEs (e.g. "Account") without a
    # separate roles fetch just to resolve each id.
    roleNames: list[str] = Field(default_factory=list)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class DayImage(BaseModel):
    src: str
    caption: str = ""

    @model_validator(mode="before")
    @classmethod
    def _from_plain_string(cls, v):
        # Packages saved before captions existed stored images as plain
        # data-URL strings — read those in as a captionless image instead
        # of failing validation on old documents.
        if isinstance(v, str):
            return {"src": v, "caption": ""}
        return v


class PackageDay(BaseModel):
    title: str = ""
    desc: str = ""
    # Optional — some clients want the itinerary to show actual calendar
    # dates per day, others deliberately don't (the same saved package gets
    # reused either way). Blank means "don't show a date for this day".
    date: str = ""
    images: list[DayImage] = Field(default_factory=list)


class PackageCreate(BaseModel):
    companyName: str = ""
    logo: str | None = None
    poster: str | None = None
    packageTitle: str = Field(min_length=1, max_length=200)
    packageType: str = "domestic"
    duration: str = ""
    highlights: list[str] = Field(default_factory=list)
    days: list[PackageDay] = Field(default_factory=list)
    inclusions: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    adultPrice: str = ""
    childPrice: str = ""
    bookingAmount: str = ""
    gst: str = ""
    dates: list[str] = Field(default_factory=list)
    cancellationPolicy: str = ""
    additionalInfo: str = ""
    termsConditions: str = ""


class PackageUpdate(PackageCreate):
    packageTitle: str = Field(default="", max_length=200)


class PackageOut(PackageCreate):
    id: str
    createdAt: str
    # Admin-only figures — deliberately not part of PackageCreate/PackageUpdate
    # (never travel through the regular package create/edit flow, which any
    # logged-in user can hit) and blanked out for non-admin viewers by the
    # route layer regardless of what's actually stored (see packages.py).
    adultNetProfit: str = ""
    childNetProfit: str = ""
    infantNetProfit: str = ""


class NetProfitUpdate(BaseModel):
    adultNetProfit: str = ""
    childNetProfit: str = ""
    infantNetProfit: str = ""


class AdvancePayment(BaseModel):
    amount: str = ""
    date: str = ""
    note: str = ""


class BookingDocument(BaseModel):
    name: str = ""
    type: str = ""
    # Base64 data URL — same "just embed it in the document" approach as
    # package images. These are ID docs (small, one-off per booking, never
    # listed in bulk like packages are), so the GET /packages list-endpoint
    # slowness this caused there doesn't apply here.
    data: str = ""


class BookingCreate(BaseModel):
    userId: str
    clientName: str = Field(min_length=1, max_length=120)
    clientPhone: str = Field(min_length=1, max_length=20)
    clientEmail: str = ""
    location: str = ""
    packageType: str = "domestic"
    packageId: str | None = None
    # Internal cost paid to the land vendor for this booking — used to work
    # out margin on the admin dashboard, never shown on the client invoice.
    landPackage: str = ""
    travelDate: str = ""
    finalPaymentDate: str = ""
    adults: str = "1"
    children: str = "0"
    infants: str = "0"
    adultPrice: str = ""
    childPrice: str = ""
    infantPrice: str = ""
    flightAmount: str = ""
    # Per-person land cost (mirrors adultPrice/childPrice/infantPrice) —
    # multiplied by adults/children/infants to get the total land cost for
    # this booking, used on the admin dashboard's net-revenue figures.
    adultLandPrice: str = ""
    childLandPrice: str = ""
    infantLandPrice: str = ""
    advancePayments: list[AdvancePayment] = Field(default_factory=list)
    invoiceNumber: str = ""
    invoiceDate: str = ""
    amount: str = ""
    transactionId: str = ""
    # Free-text notes from the client (dietary needs, room preference, etc.)
    # — shown on page 2 of the invoice alongside the hardcoded terms & conditions.
    specialRequirements: str = ""
    # Internal note for the team — shown on the Bookings list, deliberately
    # NOT printed on the invoice (unlike specialRequirements above).
    note: str = ""
    # ID document uploads — Aadhar/PAN/Passport each accept one or many
    # files (e.g. front + back of a card), plus an open-ended "other
    # documents" list for anything else.
    aadharDoc: list[BookingDocument] = Field(default_factory=list)
    panDoc: list[BookingDocument] = Field(default_factory=list)
    passportDoc: list[BookingDocument] = Field(default_factory=list)
    otherDocs: list[BookingDocument] = Field(default_factory=list)


class BookingOut(BookingCreate):
    id: str
    createdAt: str
    userName: str = ""
    userEmail: str = ""
    packageTitle: str = ""
    createdBy: str = ""


# Shared, app-wide (not per-package) — one global pair of rates any user
# can view/update, surfaced via the currency icon on every package card.
class CurrencyRatesUpdate(BaseModel):
    thaiRate: str = ""
    malaysianRate: str = ""


class CurrencyRatesOut(CurrencyRatesUpdate):
    updatedAt: str = ""
    updatedBy: str = ""


# Admin-managed list of role names — one input field (name) for now, per
# the explicit "create first this, after i give another task" scope.
class RoleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class RoleOut(RoleCreate):
    id: str
    createdAt: str


# Accounts ledger entry — visible on the Account menu (admin + users whose
# assigned custom role is "Account"). paymentMode is a free string rather
# than an enum so the frontend's exact dropdown wording can change without
# a backend migration.
class AccountEntryCreate(BaseModel):
    slNo: str = ""
    date: str = ""
    invoiceNo: str = ""
    agent: str = ""
    clientName: str = ""
    # Free-text name field alongside the Client Name dropdown — e.g. the
    # actual traveler/contact's name when it differs from the booking's
    # client name. Not auto-filled from a synced booking, manual only.
    name: str = ""
    destination: str = ""
    handOverTo: str = ""
    # Separate amount fields — an entry can carry a debit amount, a credit
    # amount, or both. A booking-synced row's advance payment lands in
    # credit (received = credit), debit stays blank.
    debit: str = ""
    credit: str = ""
    # The booking's outstanding Balance Due (package price minus total
    # advance received so far) — same figure the Bookings page shows,
    # repeated on every synced row for that booking rather than computed
    # per payment. Free text on a manual entry.
    balance: str = ""
    paymentMode: str = ""  # "Cash" | "UPI" | "Net Banking" | "Cheque"
    description: str = ""


# A file (PDF / Word doc / image) attached to a ledger entry — receipts,
# transfer screenshots, etc. Stored on the entry document as a base64 data
# URL, same approach as BookingDocument; the list endpoint projects `data`
# out so only this metadata travels with the table.
class AccountAttachmentUpload(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    type: str = ""
    data: str = Field(min_length=1)


class AccountAttachmentMeta(BaseModel):
    id: str
    name: str
    type: str = ""
    size: int = 0  # decoded bytes
    uploadedAt: str = ""
    uploadedBy: str = ""
    uploadedByName: str = ""


class AccountAttachmentOut(AccountAttachmentMeta):
    data: str


class AccountEntryOut(AccountEntryCreate):
    id: str
    createdAt: str
    createdBy: str = ""
    # Only an admin can flip this (see routes/accounts.py) — everyone else
    # who can see the ledger sees it read-only.
    approved: bool = False
    attachments: list[AccountAttachmentMeta] = Field(default_factory=list)


class ApprovalUpdate(BaseModel):
    approved: bool


# Currency exchange ledger entry — visible on the Currency menu (admin +
# users whose assigned custom role is "Currency"). Same approval pattern
# as AccountEntry above (admin-only toggle, everyone else read-only).
class CurrencyEntryCreate(BaseModel):
    slNo: str = ""
    travelDate: str = ""
    passportNumber: str = ""
    clientName: str = ""  # optional — pick from the client directory
    # Free-text name alongside the optional Client Name dropdown, same as
    # AccountEntryCreate.name — for walk-ins who aren't a booked client.
    name: str = ""
    phoneNumber: str = ""
    currency: str = ""  # e.g. "USD" — see CURRENCY_OPTIONS in routes/currency_entries.py
    amount: str = ""  # INR amount for that currency
    clientAmount: str = ""  # amount the client handed over, in the foreign currency above
    currencyConversion: str = ""  # exchange rate applied (clientAmount x this ~= amount)
    bankConversion: str = ""  # rate the bank gave
    companyCurrencyConversion: str = ""  # rate the company applies internally
    paymentMode: str = ""  # same options as AccountEntryCreate.paymentMode
    handOverTo: str = ""
    transferTo: str = ""
    # Passport details — filled by the in-browser passport reader
    # (frontend lib/passportOcr.ts) or typed by hand. passportNumber above holds the passport number.
    surname: str = ""
    givenName: str = ""
    sex: str = ""
    dob: str = ""
    nationality: str = ""
    placeOfBirth: str = ""
    placeOfIssue: str = ""
    dateOfIssue: str = ""
    dateOfExpiry: str = ""
    fatherName: str = ""
    motherName: str = ""
    spouseName: str = ""
    address: str = ""
    fileNo: str = ""


class CurrencyEntryOut(CurrencyEntryCreate):
    id: str
    createdAt: str
    createdBy: str = ""
    approved: bool = False  # "Currency Out" approval (the original one)
    approvedIn: bool = False  # "Currency In" approval — same admin-only rule


# DMC Account ledger entry — payments made to / received from a DMC
# (destination management company). Same approval pattern as the Account
# and Currency ledgers: admin-only toggle, everyone else read-only.
class DmcAccountCreate(BaseModel):
    slNo: str = ""
    name: str = ""
    travelDate: str = ""
    paymentDate: str = ""
    paymentFrom: str = ""
    paymentTo: str = ""
    paymentMode: str = ""  # same options as AccountEntryCreate.paymentMode
    destination: str = ""
    numberOfTravelers: str = ""
    perPersonQuotation: str = ""
    # Pre-filled on the frontend as travelers x per-person quotation, but
    # stored as typed so a negotiated total can override it.
    totalAmount: str = ""
    note: str = ""


class DmcAccountOut(DmcAccountCreate):
    id: str
    createdAt: str
    createdBy: str = ""
    approved: bool = False


# Upcoming package departure — admin-managed, read by everyone on the
# Overview dashboard. month is "yyyy-mm" (from <input type="month">); dates
# is the day(s) of that month it departs, free text like "11, 18, 25".
class UpcomingPackageCreate(BaseModel):
    month: str = Field(min_length=7, max_length=7)
    dates: str = ""
    packageName: str = Field(min_length=1, max_length=200)
    landCost: str = ""


class UpcomingPackageOut(UpcomingPackageCreate):
    id: str
    createdAt: str


# Offer Section row (admin-only): a package and its target amount. The
# modal saves several rows at once via OfferBulkCreate.
class OfferCreate(BaseModel):
    packageName: str = Field(min_length=1, max_length=200)
    targetAmount: str = ""
    # Offer period (yyyy-mm-dd, both inclusive). Only bookings made in this
    # window count toward the target on the admin Overview. Blank = open-ended.
    fromDate: str = ""
    toDate: str = ""

    @model_validator(mode="after")
    def _dates_in_order(self):
        if self.fromDate and self.toDate and self.fromDate > self.toDate:
            raise ValueError("From date must be on or before To date")
        return self


class OfferBulkCreate(BaseModel):
    offers: list[OfferCreate] = Field(min_length=1, max_length=100)


class OfferOut(OfferCreate):
    id: str
    createdAt: str


# A regular user's own progress on one offer — percentage only. The target
# amount and booked value deliberately never leave the server.
class MyOfferProgress(BaseModel):
    id: str
    packageName: str
    fromDate: str = ""
    toDate: str = ""
    bookings: int = 0
    percent: int = 0  # 0-100, of this user's individual target
    met: bool = False


# Per-user, per-role granular CRUD permissions — a step finer than just
# "has the Account/Currency role or not". Admin dials these down on the
# Access page (routes/access.py); a role with no explicit grant record yet
# defaults to full access, matching the original all-or-nothing behavior so
# existing role holders don't lose access the moment this feature shipped.
class AccessGrant(BaseModel):
    roleName: str
    view: bool = True
    create: bool = True
    edit: bool = True
    delete: bool = True


class AccessUpdate(BaseModel):
    grants: list[AccessGrant]


class AccessOut(BaseModel):
    userId: str
    userName: str
    grants: list[AccessGrant]


# Room list ("rooming list") — the passenger-manifest-style document travel
# agencies prepare per booking: every adult/child/infant traveling under
# that booking gets their own passport-matching identity + flight fields,
# not just a headcount.
class RoomTraveler(BaseModel):
    category: str  # "adult" | "child" | "infant"
    givenName: str = ""
    surname: str = ""
    gender: str = ""  # "Male" | "Female" | "Other"
    passportNo: str = ""
    dob: str = ""
    arrivalAirport: str = ""
    departureAirport: str = ""
    # Remaining passport fields — filled by the in-browser passport reader
    # (frontend lib/passportOcr.ts) or typed by hand.
    nationality: str = ""
    placeOfBirth: str = ""
    placeOfIssue: str = ""
    dateOfIssue: str = ""
    dateOfExpiry: str = ""
    fatherName: str = ""
    motherName: str = ""
    spouseName: str = ""
    address: str = ""
    fileNo: str = ""


class RoomEntryCreate(BaseModel):
    slNo: str = ""
    packageType: str = "domestic"  # "domestic" | "international"
    packageId: str = ""
    # Snapshotted at save time, same reasoning as bookings' packageTitle —
    # survives the source package being renamed/deleted later.
    packageTitle: str = ""
    clientName: str = ""
    # Auto-filled from the selected client's booking (see
    # routes/bookings.py's /by-package), editable afterward.
    invoiceNumber: str = ""
    roomType: str = ""  # e.g. "Double" — see ROOM_TYPE_OPTIONS in the frontend
    numberOfRooms: str = ""
    sharingPerRoom: str = ""
    travelers: list[RoomTraveler] = Field(default_factory=list)


class RoomEntryOut(RoomEntryCreate):
    id: str
    createdAt: str
    createdBy: str = ""
