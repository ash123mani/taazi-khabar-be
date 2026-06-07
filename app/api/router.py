from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.articles import router as articles_router
from app.api.quizzes import router as quizzes_router
from app.api.history import router as history_router
from app.api.admin import router as admin_router
from app.api.scraping import router as scraping_router
from app.api.categories import router as categories_router

api_router = APIRouter()

api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(articles_router, prefix="/articles", tags=["articles"])
api_router.include_router(quizzes_router, prefix="/quizzes", tags=["quizzes"])
api_router.include_router(history_router, prefix="/history", tags=["history"])
api_router.include_router(admin_router, prefix="/admin", tags=["admin"])
api_router.include_router(scraping_router, prefix="/scraping", tags=["scraping"])
api_router.include_router(categories_router, prefix="/categories", tags=["categories"])

from app.api.bookmarks import router as bookmarks_router
api_router.include_router(bookmarks_router, prefix="/bookmarks", tags=["bookmarks"])

from app.api.analytics import router as analytics_router
api_router.include_router(analytics_router, prefix="/analytics", tags=["analytics"])
