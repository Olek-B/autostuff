"""
AutoStuff - Modular automation bot.
Main entry point that loads feature modules based on configuration.

PythonAnywhere Deployment:
    Run as "Always-on task" with command:
    python /home/yourusername/autoclothes/bot.py

    The bot uses long polling and runs indefinitely.
"""

import asyncio
import logging
import os

from telegram import Update
from telegram.ext import Application
from telegram.error import NetworkError

from config import config, get_config
import database as db

# =============================================================================
# CONFIGURATION
# =============================================================================

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=getattr(logging, config.log_level, logging.INFO)
)
logger = logging.getLogger(__name__)


# =============================================================================
# ERROR HANDLER
# =============================================================================

async def error_handler(update, context) -> None:
    """Log errors caused by updates."""
    logger.error(f"Update {update} caused error: {context.error}")


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

async def post_init(application: Application) -> None:
    """Initialize database after application starts."""
    await db.init_database()
    logger.info("Database initialized")


def load_feature_modules(application) -> None:
    """Load and register enabled feature modules."""
    
    # AutoClothes module
    if config.is_feature_enabled("autoclothes"):
        logger.info("Loading AutoClothes module...")
        
        # Validate dependencies
        if not config.groq_api_key:
            logger.error("AutoClothes requires GROQ_API_KEY - module disabled")
        elif not config.telegram_bot_token:
            logger.error("AutoClothes requires TELEGRAM_BOT_TOKEN - module disabled")
        else:
            from modules.autoclothes import register_handlers, register_schedulers
            
            # Register command handlers
            register_handlers(application)
            
            # Register scheduled jobs
            register_schedulers(application.job_queue)
            
            logger.info("AutoClothes module loaded successfully")
    else:
        logger.info("AutoClothes module disabled")
    
    # Future: News tracking module
    if config.is_feature_enabled("news_tracking"):
        logger.info("News tracking module not yet implemented")
    
    # Future: Price tracking module
    if config.is_feature_enabled("price_tracking"):
        logger.info("Price tracking module not yet implemented")


def main() -> None:
    """
    Start the bot with long polling.

    PythonAnywhere Setup:
    1. Set environment variables in PythonAnywhere dashboard:
       - ALLOWED_USER_ID: Your Telegram user ID
       - TELEGRAM_BOT_TOKEN: Your bot token
       - GROQ_API_KEY: Your Groq API key
       - LATITUDE: Your latitude
       - LONGITUDE: Your longitude

    2. Create "Always-on task" with command:
       python /home/yourusername/autoclothes/bot.py

    3. The bot will run indefinitely using long polling.
    """
    # Validate configuration
    errors = config.validate()
    if errors:
        for error in errors:
            logger.error(f"Configuration error: {error}")
        raise ValueError(f"Configuration errors: {', '.join(errors)}")

    bot_token = config.telegram_bot_token

    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not configured")
        raise ValueError("Bot token not configured")

    # Build application
    application = (
        Application.builder()
        .token(bot_token)
        .post_init(post_init)
        .build()
    )

    # Load feature modules
    load_feature_modules(application)

    # Add error handler
    application.add_error_handler(error_handler)

    # Start bot with long polling
    logger.info("Starting bot with long polling...")
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
