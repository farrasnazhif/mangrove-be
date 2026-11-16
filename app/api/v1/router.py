from fastapi import APIRouter, Depends

from app.api.deps import optional_user, require_manager
from app.api.v1.auth import auth_router
from app.models.user import User
from app.schemas.auth import UserResponse

api_router = APIRouter(prefix="/api/v1")

# Mount auth routes (/api/v1/auth/login, /api/v1/auth/logout, /api/v1/auth/me, /api/v1/auth/csrf)
api_router.include_router(auth_router)


@api_router.get("/health")
async def health(_: User | None = Depends(optional_user)) -> dict[str, str]:
    """Health check endpoint accessible to all visitors."""
    return {"status": "ok"}


@api_router.get("/me", response_model=UserResponse, tags=["auth"])
async def me(user: User = Depends(require_manager)) -> UserResponse:
    """Return currently authenticated user with server-derived role."""
    return UserResponse.model_validate(user)
