"""Seed script: creates default admin user + NetSafe VPN app + demo suggestions."""
import asyncio
from datetime import datetime, timezone
from sqlalchemy import select
from app.database import async_session
from app.models.user import User
from app.models.app import App
from app.models.app_fact import AppFact
from app.models.global_config import GlobalConfig
from app.models.suggestion import Suggestion
from app.models.pipeline_run import PipelineRun
from app.auth.security import hash_password
from app.utils.encryption import encrypt_value


async def seed():
    async with async_session() as db:
        # --- Admin user ---
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

        # --- NetSafe VPN app ---
        result = await db.execute(select(App).where(App.package_name == "com.NetSafe.VPN"))
        app = result.scalar_one_or_none()
        if not app:
            app = App(name="NetSafe VPN", package_name="com.NetSafe.VPN", store="google_play", status="active")
            db.add(app)
            await db.flush()
            print("Created NetSafe VPN app")

            facts = [
                ("encryption", "yes", True),
                ("kill_switch", "yes", True),
                ("split_tunneling", "yes", True),
            ]
            for key, value, verified in facts:
                db.add(AppFact(app_id=app.id, fact_key=key, fact_value=value, verified=verified))
            print("Added app facts: encryption, kill_switch, split_tunneling")

        await db.flush()

        # --- Demo pipeline run + suggestions (only if no suggestions exist) ---
        existing_sugg = await db.execute(select(Suggestion).where(Suggestion.app_id == app.id).limit(1))
        if not existing_sugg.scalar_one_or_none():
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            demo_run = PipelineRun(
                app_id=app.id,
                status="completed",
                trigger="manual",
                steps_completed=9,
                total_steps=9,
                suggestions_generated=3,
                approvals_created=1,
                started_at=now,
                completed_at=now,
            )
            db.add(demo_run)
            await db.flush()

            demo_suggestions = [
                Suggestion(
                    app_id=app.id,
                    pipeline_run_id=demo_run.id,
                    suggestion_type="listing",
                    field_name="short_description",
                    old_value="Fast and secure VPN for everyone.",
                    new_value="Military-grade encrypted VPN — browse securely, block ads, and protect your privacy on any network.",
                    reasoning="Short description was too generic. New version highlights key features (encryption, ad-blocking) and appeals to privacy-conscious users.",
                    risk_score=0,
                    status="pending",
                    publish_status=None,
                ),
                Suggestion(
                    app_id=app.id,
                    pipeline_run_id=demo_run.id,
                    suggestion_type="listing",
                    field_name="title",
                    old_value="NetSafe VPN",
                    new_value="NetSafe VPN — Secure & Fast",
                    reasoning="Adding a subtitle to the title improves keyword density and click-through rate.",
                    risk_score=1,
                    status="rejected",
                    publish_status="blocked",
                    publish_message="Rejected in review.",
                    reviewed_by="admin",
                    last_transition_at=now,
                ),
                Suggestion(
                    app_id=app.id,
                    pipeline_run_id=demo_run.id,
                    suggestion_type="listing",
                    field_name="long_description",
                    old_value="NetSafe VPN keeps you safe online.",
                    new_value="NetSafe VPN uses AES-256 encryption to protect your data on public Wi-Fi. Features include Kill Switch, Split Tunneling, and a strict no-logs policy.",
                    reasoning="Long description lacked feature detail. Updated version emphasizes technical credibility and trust signals.",
                    risk_score=0,
                    status="published",
                    publish_status="published",
                    published_live=True,
                    published_at=now,
                    publish_message="Published successfully.",
                    reviewed_by="admin",
                    last_transition_at=now,
                ),
            ]
            for s in demo_suggestions:
                db.add(s)
            print(f"Created demo pipeline run #{demo_run.id} with {len(demo_suggestions)} suggestions (1 pending, 1 rejected, 1 published)")

        # --- Global config defaults ---
        defaults = [
            ("anthropic_api_key", "", "Claude API key for AI suggestions and reasoning"),
            ("telegram_bot_token", "", "Telegram bot token for alerts and confirmations"),
            ("telegram_chat_id", "", "Telegram chat ID that receives notifications"),
            ("serpapi_key", "", "Optional SerpAPI key for external search signals"),
            ("google_api_discovery_url", "", "Optional Google discovery host or full URL override"),
            ("dry_run", "true", "Demo mode switch. True = simulate actions, false = live publish to Google Play"),
            ("max_publish_per_day", "1", "Safety limit: max changes published per day"),
            ("max_publish_per_week", "5", "Safety limit: max changes published per week"),
            ("auto_approve_threshold", "0", "Max risk score for auto-approval (when manual approval is off)"),
            ("manual_approval_required", "true", "If true, every suggestion waits for human approval first"),
            ("publish_after_approval", "true", "If true, approved suggestions are queued for publish automatically"),
            ("manual_trigger_cooldown_minutes", "15", "Minimum wait time between manual Run Now actions per project"),
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
