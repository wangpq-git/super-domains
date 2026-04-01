"""一次性脚本：加密数据库中未加密的 credentials"""
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.db.session import async_session_maker
from app.models.platform_account import PlatformAccount
from app.core.encryption import encrypt_credentials, decrypt_credentials
from sqlalchemy import select


async def main():
    async with async_session_maker() as db:
        result = await db.execute(select(PlatformAccount))
        accounts = result.scalars().all()
        fixed = 0
        for acc in accounts:
            try:
                decrypt_credentials(acc.credentials)
            except Exception:
                try:
                    creds = json.loads(acc.credentials) if isinstance(acc.credentials, str) else acc.credentials
                    acc.credentials = encrypt_credentials(creds)
                    fixed += 1
                    print(f"Encrypted: {acc.platform}/{acc.account_name}")
                except Exception as e:
                    print(f"SKIP {acc.platform}/{acc.account_name}: {e}")
        await db.commit()
        print(f"Done. Fixed {fixed} accounts.")


if __name__ == "__main__":
    asyncio.run(main())