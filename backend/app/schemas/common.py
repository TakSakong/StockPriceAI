from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    data: T
    error: str | None = None


class PaginatedResponse(BaseModel, Generic[T]):
    data: list[T]
    meta: dict[str, Any]
    error: str | None = None
