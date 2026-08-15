from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import get_settings
from app.core.rate_limit import client_ip, limiter
from app.core.security import REFRESH_COOKIE_NAME
from app.database import get_db
from app.models.user import User
from app.schemas.auth import LoginPickResponse, LoginRequest, TokenResponse, UserResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_refresh_cookie(response: Response, token: str, *, max_age_days: int) -> None:
    settings = get_settings()
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
        path="/api/v1/auth",
        max_age=max_age_days * 24 * 60 * 60,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path="/api/v1/auth")


@router.get("/login-picks", response_model=list[LoginPickResponse])
async def login_picks(db: AsyncSession = Depends(get_db)) -> list[LoginPickResponse]:
    picks = await auth_service.get_login_picks(db)
    return [LoginPickResponse(**pick) for pick in picks]


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    limiter.check(key=f"login:{client_ip(request)}", limit=10, window_seconds=60)
    token_response, raw_refresh, user = await auth_service.login(
        db, username=payload.username, password=payload.password
    )
    max_age = 7 if user.role == "parent" else 30
    _set_refresh_cookie(response, raw_refresh, max_age_days=max_age)
    return token_response


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    raw_refresh = request.cookies.get(REFRESH_COOKIE_NAME)
    if not raw_refresh:
        raise auth_service.AuthError("AUTH_TOKEN_EXPIRED")
    token_response, new_raw = await auth_service.refresh_access_token(
        db, raw_refresh_token=raw_refresh
    )
    if new_raw:
        _set_refresh_cookie(response, new_raw, max_age_days=30)
    return token_response


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> Response:
    raw_refresh = request.cookies.get(REFRESH_COOKIE_NAME)
    await auth_service.logout(db, raw_refresh_token=raw_refresh)
    _clear_refresh_cookie(response)
    return response


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)) -> UserResponse:
    return auth_service.user_to_response(user)
