import asyncio
import os
import sys

# Append the project root to the python path so it can be run directly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import engine, AsyncSessionLocal
from app.models import Base  # This loads all models into Base.metadata
from app.db import crud

async def init_db_and_seed_admin():
    print("⏳ Connecting to Supabase to initialize models...")
    
    # Create the user table if it doesn't already exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    print("✅ Schema sync complete. Models verified.")

    # We need to manually prompt for the admin Chat ID since it is 
    # not in the .env anymore.
    print("\n--- Seed First Administrator ---")
    chat_id = input("Enter your Telegram Chat ID: ").strip()
    
    if not chat_id:
        print("❌ Error: Chat ID cannot be empty.")
        return
        
    async with AsyncSessionLocal() as db:
        existing_user = await crud.get_user_by_telegram_id(db, chat_id)
        if existing_user:
            if not existing_user.is_active:
                existing_user.is_active = True
                await db.commit()
                print(f"✅ User {chat_id} already existed. Elevated to ACTIVE.")
            else:
                print(f"ℹ️ User {chat_id} is already ACTIVE. Skipping.")
        else:
            await crud.create_user(db, chat_id, is_active=True)
            print(f"✅ User {chat_id} created and set to ACTIVE.")
            
    print("\n🚀 System Ready. Your Telegram Bot is now secured behind RBAC.")

if __name__ == "__main__":
    asyncio.run(init_db_and_seed_admin())
