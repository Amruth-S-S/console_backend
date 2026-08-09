from pydantic import BaseModel, EmailStr, Field, model_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=20)
    password: str = Field(min_length=6, max_length=128)


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=20)
    # Admin-only password reset — omit the field entirely to leave the
    # password unchanged (see exclude_unset in the update route).
    password: str | None = Field(default=None, min_length=6, max_length=128)


class UserOut(BaseModel):
    id: str
    name: str
    email: EmailStr
    phone: str | None = None
    role: str


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


class BookingOut(BookingCreate):
    id: str
    createdAt: str
    userName: str = ""
    userEmail: str = ""
    packageTitle: str = ""
    createdBy: str = ""
