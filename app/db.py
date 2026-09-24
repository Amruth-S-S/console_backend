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


async def ensure_indexes():
    await users_collection.create_index("email", unique=True)
    await packages_collection.create_index("createdAt")
    await bookings_collection.create_index("createdAt")
