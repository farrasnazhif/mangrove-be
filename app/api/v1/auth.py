from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_manager
from app.core.config import settings
from app.core.security import (
    create_session_token,
    generate_csrf_token,
    verify_password,
)
from app.db.session import get_session
from app.models.user import User
from app.schemas.auth import (
    CSRFTokenResponse,
    LoginRequest,
    LoginResponse,
    MessageResponse,
    UserResponse,
)

auth_router = APIRouter(prefix="/auth", tags=["auth"])


@auth_router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> LoginResponse:
    """Authenticate with email and password, returning session cookie and CSRF token."""
    stmt = select(User).where(User.email == payload.email)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if (
        user is None
        or not user.hashed_password
        or not verify_password(payload.password, user.hashed_password)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    session_token = create_session_token(user_id=str(user.id), role=user.role.value)
    csrf_token = generate_csrf_token()

    # Set secure HttpOnly session cookie
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        max_age=settings.session_max_age,
        path="/",
    )

    # Set CSRF cookie (readable by JS to include in X-CSRF-Token header)
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf_token,
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        max_age=settings.session_max_age,
        path="/",
    )

    return LoginResponse(
        user=UserResponse.model_validate(user),
        csrf_token=csrf_token,
    )


@auth_router.post("/logout", response_model=MessageResponse)
async def logout(response: Response) -> MessageResponse:
    """Clear session and CSRF cookies."""
    response.delete_cookie(key=settings.session_cookie_name, path="/")
    response.delete_cookie(key=settings.csrf_cookie_name, path="/")
    return MessageResponse(message="Logged out successfully")


@auth_router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(require_manager)) -> UserResponse:
    """Return currently authenticated user with server-derived role."""
    return UserResponse.model_validate(user)


@auth_router.get("/csrf", response_model=CSRFTokenResponse)
async def get_csrf_token(response: Response) -> CSRFTokenResponse:
    """Generate and return a fresh CSRF token."""
    csrf_token = generate_csrf_token()
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf_token,
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        max_age=settings.session_max_age,
        path="/",
    )
    return CSRFTokenResponse(csrf_token=csrf_token)
