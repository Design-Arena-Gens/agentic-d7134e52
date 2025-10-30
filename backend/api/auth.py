"""Authentication API endpoints - JWT + TOTP 2FA"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import timedelta

from backend.database import get_db
from backend.models.user import User
from backend.utils.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    decode_access_token,
    generate_totp_secret,
    verify_totp,
    get_totp_uri,
    generate_qr_code,
)
from backend.config import settings

router = APIRouter()
security = HTTPBearer()


# Pydantic schemas
class UserRegister(BaseModel):
    username: str
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    username: str
    password: str
    totp_token: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    username: str


class Enable2FAResponse(BaseModel):
    secret: str
    qr_code: str
    uri: str


class Verify2FA(BaseModel):
    totp_token: str


# Dependency to get current user
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Get current authenticated user from JWT token"""
    token = credentials.credentials
    payload = decode_access_token(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )

    return user


@router.post("/register", response_model=TokenResponse)
async def register(user_data: UserRegister, db: AsyncSession = Depends(get_db)):
    """Register new user"""
    # Check if user exists
    result = await db.execute(
        select(User).where(
            (User.username == user_data.username) | (User.email == user_data.email)
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already registered"
        )

    # Create user
    user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        is_active=True,
        is_verified=True,
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Create token
    access_token = create_access_token(
        data={"sub": str(user.id), "username": user.username}
    )

    return TokenResponse(
        access_token=access_token,
        user_id=str(user.id),
        username=user.username
    )


@router.post("/login", response_model=TokenResponse)
async def login(credentials: UserLogin, db: AsyncSession = Depends(get_db)):
    """Login user with password (and optional TOTP)"""
    # Find user
    result = await db.execute(
        select(User).where(User.username == credentials.username)
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )

    # Check 2FA if enabled
    if user.totp_enabled:
        if not credentials.totp_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="TOTP token required"
            )

        if not verify_totp(user.totp_secret, credentials.totp_token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid TOTP token"
            )

    # Create token
    access_token = create_access_token(
        data={"sub": str(user.id), "username": user.username}
    )

    return TokenResponse(
        access_token=access_token,
        user_id=str(user.id),
        username=user.username
    )


@router.post("/2fa/enable", response_model=Enable2FAResponse)
async def enable_2fa(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Enable TOTP 2FA for current user"""
    if current_user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA already enabled"
        )

    # Generate secret
    secret = generate_totp_secret()
    uri = get_totp_uri(secret, current_user.username)
    qr_code = generate_qr_code(uri)

    # Save secret (not enabled yet until verified)
    current_user.totp_secret = secret
    await db.commit()

    return Enable2FAResponse(
        secret=secret,
        qr_code=qr_code,
        uri=uri
    )


@router.post("/2fa/verify")
async def verify_2fa_enable(
    verify_data: Verify2FA,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Verify TOTP token and enable 2FA"""
    if not current_user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA not initialized. Call /2fa/enable first"
        )

    if not verify_totp(current_user.totp_secret, verify_data.totp_token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid TOTP token"
        )

    # Enable 2FA
    current_user.totp_enabled = True
    await db.commit()

    return {"message": "2FA enabled successfully"}


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user info"""
    return {
        "id": str(current_user.id),
        "username": current_user.username,
        "email": current_user.email,
        "role": current_user.role,
        "totp_enabled": current_user.totp_enabled,
    }
