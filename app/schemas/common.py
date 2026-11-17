from pydantic import BaseModel, ConfigDict, Field


class FieldError(BaseModel):
    field: str
    message: str
    type: str


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: list[FieldError] = Field(default_factory=list)
    request_id: str


class Page[T](BaseModel):
    items: list[T]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, from_attributes=True)
