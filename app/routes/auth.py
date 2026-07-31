from fastapi import APIRouter, HTTPException, status
from ..db import users_collection
from ..schemas import LoginRequest, TokenResponse, UserOut
from ..security import verify_password, create_token

router = APIRouter(prefix="/auth", tags=["auth"])


def serialize(u: dict) -> UserOut:
    return UserOut(id=str(u["_id"]), name=u["name"], email=u["email"], role=u["role"])


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    user = await users_collection.find_one({"email": body.email.lower()})
    if not user or not verify_password(body.password, user["password"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    token = create_token(str(user["_id"]), user["role"])
    return TokenResponse(access_token=token, user=serialize(user))
