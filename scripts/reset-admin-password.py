"""Reset a trade user's local bcrypt password (development helper).

Useful when a tenant/admin user was created while Supabase Auth was configured
but unreachable, leaving password_hash NULL and preventing local login.

Usage:
    python scripts/reset-admin-password.py admin@example.com new-password-123

Run inside the API container, or set DATABASE_URL to point at the local DB:
    docker compose -f docker-compose.mobile.yml exec api \
        python /app/scripts/reset-admin-password.py admin@example.com new-password-123
"""

import asyncio
import os
import sys

from sqlalchemy import select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "api"))

from app.database import AsyncSessionLocal
from app.models import User
from app.rls import bypass_rls_in_session
from app.security import get_password_hash


async def main(email: str, password: str) -> None:
    async with AsyncSessionLocal() as session:
        await bypass_rls_in_session(session)
        users = (await session.execute(select(User).where(User.email == email))).scalars().all()
        if not users:
            print(f"No user found with email: {email}")
            sys.exit(1)

        for user in users:
            user.password_hash = get_password_hash(password)
            user.supabase_uid = None
            print(f"Reset local password for {email} (tenant_id={user.tenant_id})")

        await session.commit()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <email> <new-password>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1], sys.argv[2]))
