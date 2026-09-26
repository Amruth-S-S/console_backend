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
# assigned custom role is "Account"). debitCredit/paymentMode are free
# strings rather than enums so the frontend's exact dropdown wording can
# change without a backend migration.
class AccountEntryCreate(BaseModel):
    slNo: str = ""
    date: str = ""
    invoiceNo: str = ""
    agent: str = ""
    clientName: str = ""
    destination: str = ""
    handOverTo: str = ""
    debitCredit: str = ""  # "Debit" | "Credit"
    balance: str = ""
    paymentMode: str = ""  # "Cash" | "UPI" | "Net Banking" | "Cheque"
    description: str = ""


class AccountEntryOut(AccountEntryCreate):
    id: str
    createdAt: str
    createdBy: str = ""
    # Only an admin can flip this (see routes/accounts.py) — everyone else
    # who can see the ledger sees it read-only.
    approved: bool = False


class ApprovalUpdate(BaseModel):
    approved: bool


# Currency exchange ledger entry — visible on the Currency menu (admin +
# users whose assigned custom role is "Currency"). Same approval pattern
# as AccountEntry above (admin-only toggle, everyone else read-only).
class CurrencyEntryCreate(BaseModel):
    slNo: str = ""
    travelDate: str = ""
    passportNumber: str = ""
    clientName: str = ""
    phoneNumber: str = ""
    currency: str = ""  # e.g. "USD" — see CURRENCY_OPTIONS in routes/currency_entries.py
    amount: str = ""  # INR amount for that currency
    clientAmount: str = ""  # amount the client handed over, in the foreign currency above
    currencyConversion: str = ""  # exchange rate applied (clientAmount x this ~= amount)
    handOverTo: str = ""


class CurrencyEntryOut(CurrencyEntryCreate):
    id: str
    createdAt: str
    createdBy: str = ""
    approved: bool = False


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
