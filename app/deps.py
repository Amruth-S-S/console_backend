from fastapi import Header, HTTPException, status
from jose import JWTError
from .security import decode_token


class CurrentUser:
    def __init__(self, id: str, role: str):
        self.id = id
        self.role = role


async def get_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing or invalid authorization header")
    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_token(token)
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    sub = payload.get("sub")
    role = payload.get("role")
    if not sub or not role:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token payload")
    return CurrentUser(id=sub, role=role)
