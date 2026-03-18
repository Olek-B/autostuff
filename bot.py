"""
Telegram Bot for AI-powered daily outfit suggestions.
Main entry point with command handlers and scheduled jobs.

PythonAnywhere Deployment:
    Run as "Always-on task" with command:
    python /home/yourusername/autoclothes/bot.py
    
    The bot uses long polling and runs indefinitely.
"""

import asyncio
import logging
import os
import re
from datetime import time as dt_time
from typing import Optional

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from telegram.error import NetworkError

from groq import APIError as GroqAPIError

import database as db
from services import (
    get_weather,
    get_ai_outfit,
    get_fallback_outfit,
    WeatherData
)

# =============================================================================
# CONFIGURATION
# =============================================================================

# Replace with your Telegram user ID (get from @userinfobot)
# Security: Only this user can interact with the bot
ALLOWED_USER_ID: int = int(os.environ.get("ALLOWED_USER_ID", "0"))

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# =============================================================================
# SECURITY MIDDLEWARE
# =============================================================================

def is_authorized(update: Update) -> bool:
    """
    Check if the user is authorized to use the bot.
    Logs unauthorized attempts and returns False.
    """
    user_id = update.effective_user.id if update.effective_user else 0
    
    if user_id != ALLOWED_USER_ID:
        logger.warning(
            f"Unauthorized access attempt from user_id={user_id}, "
            f"username={update.effective_user.username if update.effective_user else 'unknown'}"
        )
        return False
    
    return True


# =============================================================================
# COMMAND HANDLERS
# =============================================================================

async def cmd_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /start command - verify user and welcome."""
    if not is_authorized(update):
        return  # Silent drop for unauthorized users
    
    await update.message.reply_text(
        "👋 Welcome to AutoClothes Bot!\n\n"
        "I help you choose daily outfits based on weather and your wardrobe.\n\n"
        "Available commands:\n"
        "/outfit - Get today's outfit suggestion\n"
        "/add <name> <category> <min_temp> <max_temp> - Add clothing item\n"
        "/list - View your wardrobe\n"
        "/reset_laundry - Reset weekly laundry tracking\n"
        "/help - Show this help message\n\n"
        "Daily outfit suggestions are sent automatically at 7:00 AM."
    )


async def cmd_help(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /help command."""
    if not is_authorized(update):
        return
    
    await update.message.reply_text(
        "📖 *AutoClothes Bot Help*\n\n"
        "*Commands:*\n"
        "/start - Welcome message\n"
        "/outfit - Generate outfit for current weather\n"
        "/add - Add item: /add \"Blue Shirt\" top 15 30\n"
        "/list - Show all wardrobe items\n"
        "/reset_laundry - Clear wear history\n\n"
        "*Categories:*\n"
        "top, bottom, shoes, outer\n\n"
        "*Temperature:*\n"
        "Specify min and max temp in Celsius for when the item is suitable.",
        parse_mode="Markdown"
    )


async def cmd_outfit(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /outfit command - generate outfit based on current weather."""
    if not is_authorized(update):
        return
    
    await update.message.reply_text("🌤️ Checking weather and selecting outfit...")
    
    try:
        outfit = await generate_outfit(context)
        
        if outfit is None:
            await update.message.reply_text(
                "❌ No suitable clothes found for this weather.\n"
                "Consider adding more versatile items to your wardrobe."
            )
            return
        
        # Format outfit message
        message = _format_outfit_message(outfit)
        await update.message.reply_text(message, parse_mode="Markdown")
        
        # Mark items as worn
        worn_ids = [
            outfit.get("top_id"),
            outfit.get("bottom_id"),
            outfit.get("outer_id")
        ]
        worn_ids = [id_ for id_ in worn_ids if id_ is not None]
        if worn_ids:
            await db.mark_items_worn(worn_ids)
            
    except (GroqAPIError, NetworkError) as e:
        logger.error(f"Service error in /outfit: {e}")
        await update.message.reply_text(
            "⚠️ Service temporarily unavailable. Please try again later."
        )
    except Exception as e:
        logger.exception(f"Unexpected error in /outfit: {e}")
        await update.message.reply_text(
            "⚠️ An error occurred. Please try again later."
        )


async def cmd_add(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle /add command - add clothing item to wardrobe.
    Format: /add <name> <category> <min_temp> <max_temp>
    Example: /add "Blue Shirt" top 15 30
    """
    if not is_authorized(update):
        return
    
    args = context.args
    
    if len(args) < 4:
        await update.message.reply_text(
            "❌ Invalid format.\n\n"
            "Usage: /add <name> <category> <min_temp> <max_temp>\n"
            "Example: /add \"Blue Shirt\" top 15 30\n\n"
            "Categories: top, bottom, shoes, outer"
        )
        return
    
    # Parse arguments - handle quoted names
    full_text = update.message.text
    name_match = re.search(r'/add\s+"([^"]+)"', full_text)
    
    if name_match:
        item_name = name_match.group(1)
        remaining = full_text[name_match.end():].strip().split()
    else:
        # No quotes, first arg is name
        item_name = args[0].strip('"')
        remaining = args[1:]
    
    if len(remaining) < 3:
        await update.message.reply_text("❌ Missing category or temperature values.")
        return
    
    category = remaining[0].lower()
    
    # Validate category
    valid_categories = {"top", "bottom", "shoes", "outer"}
    if category not in valid_categories:
        await update.message.reply_text(
            f"❌ Invalid category '{category}'.\n"
            f"Valid categories: {', '.join(valid_categories)}"
        )
        return
    
    # Validate and sanitize temperature values
    try:
        min_temp = int(remaining[1])
        max_temp = int(remaining[2])
        
        # Temperature range validation
        if min_temp < -20 or max_temp > 50:
            raise ValueError("Temperature out of reasonable range")
        if min_temp >= max_temp:
            raise ValueError("min_temp must be less than max_temp")
            
    except ValueError as e:
        await update.message.reply_text(
            f"❌ Invalid temperature values: {e}\n"
            "Use integers between -20 and 50°C."
        )
        return
    
    try:
        item_id = await db.add_wardrobe_item(item_name, category, min_temp, max_temp)
        await update.message.reply_text(
            f"✅ Added '{item_name}' to wardrobe.\n"
            f"Category: {category}\n"
            f"Temperature range: {min_temp}°C - {max_temp}°C"
        )
    except Exception as e:
        logger.error(f"Database error adding item: {e}")
        await update.message.reply_text("❌ Failed to add item. Please try again.")


async def cmd_list(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /list command - show wardrobe inventory."""
    if not is_authorized(update):
        return
    
    try:
        items = await db.list_wardrobe_items()
        
        if not items:
            await update.message.reply_text(
                "📭 Your wardrobe is empty.\n"
                "Use /add to add clothing items."
            )
            return
        
        # Group by category
        by_category: dict[str, list[dict]] = {}
        for item in items:
            cat = item["category"]
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(item)
        
        message = "👔 *Your Wardrobe*\n\n"
        
        category_emojis = {
            "top": "👕",
            "bottom": "👖",
            "shoes": "👟",
            "outer": "🧥"
        }
        
        for category in ["top", "bottom", "shoes", "outer"]:
            if category in by_category:
                emoji = category_emojis.get(category, "")
                message += f"*{emoji} {category.title()}s*\n"
                
                for item in by_category[category]:
                    last_worn = item["last_worn_date"]
                    if last_worn:
                        try:
                            date_str = last_worn.split("T")[0]
                            worn_info = f"(last: {date_str})"
                        except:
                            worn_info = ""
                    else:
                        worn_info = "(new)"
                    
                    message += (
                        f"• {item['item_name']} "
                        f"[{item['min_temp']}°-{item['max_temp']}°C] "
                        f"{worn_info}\n"
                    )
                message += "\n"
        
        await update.message.reply_text(message, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Database error listing items: {e}")
        await update.message.reply_text("❌ Failed to retrieve wardrobe.")


async def cmd_reset_laundry(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /reset_laundry command - clear wear history."""
    if not is_authorized(update):
        return
    
    try:
        count = await db.reset_weekly_laundry()
        await update.message.reply_text(
            f"✅ Laundry reset complete.\n"
            f"{count} items marked as available."
        )
    except Exception as e:
        logger.error(f"Database error resetting laundry: {e}")
        await update.message.reply_text("❌ Failed to reset laundry.")


# =============================================================================
# OUTFIT GENERATION LOGIC
# =============================================================================

async def generate_outfit(
    context: ContextTypes.DEFAULT_TYPE
) -> Optional[dict]:
    """
    Core outfit generation logic.
    Fetches weather, filters wardrobe, queries AI, returns outfit.
    """
    # Get user's location from config
    config = await db.get_all_config()
    
    try:
        lat = float(config.get("LATITUDE", "51.5074"))  # Default: London
        lon = float(config.get("LONGITUDE", "-0.1278"))
    except ValueError:
        lat, lon = 51.5074, -0.1278
    
    # Fetch current weather
    weather = await get_weather(lat, lon)
    logger.info(f"Weather: {weather.temperature}°C, {weather.conditions}")
    
    # Get suitable items from wardrobe
    available_items = await db.get_items_for_weather(weather.temperature)
    logger.info(f"Available items: {len(available_items)}")
    
    if not available_items:
        return None
    
    # Get Groq API key
    groq_key = config.get("GROQ_API_KEY")
    if not groq_key:
        logger.error("Groq API key not configured")
        raise ValueError("Groq API key not configured")
    
    # Get AI outfit suggestion
    try:
        outfit = await get_ai_outfit(weather, available_items, groq_key)
    except (GroqAPIError, ValueError, Exception) as e:
        logger.warning(f"Groq API failed, using fallback: {e}")
        outfit = await get_fallback_outfit(weather, available_items)
    
    return outfit


def _format_outfit_message(outfit: dict) -> str:
    """Format outfit dict into readable Telegram message."""
    message = "🎯 *Today's Outfit*\n\n"
    
    if outfit.get("outer"):
        message += f"🧥 Outer: {outfit['outer']}\n"
    if outfit.get("top"):
        message += f"👕 Top: {outfit['top']}\n"
    if outfit.get("bottom"):
        message += f"👖 Bottom: {outfit['bottom']}\n"
    
    message += f"\n💡 {outfit.get('reasoning', 'Enjoy your day!')}"
    
    return message


# =============================================================================
# SCHEDULED JOBS
# =============================================================================

async def daily_outfit_job(
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Scheduled job: Send outfit suggestion at 7:00 AM daily.
    Checks if auto-suggestions are enabled before sending.
    """
    logger.info("Running daily outfit job (7:00 AM)")
    
    try:
        config = await db.get_all_config()
        
        # Check if auto-suggestions are disabled
        if config.get("AUTO_OUTFIT_DISABLED") == "true":
            logger.info("Auto-outfit disabled, skipping")
            return
        
        outfit = await generate_outfit(context)
        
        if outfit is None:
            logger.info("No suitable outfit found for daily suggestion")
            return
        
        message = "☀️ *Good Morning!*\n\n" + _format_outfit_message(outfit)
        
        # Send to authorized user
        await context.bot.send_message(
            chat_id=ALLOWED_USER_ID,
            text=message,
            parse_mode="Markdown"
        )
        
        # Mark items as worn
        worn_ids = [
            outfit.get("top_id"),
            outfit.get("bottom_id"),
            outfit.get("outer_id")
        ]
        worn_ids = [id_ for id_ in worn_ids if id_ is not None]
        if worn_ids:
            await db.mark_items_worn(worn_ids)
            
    except Exception as e:
        logger.exception(f"Error in daily outfit job: {e}")


async def weekly_laundry_job(
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Scheduled job: Reset laundry tracking every Sunday at 2:00 AM.
    Clears last_worn_date for all items.
    """
    logger.info("Running weekly laundry reset (Sunday 2:00 AM)")
    
    try:
        count = await db.reset_weekly_laundry()
        logger.info(f"Reset {count} items in weekly laundry job")
        
        # Optionally notify user
        config = await db.get_all_config()
        if config.get("LAUNDRY_NOTIFICATION") == "true":
            await context.bot.send_message(
                chat_id=ALLOWED_USER_ID,
                text=f"🧺 Weekly laundry reset complete!\n{count} items are now available."
            )
    except Exception as e:
        logger.exception(f"Error in weekly laundry job: {e}")


# =============================================================================
# ERROR HANDLER
# =============================================================================

async def error_handler(
    update: Optional[Update],
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Log errors caused by updates."""
    logger.error(f"Update {update} caused error: {context.error}")


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

async def post_init(application: Application) -> None:
    """Initialize database after application starts."""
    await db.init_database()
    logger.info("Database initialized")


def main() -> None:
    """
    Start the bot with long polling.
    
    PythonAnywhere Setup:
    1. Set environment variables in PythonAnywhere dashboard:
       - ALLOWED_USER_ID: Your Telegram user ID
       - TELEGRAM_BOT_TOKEN: Your bot token (or store in DB)
       - GROQ_API_KEY: Your Groq API key (or store in DB)
       - LATITUDE: Your latitude
       - LONGITUDE: Your longitude
    
    2. Create "Always-on task" with command:
       python /home/yourusername/autoclothes/bot.py
    
    3. The bot will run indefinitely using long polling.
    """
    # Get bot token from environment or database
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    
    if not bot_token:
        # Try loading from database (requires pre-existing DB)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            bot_token = loop.run_until_complete(db.get_config("TELEGRAM_BOT_TOKEN"))
        finally:
            loop.close()
    
    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment or database")
        raise ValueError("Bot token not configured")
    
    # Build application
    application = (
        Application.builder()
        .token(bot_token)
        .post_init(post_init)
        .build()
    )
    
    # Add command handlers (all with authorization check)
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("outfit", cmd_outfit))
    application.add_handler(CommandHandler("add", cmd_add))
    application.add_handler(CommandHandler("list", cmd_list))
    application.add_handler(CommandHandler("reset_laundry", cmd_reset_laundry))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Setup JobQueue for scheduled tasks
    job_queue = application.job_queue
    
    # Daily outfit suggestion at 7:00 AM
    job_queue.run_daily(
        daily_outfit_job,
        time=dt_time(7, 0, 0),  # 7:00 AM
        name="daily_outfit"
    )
    logger.info("Scheduled daily outfit job at 7:00 AM")
    
    # Weekly laundry reset on Sunday at 2:00 AM
    job_queue.run_daily(
        weekly_laundry_job,
        time=dt_time(2, 0, 0),  # 2:00 AM
        days=[6],  # Sunday (0=Monday, 6=Sunday)
        name="weekly_laundry"
    )
    logger.info("Scheduled weekly laundry job on Sunday at 2:00 AM")
    
    # Start bot with long polling
    logger.info("Starting bot with long polling...")
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
