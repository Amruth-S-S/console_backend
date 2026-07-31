from motor.motor_asyncio import AsyncIOMotorClient
from .config import settings

client = AsyncIOMotorClient(settings.MONGODB_URI)
db = client[settings.DB_NAME]
users_collection = db["users"]
packages_collection = db["packages"]
bookings_collection = db["bookings"]


async def ensure_indexes():
    await users_collection.create_index("email", unique=True)
    await packages_collection.create_index("createdAt")
    await bookings_collection.create_index("createdAt")
