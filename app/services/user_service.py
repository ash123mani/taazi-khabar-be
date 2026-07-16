from uuid import UUID

import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from jose import jwt
from datetime import datetime, timedelta, timezone

from app.models.user import User
from app.config import settings


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def _create_token(user_id: UUID) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.nextauth_secret.get_secret_value(), algorithm="HS256")


async def create_user(db: AsyncSession, email: str, password: str, name: str | None = None) -> User:
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise ValueError("Email already registered")

    user = User(
        email=email,
        password_hash=_hash_password(password),
        name=name,
    )
    db.add(user)
    await db.flush()
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> tuple[User, str] | None:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None or not user.password_hash or not _verify_password(password, user.password_hash):
        return None
    token = _create_token(user.id)
    return user, token


async def find_or_create_google_user(
    db: AsyncSession,
    email: str,
    google_id: str,
    name: str | None = None,
    avatar_url: str | None = None,
) -> User:
    existing = await db.execute(select(User).where(User.google_id == google_id))
    user = existing.scalar_one_or_none()
    if user:
        return user

    existing_email = await db.execute(select(User).where(User.email == email))
    user = existing_email.scalar_one_or_none()
    if user:
        user.google_id = google_id
        user.avatar_url = avatar_url or user.avatar_url
        user.name = name or user.name
        await db.flush()
        return user

    user = User(
        email=email,
        google_id=google_id,
        name=name,
        avatar_url=avatar_url,
        password_hash=None,
    )
    db.add(user)
    await db.flush()
    return user


async def get_user_by_id(db: AsyncSession, user_id: UUID) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
