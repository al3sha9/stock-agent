import asyncio
from app.db.session import engine
from app.db.base import Base
# Import models to ensure they are registered with Base.metadata
from app.db.models import Watchlist, TriggerEvent

async def reset_database():
    async with engine.begin() as conn:
        print("Dropping all tables...")
        await conn.run_sync(Base.metadata.drop_all)
        print("Creating all tables with new schema...")
        await conn.run_sync(Base.metadata.create_all)
    print("Database migration complete.")

if __name__ == "__main__":
    asyncio.run(reset_database())
