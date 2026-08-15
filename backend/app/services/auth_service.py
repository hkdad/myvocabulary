from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    refresh_token_expiry,
    verify_password,
)
from app.models.learner import Learner
from app.models.user import RefreshToken, User
from app.schemas.auth import LearnerProfileResponse, TokenResponse, UserResponse
from app.services import loop_engine
from app.services.learner_profile import resolve_learner_emoji


class AuthError(HTTPException):
    def __init__(self, detail: str, status_code: int = status.HTTP_401_UNAUTHORIZED) -> None:
        super().__init__(status_code=status_code, detail={"code": detail, "message": detail})


def user_to_response(user: User) -> UserResponse:
    learner = None
    if user.learner_profile is not None:
        profile = user.learner_profile
        learner = LearnerProfileResponse(
            id=profile.id,
            display_name=profile.display_name,
            age=profile.age,
            english_level=profile.english_level,
            ui_mode=profile.ui_mode,
            emoji=resolve_learner_emoji(profile.emoji, profile.display_name),
            avatar_url=profile.avatar_url,
            daily_practice_goal=loop_engine.daily_practice_goal(profile),
        )
    return UserResponse(
        id=user.id,
        username=user.username,
        role=user.role,
        learner=learner,
    )


async def authenticate_user(db: AsyncSession, *, username: str, password: str) -> User:
    result = await db.execute(
        select(User).options(selectinload(User.learner_profile)).where(User.username == username)
    )
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise AuthError("AUTH_INVALID_CREDENTIALS")
    if not verify_password(password, user.password_hash):
        raise AuthError("AUTH_INVALID_CREDENTIALS")
    return user


async def create_refresh_token_record(
    db: AsyncSession, *, user: User, device_label: str | None = None
) -> tuple[str, RefreshToken]:
    raw_token = generate_refresh_token()
    record = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(raw_token),
        device_label=device_label,
        expires_at=refresh_token_expiry(role=user.role),
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return raw_token, record


async def login(
    db: AsyncSession, *, username: str, password: str, device_label: str | None = None
) -> tuple[TokenResponse, str, User]:
    user = await authenticate_user(db, username=username, password=password)
    access_token = create_access_token(user_id=user.id, role=user.role)
    raw_refresh, _ = await create_refresh_token_record(db, user=user, device_label=device_label)
    return TokenResponse(access_token=access_token), raw_refresh, user


async def refresh_access_token(
    db: AsyncSession, *, raw_refresh_token: str
) -> tuple[TokenResponse, str | None]:
    token_hash = hash_refresh_token(raw_refresh_token)
    result = await db.execute(
        select(RefreshToken)
        .options(selectinload(RefreshToken.user).selectinload(User.learner_profile))
        .where(RefreshToken.token_hash == token_hash)
    )
    record = result.scalar_one_or_none()
    now = datetime.now(UTC)

    if record is None or record.revoked_at is not None:
        raise AuthError("AUTH_TOKEN_REVOKED")
    expires_at = record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= now:
        raise AuthError("AUTH_TOKEN_EXPIRED")
    if not record.user.is_active:
        raise AuthError("AUTH_TOKEN_REVOKED")

    record.revoked_at = now
    access_token = create_access_token(user_id=record.user.id, role=record.user.role)
    new_raw, _ = await create_refresh_token_record(db, user=record.user)
    return TokenResponse(access_token=access_token), new_raw


async def logout(db: AsyncSession, *, raw_refresh_token: str | None) -> None:
    if not raw_refresh_token:
        return
    token_hash = hash_refresh_token(raw_refresh_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    record = result.scalar_one_or_none()
    if record is None or record.revoked_at is not None:
        return
    record.revoked_at = datetime.now(UTC)
    await db.commit()


async def get_login_picks(db: AsyncSession) -> list[dict[str, str]]:
    result = await db.execute(
        select(User)
        .options(selectinload(User.learner_profile))
        .where(User.is_active.is_(True), User.role.in_(["parent", "learner"]))
    )
    users = result.scalars().all()
    picks: list[dict[str, str]] = []
    parents = [user for user in users if user.role == "parent"]
    learners = [
        user for user in users if user.role == "learner" and user.learner_profile is not None
    ]

    for user in sorted(parents, key=lambda row: row.username):
        picks.append(
            {
                "label": "Parent",
                "emoji": "👨‍👩‍👧‍👦",
                "role": "parent",
            }
        )

    for user in sorted(learners, key=lambda row: row.learner_profile.display_name):  # type: ignore[union-attr]
        profile: Learner = user.learner_profile  # type: ignore[assignment]
        picks.append(
            {
                "label": profile.display_name,
                "emoji": resolve_learner_emoji(profile.emoji, profile.display_name),
                "role": "learner",
            }
        )
    return picks


async def get_user_by_id(db: AsyncSession, user_id: int) -> User:
    result = await db.execute(
        select(User).options(selectinload(User.learner_profile)).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise AuthError("AUTH_INVALID_CREDENTIALS")
    return user
