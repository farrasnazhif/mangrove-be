from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import optional_user, require_manager, verify_login_csrf
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


@auth_router.post(
    "/login",
    response_model=LoginResponse,
    dependencies=[Depends(optional_user), Depends(verify_login_csrf)],
)
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

    if not user.is_active or user.role.value != "manager":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager account is inactive or unavailable",
        )

    session_token = create_session_token(
        user_id=str(user.id),
        role=user.role.value,
        session_version=user.session_version or 0,
    )
    csrf_token = generate_csrf_token(session_token)
    response.headers["Cache-Control"] = "no-store"

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
        max_age=settings.csrf_token_expire,
        path="/",
    )

    return LoginResponse(
        user=UserResponse.model_validate(user),
        csrf_token=csrf_token,
    )


@auth_router.post("/logout", response_model=MessageResponse)
async def logout(
    response: Response,
    user: User = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> MessageResponse:
    """Revoke all sessions for this manager, then clear browser cookies."""
    await session.execute(
        update(User).where(User.id == user.id).values(session_version=User.session_version + 1)
    )
    await session.commit()
    for name in (settings.session_cookie_name, settings.csrf_cookie_name):
        response.delete_cookie(
            key=name,
            path="/",
            secure=settings.session_cookie_secure,
            httponly=name == settings.session_cookie_name,
            samesite=settings.session_cookie_samesite,
        )
    response.headers["Cache-Control"] = "no-store"
    return MessageResponse(message="Logged out successfully")


@auth_router.get("/me", response_model=UserResponse)
async def get_me(response: Response, user: User = Depends(require_manager)) -> UserResponse:
    """Return currently authenticated user with server-derived role."""
    response.headers["Cache-Control"] = "no-store"
    return UserResponse.model_validate(user)


@auth_router.get(
    "/csrf",
    response_model=CSRFTokenResponse,
    dependencies=[Depends(optional_user)],
)
async def get_csrf_token(request: Request, response: Response) -> CSRFTokenResponse:
    """Generate and return a fresh CSRF token."""
    csrf_token = generate_csrf_token(request.cookies.get(settings.session_cookie_name, ""))
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf_token,
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        max_age=settings.csrf_token_expire,
        path="/",
    )
    return CSRFTokenResponse(csrf_token=csrf_token)
