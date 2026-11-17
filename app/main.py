from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.cors import APICORSMiddleware
from app.core.errors import install_error_handlers
from app.core.observability import RequestContextMiddleware, configure_app_logging
from app.core.openapi import install_openapi
from app.core.upload_limit import PhotoUploadLimitMiddleware
from app.schemas.common import ErrorResponse

configure_app_logging()
app = FastAPI(
    title="Mangrove Carbon Inventory API",
    version="0.1.0",
    description="P0 API contract. Routes labelled planned return 501 until their backlog feature is implemented.",
    responses={code: {"model": ErrorResponse} for code in (400, 401, 403, 404, 409, 422, 500, 501)},
)
app.add_middleware(PhotoUploadLimitMiddleware)
app.add_middleware(
    APICORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)
app.add_middleware(RequestContextMiddleware)
install_error_handlers(app)
app.include_router(api_router)
install_openapi(app)
