from fastapi import APIRouter

from .endpoints import predict, scanner, sentiment, technical

api_router = APIRouter()

api_router.include_router(predict.router, prefix="/predict", tags=["predict"])
api_router.include_router(technical.router, prefix="/technical", tags=["technical"])
api_router.include_router(sentiment.router, prefix="/sentiment", tags=["sentiment"])
api_router.include_router(scanner.router, prefix="/scanner", tags=["scanner"])
