from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Cookie, HTTPException, Request, Response, status

from app.config import get_settings
from app.dependencies import DbSession, Notifier
from app.models import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from app.schemas.user import UserOut
from app.services import auth as auth_service
from app.services import notifications as notification_service
from app.services import rate_limit
from app.services.auth import InvalidRefreshToken, normalize_email
from app.utils.security import create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "sc_refresh_token"

RefreshCookie = Annotated[str | None, Cookie(alias=REFRESH_COOKIE)]


def _set_refresh_cookie(response: Response, raw: str) -> None:
    settings = get_settings()
    response.set_cookie(
        REFRESH_COOKIE,
        raw,
        max_age=settings.refresh_token_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path=settings.refresh_cookie_path,
    )


def _token_response(user: User) -> TokenResponse:
    access_token, expires_in = create_access_token(user.id, user.role)
    return TokenResponse(access_token=access_token, expires_in=expires_in, user=UserOut.model_validate(user))


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserOut)
def register(
    payload: RegisterRequest, request: Request, db: DbSession, background_tasks: BackgroundTasks, notifier: Notifier
) -> User:
    rate_limit.hit(rate_limit.REGISTER_PER_IP, rate_limit.client_ip(request))
    user = auth_service.register_user(
        db,
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        password=payload.password,
        department_id=payload.department_id,
    )
    db.commit()
    background_tasks.add_task(notifier.dispatch_pending)  # welcome email
    return user


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, response: Response, db: DbSession) -> TokenResponse:
    # Counted before checking the password, so failed guesses use up the allowance too.
    rate_limit.hit(rate_limit.LOGIN_PER_IP, rate_limit.client_ip(request))
    rate_limit.hit(rate_limit.LOGIN_PER_ACCOUNT, normalize_email(payload.email))
    user = auth_service.authenticate(db, payload.email, payload.password)
    raw = auth_service.issue_refresh_token(db, user)
    db.commit()
    _set_refresh_cookie(response, raw)
    return _token_response(user)


@router.post("/refresh", response_model=TokenResponse)
def refresh(request: Request, response: Response, db: DbSession, refresh_token: RefreshCookie = None) -> TokenResponse:
    rate_limit.hit(rate_limit.REFRESH_PER_IP, rate_limit.client_ip(request))
    if not refresh_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, InvalidRefreshToken.message)
    try:
        user, raw = auth_service.rotate_refresh_token(db, refresh_token)
    except InvalidRefreshToken:
        db.commit()  # persist reuse-detection revocations before the error response
        raise

    db.commit()
    _set_refresh_cookie(response, raw)
    return _token_response(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, db: DbSession, refresh_token: RefreshCookie = None) -> None:
    if refresh_token:
        auth_service.revoke_refresh_token(db, refresh_token)
        db.commit()
    settings = get_settings()
    response.delete_cookie(
        REFRESH_COOKIE, path=settings.refresh_cookie_path, secure=settings.cookie_secure, httponly=True, samesite="lax"
    )


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED, response_model=MessageResponse)
def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    db: DbSession,
    background_tasks: BackgroundTasks,
    notifier: Notifier,
) -> MessageResponse:
    # Limited per address whether or not an account exists, so the limit reveals nothing either.
    rate_limit.hit(rate_limit.FORGOT_PASSWORD_PER_IP, rate_limit.client_ip(request))
    rate_limit.hit(rate_limit.FORGOT_PASSWORD_PER_ACCOUNT, normalize_email(payload.email))
    result = auth_service.create_password_reset(db, payload.email)
    if result is not None:
        user, raw = result
        notification = notification_service.record_password_reset(db, user)
        db.commit()
        # The link lives only in memory until the email is sent; it is never stored.
        link = f"{get_settings().frontend_url}/reset-password?token={raw}"
        background_tasks.add_task(notifier.deliver_password_reset, notification.id, link)
    # Same response whether or not the account exists.
    return MessageResponse(message="If an account exists for this email, a password reset link has been sent.")


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(payload: ResetPasswordRequest, request: Request, db: DbSession) -> MessageResponse:
    rate_limit.hit(rate_limit.RESET_PASSWORD_PER_IP, rate_limit.client_ip(request))
    auth_service.reset_password(db, payload.token, payload.new_password)
    db.commit()
    return MessageResponse(message="Password updated. Please log in with your new password.")
