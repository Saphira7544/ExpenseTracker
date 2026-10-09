from fastapi import Request, HTTPException, status, Depends  
from app.core.config import settings
from app.core.auth import read_session_token
from app.services.users import get_user_by_id

def get_current_user(request: Request) -> dict:
    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    session = read_session_token(token)
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")

    user = get_user_by_id(session["user_id"])
    # A password reset bumps session_version, which signs out every older session.
    if user and session["v"] != user.get("session_version", 0):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session ended, please sign in again")
    # Block unapproved users from accessing the app
    if not user or not user.get("is_approved"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authorized or pending approval")

    return user

def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if not user.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins only")
    return user