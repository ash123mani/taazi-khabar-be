from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.articles import router as articles_router
from app.api.quizzes import router as quizzes_router
from app.api.history import router as history_router
from app.api.admin import router as admin_router

api_router = APIRouter()

api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(articles_router, prefix="/articles", tags=["articles"])
api_router.include_router(quizzes_router, prefix="/quizzes", tags=["quizzes"])
api_router.include_router(history_router, prefix="/history", tags=["history"])
api_router.include_router(admin_router, prefix="/admin", tags=["admin"])
