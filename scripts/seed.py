"""Seed script: creates default admin user + NetSafe VPN app."""
import asyncio
from sqlalchemy import select
from app.database import async_session
from app.models.user import User
from app.models.app import App
from app.models.app_fact import AppFact
from app.models.global_config import GlobalConfig
from app.auth.security import hash_password
from app.utils.encryption import encrypt_value


async def seed():
    async with async_session() as db:
        # Create admin user
        result = await db.execute(select(User).where(User.username == "admin"))
        if not result.scalar_one_or_none():
            admin = User(
                username="admin",
                email="admin@aso.local",
                hashed_password=hash_password("myadmin1447"),
                role="admin",
                is_active=True,
            )
            db.add(admin)
            print("Created admin user (admin/myadmin1447)")

        # Create NetSafe VPN app
        result = await db.execute(select(App).where(App.package_name == "com.NetSafe.VPN"))
        app = result.scalar_one_or_none()
        if not app:
            app = App(name="NetSafe VPN", package_name="com.NetSafe.VPN", store="google_play", status="active")
            db.add(app)
            await db.flush()
            print("Created NetSafe VPN app")

            # Add known app facts
            facts = [
                ("encryption", "yes", True),
                ("kill_switch", "yes", True),
                ("split_tunneling", "yes", True),
            ]
            for key, value, verified in facts:
                db.add(AppFact(app_id=app.id, fact_key=key, fact_value=value, verified=verified))
            print("Added app facts: encryption, kill_switch, split_tunneling")

        # Seed default global config entries
        defaults = [
            ("anthropic_api_key", "", "Claude API key for AI suggestions and reasoning"),
            ("telegram_bot_token", "", "Telegram bot token for alerts and confirmations"),
            ("telegram_chat_id", "", "Telegram chat ID that receives notifications"),
            ("serpapi_key", "", "Optional SerpAPI key for external search signals"),
            ("google_api_discovery_url", "", "Optional Google discovery host or full URL override"),
            ("dry_run", "true", "Demo mode switch. True simulates actions, false allows live publish"),
            ("max_publish_per_day", "1", "Safety limit for how many changes can publish in one day"),
            ("max_publish_per_week", "5", "Safety limit for how many changes can publish in one week"),
            ("auto_approve_threshold", "0", "Maximum risk score allowed for auto-approval when manual approval is off"),
            ("manual_approval_required", "true", "If true, every suggestion waits for human approval first"),
            ("publish_after_approval", "true", "If true, approved suggestions are queued for publish automatically"),
            ("manual_trigger_cooldown_minutes", "15", "Minimum wait time between manual Run now actions for the same project"),
        ]
        for key, value, description in defaults:
            result = await db.execute(select(GlobalConfig).where(GlobalConfig.key == key))
            if not result.scalar_one_or_none():
                encrypted = encrypt_value(value) if key in {"anthropic_api_key", "telegram_bot_token", "serpapi_key"} else value
                db.add(GlobalConfig(key=key, value=encrypted, description=description))

        await db.commit()
        print("Seed completed!")


if __name__ == "__main__":
    asyncio.run(seed())
