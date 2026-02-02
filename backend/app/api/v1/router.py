from fastapi import APIRouter
from app.api.v1 import disease

api_router = APIRouter()
api_router.include_router(disease.router, prefix="/diseases", tags=["diseases"])