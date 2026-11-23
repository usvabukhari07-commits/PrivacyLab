import bcrypt
from fastapi import Request, HTTPException
from app.db import log_event


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def current_user(request: Request):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def require_role(*roles):
    """Server-side authorization: use as a dependency on any route."""
    def checker(request: Request):
        user = current_user(request)
        if user["role"] not in roles:
            log_event(user["username"], "access_denied", "denied", request.url.path)
            raise HTTPException(status_code=403, detail="Access denied")
        return user
    return checker