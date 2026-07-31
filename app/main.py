from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .db import users_collection, ensure_indexes
from .security import hash_password
from .routes import auth, users, packages, bookings


async def seed_admin():
    if await users_collection.find_one({"role": "admin"}):
        return
    await users_collection.insert_one({
        "name": settings.ADMIN_NAME,
        "email": settings.ADMIN_EMAIL.lower(),
        "password": hash_password(settings.ADMIN_PASSWORD),
        "role": "admin",
    })
    print(f"Seeded admin: {settings.ADMIN_EMAIL}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_indexes()
    await seed_admin()
    yield


app = FastAPI(title="Auth Dashboard API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(packages.router)
app.include_router(bookings.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
