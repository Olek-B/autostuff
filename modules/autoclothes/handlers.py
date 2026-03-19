"""
AutoClothes Telegram command handlers.
Provides /outfit, /add, /list, /reset_laundry, /start, /help commands.
"""

import logging
import re
from typing import Optional

from telegram import Update
from telegram.ext import CommandHandler

from config import config, is_feature_enabled
from database import (
    add_wardrobe_item,
    list_wardrobe_items,
    get_items_for_weather,
    mark_items_worn,
    reset_weekly_laundry,
    get_all_config,
)
from services import get_weather, get_ai_outfit, get_fallback_outfit

logger = logging.getLogger(__name__)


def is_authorized(update: Update) -> bool:
    """Check if the user is authorized to use the bot."""
    user_id = update.effective_user.id if update.effective_user else 0
    if user_id != config.allowed_user_id:
        logger.warning(f"Unauthorized access attempt from user_id={user_id}")
        return False
    return True


async def cmd_start(update: Update, context) -> None:
    """Handle /start command."""
    if not is_authorized(update):
        return

    features = []
    if is_feature_enabled("autoclothes"):
        features.append("👔 AutoClothes - AI outfit suggestions")

    features_text = "\n".join(features) if features else "No features enabled"

    await update.message.reply_text(
        f"👋 Welcome to AutoStuff Bot!\n\n"
        f"Enabled features:\n{features_text}\n\n"
        f"Available commands:\n"
        f"/outfit - Get today's outfit suggestion\n"
        f"/add <name> <category> <min_temp> <max_temp> - Add clothing item\n"
        f"/list - View your wardrobe\n"
        f"/reset_laundry - Reset weekly laundry tracking\n"
        f"/help - Show help message\n\n"
        f"Daily outfit suggestions are sent automatically at 7:00 AM."
    )


async def cmd_help(update: Update, context) -> None:
    """Handle /help command."""
    if not is_authorized(update):
        return

    await update.message.reply_text(
        "📖 <b>AutoStuff Help</b>\n\n"
        "<b>AutoClothes Commands:</b>\n"
        "/start - Welcome message\n"
        "/outfit - Generate outfit for current weather\n"
        "/add - Add item: /add \"Blue Shirt\" top 15 30\n"
        "/list - Show all wardrobe items\n"
        "/reset_laundry - Clear wear history\n\n"
        "<b>Categories:</b>\n"
        "top, bottom, shoes, outer\n\n"
        "<b>Temperature:</b>\n"
        "Specify min and max temp in Celsius for when the item is suitable.",
        parse_mode="HTML"
    )


async def generate_outfit(context) -> Optional[dict]:
    """Core outfit generation logic."""
    lat = config.latitude
    lon = config.longitude

    weather = await get_weather(lat, lon)
    logger.info(f"Weather: {weather.temperature}°C, {weather.conditions}")

    available_items = await get_items_for_weather(weather.temperature)
    logger.info(f"Available items: {len(available_items)}")

    if not available_items:
        return None

    groq_key = config.groq_api_key
    if not groq_key:
        logger.error("Groq API key not configured")
        raise ValueError("Groq API key not configured")

    try:
        outfit = await get_ai_outfit(weather, available_items, groq_key)
    except Exception as e:
        logger.warning(f"Groq API failed, using fallback: {e}")
        outfit = await get_fallback_outfit(weather, available_items)

    return outfit


def _format_outfit_message(outfit: dict) -> str:
    """Format outfit dict into readable Telegram message."""
    message = "🎯 <b>Today's Outfit</b>\n\n"

    if outfit.get("outer"):
        message += f"🧥 Outer: {outfit['outer']}\n"
    if outfit.get("top"):
        message += f"👕 Top: {outfit['top']}\n"
    if outfit.get("bottom"):
        message += f"👖 Bottom: {outfit['bottom']}\n"

    reasoning = outfit.get('reasoning', 'Enjoy your day!').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    message += f"\n💡 {reasoning}"
    return message


async def cmd_outfit(update: Update, context) -> None:
    """Handle /outfit command."""
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

        message = _format_outfit_message(outfit)
        await update.message.reply_text(message, parse_mode="HTML")

        worn_ids = [outfit.get("top_id"), outfit.get("bottom_id"), outfit.get("outer_id")]
        worn_ids = [id_ for id_ in worn_ids if id_ is not None]
        if worn_ids:
            await mark_items_worn(worn_ids)

    except Exception as e:
        logger.exception(f"Error in /outfit: {e}")
        await update.message.reply_text("⚠️ Service temporarily unavailable. Please try again later.")


async def cmd_add(update: Update, context) -> None:
    """Handle /add command."""
    if not is_authorized(update):
        return

    args = context.args

    if len(args) < 3:
        await update.message.reply_text(
            "❌ Invalid format.\n\n"
            "Usage: /add <name> <category> <min_temp> <max_temp>\n"
            "   or: /add <name> <category> auto (AI estimates temperature)\n\n"
            "Example: /add \"Blue Shirt\" top 15 30\n"
            "Example: /add \"Wool Sweater\" top auto\n\n"
            "Categories: top, bottom, shoes, outer"
        )
        return

    full_text = update.message.text
    name_match = re.search(r'/add\s+"([^"]+)"', full_text)

    if name_match:
        item_name = name_match.group(1)
        remaining = full_text[name_match.end():].strip().split()
    else:
        item_name = args[0].strip('"')
        remaining = args[1:]

    if len(remaining) < 2:
        await update.message.reply_text("❌ Missing category or temperature values.")
        return

    category = remaining[0].lower()
    valid_categories = {"top", "bottom", "shoes", "outer"}

    if category not in valid_categories:
        await update.message.reply_text(
            f"❌ Invalid category '{category}'.\n"
            f"Valid categories: {', '.join(valid_categories)}"
        )
        return

    # Check if using AI temperature estimation
    temp_arg = remaining[1].lower()
    
    if temp_arg == "auto":
        # AI-based temperature estimation
        await update.message.reply_text(
            f"🤖 Analyzing \"{item_name}\" to estimate temperature range..."
        )
        
        try:
            from config import config
            from services import estimate_temperature_range
            
            groq_key = config.groq_api_key
            if not groq_key:
                raise ValueError("Groq API key not configured")
            
            min_temp, max_temp, reasoning = await estimate_temperature_range(
                item_name, category, groq_key
            )
            
            logger.info(f"AI temperature estimate for '{item_name}': {min_temp}-{max_temp}°C ({reasoning})")
            
        except Exception as e:
            logger.warning(f"AI temperature estimation failed: {e}")
            # Use default values
            from services import DEFAULT_TEMP_RANGES
            min_temp, max_temp = DEFAULT_TEMP_RANGES.get(category, (15, 25))
            reasoning = "Default range (AI unavailable)"
    else:
        # Manual temperature specification
        try:
            if len(remaining) < 3:
                raise ValueError("Missing max_temp")
            
            min_temp = int(remaining[1])
            max_temp = int(remaining[2])

            if min_temp < -20 or max_temp > 50:
                raise ValueError("Temperature out of reasonable range (-20 to 50°C)")
            if min_temp >= max_temp:
                raise ValueError("min_temp must be less than max_temp")
            
            reasoning = "Manual specification"

        except ValueError as e:
            await update.message.reply_text(
                f"❌ Invalid temperature values: {e}\n"
                "Use integers between -20 and 50°C, or use 'auto' for AI estimation."
            )
            return

    try:
        item_id = await add_wardrobe_item(item_name, category, min_temp, max_temp)
        
        # Show confirmation with temperature source
        confirmation = (
            f"✅ Added '{item_name}' to wardrobe.\n\n"
            f"Category: {category}\n"
            f"Temperature range: {min_temp}°C - {max_temp}°C\n"
        )
        
        if temp_arg == "auto":
            confirmation += f"\n💡 {reasoning}"
        
        await update.message.reply_text(confirmation)
        
    except Exception as e:
        logger.error(f"Database error adding item: {e}")
        await update.message.reply_text("❌ Failed to add item. Please try again.")


async def cmd_list(update: Update, context) -> None:
    """Handle /list command."""
    if not is_authorized(update):
        return

    try:
        items = await list_wardrobe_items()

        if not items:
            await update.message.reply_text(
                "📭 Your wardrobe is empty.\n"
                "Use /add to add clothing items."
            )
            return

        by_category = {}
        for item in items:
            cat = item["category"]
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(item)

        message = "👔 *Your Wardrobe*\n\n"

        category_emojis = {"top": "👕", "bottom": "👖", "shoes": "👟", "outer": "🧥"}

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

        await update.message.reply_text(message, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Database error listing items: {e}")
        await update.message.reply_text("❌ Failed to retrieve wardrobe.")


async def cmd_reset_laundry(update: Update, context) -> None:
    """Handle /reset_laundry command."""
    if not is_authorized(update):
        return

    try:
        count = await reset_weekly_laundry()
        await update.message.reply_text(
            f"✅ Laundry reset complete.\n"
            f"{count} items marked as available."
        )
    except Exception as e:
        logger.error(f"Database error resetting laundry: {e}")
        await update.message.reply_text("❌ Failed to reset laundry.")


def register_handlers(application) -> None:
    """Register all AutoClothes command handlers with the application."""
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("outfit", cmd_outfit))
    application.add_handler(CommandHandler("add", cmd_add))
    application.add_handler(CommandHandler("list", cmd_list))
    application.add_handler(CommandHandler("reset_laundry", cmd_reset_laundry))
    logger.info("AutoClothes handlers registered")
