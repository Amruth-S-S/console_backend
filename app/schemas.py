from pydantic import BaseModel, EmailStr, Field


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


class PackageDay(BaseModel):
    title: str = ""
    desc: str = ""
    images: list[str] = Field(default_factory=list)


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
    travelDate: str = ""
    finalPaymentDate: str = ""
    adults: str = "1"
    children: str = "0"
    adultPrice: str = ""
    childPrice: str = ""
    advancePayments: list[AdvancePayment] = Field(default_factory=list)
    invoiceNumber: str = ""
    invoiceDate: str = ""
    amount: str = ""
    transactionId: str = ""


class BookingOut(BookingCreate):
    id: str
    createdAt: str
    userName: str = ""
    packageTitle: str = ""
    createdBy: str = ""
