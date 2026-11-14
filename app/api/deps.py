from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decode_session_token, verify_csrf_token
from app.db.session import SessionLocal
from app.models.user import User, UserRole


def get_session_token_from_request(request: Request) -> str | None:
    """Extract raw session token from cookie or Authorization Bearer header."""
    token: str | None = request.cookies.get(settings.session_cookie_name)
    if not token:
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
    return token


async def get_optional_session(
    request: Request,
) -> AsyncIterator[AsyncSession | None]:
    """Only open a DB session if a valid session token is actually present."""
    token = get_session_token_from_request(request)
    if not token:
        yield None
        return

    try:
        payload = decode_session_token(token)
    except HTTPException:
        yield None
        return

    # If role is not manager, protected endpoints don't need DB lookup to reject
    if payload.get("role") != UserRole.manager.value:
        yield None
        return

    async with SessionLocal() as session:
        yield session


async def get_current_user(
    request: Request,
    session: AsyncSession | None = Depends(get_optional_session),
) -> User | None:
    """Extract current user from session token and verify against DB."""
    token = get_session_token_from_request(request)
    if not token or session is None:
        return None

    try:
        payload = decode_session_token(token)
    except HTTPException:
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    stmt = select(User).where(User.id == str(user_id))
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        return None

    return user


async def optional_user(
    user: User | None = Depends(get_current_user),
) -> User | None:
    """Optional user dependency for public routes (visitor = None)."""
    return user


async def require_manager(
    request: Request,
    session: AsyncSession | None = Depends(get_optional_session),
) -> User:
    """Require authenticated user with Manager role.

    Returns 401 if unauthenticated or token expired.
    Returns 403 if user role is not Manager.
    """
    token = get_session_token_from_request(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    try:
        payload = decode_session_token(token)
    except HTTPException as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=exc.detail,
        ) from exc

    role = payload.get("role")
    if role != UserRole.manager.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager access required",
        )

    user_id = payload.get("sub")
    if not user_id or session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    stmt = select(User).where(User.id == str(user_id))
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None or not user.is_active or user.role != UserRole.manager:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return user


async def verify_csrf(request: Request) -> None:
    """Verify CSRF token for state-changing requests when session cookie is present."""
    session_cookie = request.cookies.get(settings.session_cookie_name)
    if not session_cookie:
        return

    csrf_header = request.headers.get("x-csrf-token")
    csrf_cookie = request.cookies.get(settings.csrf_cookie_name)

    if not csrf_header or not csrf_cookie or not verify_csrf_token(csrf_header, csrf_cookie):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token validation failed",
        )
