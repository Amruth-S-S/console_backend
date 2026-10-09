from motor.motor_asyncio import AsyncIOMotorClient
from .config import settings

client = AsyncIOMotorClient(settings.MONGODB_URI)
db = client[settings.DB_NAME]
users_collection = db["users"]
packages_collection = db["packages"]
bookings_collection = db["bookings"]
# Small shared app-wide settings (e.g. currency exchange rates) — one
# document per setting, keyed by _id, not tied to any specific package.
settings_collection = db["settings"]
# Admin-managed role names — a separate concept from users_collection's own
# "role" field (still hardcoded to "admin"/"user" for actual access control
# right now). This is the first piece of a role management feature; more
# is coming per the user's own "after i give another task" plan.
roles_collection = db["roles"]
# Accounts ledger entries — visible to admin and to users whose assigned
# custom role (roles_collection, via users.roleId) is named "Account".
accounts_collection = db["accounts"]
# Currency exchange ledger entries — same shape of gating, visible to admin
# and to users whose assigned custom role is named "Currency". Distinct
# from settings_collection's currency_rates document (one global Thai/
# Malaysian rate pair) — this is a per-client exchange record.
currency_entries_collection = db["currency_entries"]
# Per-user, per-role granular CRUD permissions (view/create/edit/delete) —
# keyed by (userId, roleName). A role assigned to a user but with no
# document here yet defaults to full access (see routes/access.py), so this
# collection only ever holds explicit *restrictions* an admin has dialed in
# on the Access page.
access_collection = db["access"]
# Room list ("rooming list") entries — passenger-manifest documents per
# booking. Common to every logged-in account, same as the Travel List page
# (not scoped to who created it — see routes/rooms.py).
rooms_collection = db["rooms"]
# DMC (destination management company) payment ledger — same gating shape
# as accounts/currency: admin plus users assigned the "DMC Account" role.
dmc_accounts_collection = db["dmc_accounts"]
# Hotel vouchers — same gating as the ledgers: admin plus users assigned the
# "Hotel Voucher" role (routes/hotel_vouchers.py).
hotel_vouchers_collection = db["hotel_vouchers"]
# Admin-curated "upcoming departures" (month, dates, package, land cost),
# shown to every logged-in user at the top of the Overview dashboard.
upcoming_packages_collection = db["upcoming_packages"]
# Admin-only offer targets — one document per package + target amount row.
offers_collection = db["offers"]


async def ensure_indexes():
    await users_collection.create_index("email", unique=True)
    await packages_collection.create_index("createdAt")
    await bookings_collection.create_index("createdAt")
