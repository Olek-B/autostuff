"""
AutoClothes scheduled jobs.
- Daily outfit suggestion at 7:00 AM
- Weekly laundry reset on Sunday at 2:00 AM
"""

import logging
from datetime import time as dt_time

from telegram.ext import JobQueue

from config import config
from database import mark_items_worn, reset_weekly_laundry, get_all_config
from .handlers import generate_outfit, _format_outfit_message

logger = logging.getLogger(__name__)


async def daily_outfit_job(context) -> None:
    """Scheduled job: Send outfit suggestion at 7:00 AM daily."""
    logger.info("Running daily outfit job (7:00 AM)")

    try:
        if config.auto_outfit_disabled:
            logger.info("Auto-outfit disabled, skipping")
            return

        outfit = await generate_outfit(context)

        if outfit is None:
            logger.info("No suitable outfit found for daily suggestion")
            return

        message = "☀️ <b>Good Morning!</b>\n\n" + _format_outfit_message(outfit)

        await context.bot.send_message(
            chat_id=config.allowed_user_id,
            text=message,
            parse_mode="HTML"
        )

        worn_ids = [outfit.get("top_id"), outfit.get("bottom_id"), outfit.get("outer_id")]
        worn_ids = [id_ for id_ in worn_ids if id_ is not None]
        if worn_ids:
            await mark_items_worn(worn_ids)

    except Exception as e:
        logger.exception(f"Error in daily outfit job: {e}")


async def weekly_laundry_job(context) -> None:
    """Scheduled job: Reset laundry tracking every Sunday at 2:00 AM."""
    logger.info("Running weekly laundry reset (Sunday 2:00 AM)")

    try:
        count = await reset_weekly_laundry()
        logger.info(f"Reset {count} items in weekly laundry job")

        if config.laundry_notification:
            await context.bot.send_message(
                chat_id=config.allowed_user_id,
                text=f"🧺 Weekly laundry reset complete!\n{count} items are now available."
            )
    except Exception as e:
        logger.exception(f"Error in weekly laundry job: {e}")


def register_schedulers(job_queue: JobQueue) -> None:
    """Register all AutoClothes scheduled jobs."""
    
    # Daily outfit suggestion at 7:00 AM
    job_queue.run_daily(
        daily_outfit_job,
        time=dt_time(7, 0, 0),
        name="daily_outfit"
    )
    logger.info("Scheduled daily outfit job at 7:00 AM")

    # Weekly laundry reset on Sunday at 2:00 AM
    job_queue.run_daily(
        weekly_laundry_job,
        time=dt_time(2, 0, 0),
        days=[6],  # Sunday (0=Monday, 6=Sunday)
        name="weekly_laundry"
    )
    logger.info("Scheduled weekly laundry job on Sunday at 2:00 AM")
