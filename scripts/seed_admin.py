"""
Seed script to create admin user with TOTP 2FA
"""
import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select
from backend.models.user import User
from backend.utils.security import get_password_hash, generate_totp_secret, get_totp_uri
from backend.config import settings
import pyotp


async def seed_admin():
    """Create admin user with TOTP"""

    # Create async engine
    database_url = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
    engine = create_async_engine(database_url, echo=True)

    AsyncSessionLocal = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    async with AsyncSessionLocal() as session:
        # Check if admin exists
        result = await session.execute(
            select(User).where(User.username == "admin")
        )
        existing_admin = result.scalar_one_or_none()

        if existing_admin:
            print("✓ Admin user already exists")
            print(f"  Username: {existing_admin.username}")
            print(f"  Email: {existing_admin.email}")

            if existing_admin.totp_secret:
                uri = get_totp_uri(existing_admin.totp_secret, existing_admin.username)
                print(f"\n  TOTP URI: {uri}")
                print(f"  TOTP Secret: {existing_admin.totp_secret}")

            return

        # Generate TOTP secret
        totp_secret = generate_totp_secret()

        # Create admin user
        admin = User(
            username="admin",
            email="admin@healthcare-ai.local",
            hashed_password=get_password_hash("admin123"),  # Change in production!
            totp_secret=totp_secret,
            totp_enabled=True,
            role="admin",
            is_active=True,
            is_verified=True
        )

        session.add(admin)
        await session.commit()
        await session.refresh(admin)

        # Generate TOTP URI for QR code
        uri = get_totp_uri(totp_secret, admin.username)

        print("✓ Admin user created successfully!")
        print(f"\n  Username: {admin.username}")
        print(f"  Password: admin123  (CHANGE THIS IN PRODUCTION!)")
        print(f"  Email: {admin.email}")
        print(f"  Role: {admin.role}")
        print(f"\n  TOTP 2FA Enabled")
        print(f"  TOTP Secret: {totp_secret}")
        print(f"  TOTP URI (scan with authenticator app):")
        print(f"  {uri}")
        print(f"\n  Current TOTP token: {pyotp.TOTP(totp_secret).now()}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_admin())
