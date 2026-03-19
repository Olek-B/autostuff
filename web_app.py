"""
AutoStuff Web App - Flask endpoints for scheduled tasks and Telegram webhook.
Deploy on PythonAnywhere free tier and trigger via cron-job.org

Endpoints:
    POST /webhook                 - Telegram webhook receiver
    GET  /set-webhook?key=SECRET  - Register webhook with Telegram (one-time)
    GET  /daily-outfit?key=SECRET - Send daily outfit suggestion
    GET  /discord-day?key=SECRET  - Send "what day is it" message
    GET  /reset-laundry?key=SECRET- Reset weekly laundry tracking
    GET  /health                  - Health check

PythonAnywhere Setup:
    1. Upload files to /home/yourusername/autoclothes/
    2. Create web app pointing to this file
    3. Set environment variables in PythonAnywhere dashboard
    4. Configure cron-job.org to hit endpoints on schedule
    5. Call /set-webhook?key=SECRET once to register webhook

cron-job.org Schedule:
    Daily outfit:    0 7 * * *    → https://yourusername.pythonanywhere.com/daily-outfit?key=xxx
    Discord day:     0 8 * * *    → https://yourusername.pythonanywhere.com/discord-day?key=xxx
    Weekly laundry:  0 2 * * 0    → https://yourusername.pythonanywhere.com/reset-laundry?key=xxx
"""

import os
import logging
import httpx
from datetime import datetime, timedelta
from flask import Flask, request, jsonify

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# =============================================================================
# DATABASE INITIALIZATION
# =============================================================================

# Initialize database on app startup
import asyncio
from database import init_database

try:
    asyncio.run(init_database())
    logger.info("Database initialized successfully")
except Exception as e:
    logger.error(f"Database initialization failed: {e}")
    raise

# =============================================================================
# CONFIGURATION
# =============================================================================

SECRET_KEY = os.environ.get("SECRET_KEY")
ALLOWED_USER_ID = int(os.environ.get("ALLOWED_USER_ID", "0"))
DAY_MESSAGE_USER_ID = int(os.environ.get("DAY_MESSAGE_USER_ID", ALLOWED_USER_ID))
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
LATITUDE = float(os.environ.get("LATITUDE", "51.5074"))
LONGITUDE = float(os.environ.get("LONGITUDE", "-0.1278"))

# Telegram webhook URL (PythonAnywhere)
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "https://Dailystuff.pythonanywhere.com")

if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable is required")


def check_auth(key: str) -> bool:
    """Check if request key matches secret key."""
    if not key:
        logger.warning(f"Unauthorized access attempt from {request.remote_addr}")
        return False
    return key == SECRET_KEY


# =============================================================================
# TELEGRAM HELPERS
# =============================================================================

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# Build Telegram application for webhook processing
def build_telegram_app() -> Application:
    """Build Telegram application with all handlers."""
    # Import handlers from modules
    from modules.autoclothes.handlers import (
        cmd_start, cmd_help, cmd_outfit, cmd_add, cmd_list, cmd_reset_laundry,
        is_authorized
    )
    
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Register command handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("outfit", cmd_outfit))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("reset_laundry", cmd_reset_laundry))
    
    return app

# Global Telegram app instance
telegram_app = None

def get_telegram_app() -> Application:
    """Get or create Telegram application instance."""
    global telegram_app
    if telegram_app is None:
        telegram_app = build_telegram_app()
    return telegram_app

async def send_telegram_message(text: str, chat_id: int = None, use_html: bool = True) -> bool:
    """Send message via Telegram bot API."""
    if chat_id is None:
        chat_id = ALLOWED_USER_ID

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": str(chat_id),
        "text": text
    }

    # Only use HTML parse mode if message contains HTML tags
    if use_html and ('<' in text and '>' in text):
        data["parse_mode"] = "HTML"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, data=data)
            response.raise_for_status()
            result = response.json()
            if not result.get("ok"):
                logger.error(f"Telegram API error: {result.get('description', 'Unknown error')}")
                return False
            return True
    except httpx.HTTPStatusError as e:
        logger.error(f"Telegram HTTP error: {e.response.status_code} - {e.response.text}")
        return False
    except Exception as e:
        logger.error(f"Telegram API error: {e}")
        return False


async def get_daily_outfit() -> str:
    """Generate daily outfit using services module."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    
    from services import get_weather, get_ai_outfit, get_fallback_outfit
    from database import get_items_for_weather, mark_items_worn
    
    try:
        # Get weather
        weather = await get_weather(LATITUDE, LONGITUDE)
        
        # Get available items
        available_items = await get_items_for_weather(weather.temperature)
        
        if not available_items:
            return "🎯 <b>Today's Outfit</b>\n\n❌ No suitable clothes for this weather.\n\n💡 Add more versatile items to your wardrobe!"

        # Get AI outfit
        try:
            outfit = await get_ai_outfit(weather, available_items, GROQ_API_KEY)
        except Exception:
            outfit = await get_fallback_outfit(weather, available_items)

        # Format message
        message = "☀️ <b>Good Morning!</b>\n\n🎯 <b>Today's Outfit</b>\n\n"

        if outfit.get("outer"):
            message += f"🧥 Outer: {outfit['outer']}\n"
        if outfit.get("top"):
            message += f"👕 Top: {outfit['top']}\n"
        if outfit.get("bottom"):
            message += f"👖 Bottom: {outfit['bottom']}\n"

        reasoning = outfit.get('reasoning', 'Enjoy your day!').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        message += f"\n💡 {reasoning}"
        
        # Mark items as worn
        worn_ids = [outfit.get("top_id"), outfit.get("bottom_id"), outfit.get("outer_id")]
        worn_ids = [id_ for id_ in worn_ids if id_ is not None]
        if worn_ids:
            await mark_items_worn(worn_ids)
        
        return message
        
    except Exception as e:
        logger.exception(f"Error generating outfit: {e}")
        return "Outfit service temporarily unavailable."


# =============================================================================
# TELEGRAM HELPERS - WHAT DAY IS IT
# =============================================================================

async def get_weather_vegas() -> tuple[int, str, str]:
    """Fetch Las Vegas weather."""
    lat = 36.1699
    lon = -115.1398

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m",
                    "timezone": "America/Los_Angeles"
                }
            )
            response.raise_for_status()
            data = response.json()

        temp_c = data.get("current", {}).get("temperature_2m", 70)
        temp_f = round((temp_c * 9/5) + 32)

        if temp_f >= 90:
            descriptor, comment = "boiling", "Better find a pool—or become one!"
        elif temp_f <= 50:
            descriptor, comment = "chilling", "Time to dig out that 'Vegas cold' jacket!"
        else:
            descriptor, comment = "sane", "Almost too normal. Almost."

        return temp_f, descriptor, comment
    except Exception as e:
        logger.error(f"Weather error: {e}")
        return 75, "sane", "Almost too normal. Almost."


async def get_name_days() -> tuple[str, str]:
    """Fetch name days from API."""
    today = datetime.now()
    date_str = f"{today.month:02d}{today.day:02d}{today.year % 100:02d}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"https://imieniny.vercel.app/{date_str}")
            response.raise_for_status()
            names = response.json()

        if not names:
            return "No one", "is"
        elif len(names) == 1:
            return names[0], "is"
        elif len(names) == 2:
            return f"{names[0]} and {names[1]}", "are"
        else:
            return ", ".join(names[:-1]) + f", and {names[-1]}", "are"
    except Exception as e:
        logger.error(f"Name day error: {e}")
        return "Everyone", "is"


def get_party_advice() -> str:
    """Determine party advice based on tomorrow."""
    tomorrow = datetime.now() + timedelta(days=1)
    if tomorrow.weekday() >= 5:
        return "hey, it's the weekend—GO OVERBOARD!"
    return "remember tomorrow's a workday, so maybe don't go overboard!"


async def format_day_message() -> str:
    """Format the complete daily 'What Day Is It' message for Telegram."""
    today = datetime.now()
    day_of_week = today.strftime("%A")
    temp_f, descriptor, descriptor_comment = await get_weather_vegas()
    names, names_plural = await get_name_days()
    party_advice = get_party_advice()

    # Escape special HTML characters in variable content
    names_escaped = names.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    descriptor_comment_escaped = descriptor_comment.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    party_advice_escaped = party_advice.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    return f"""🌟 <b>GOOD MORNING, LAS VEGAS!</b> 🌟

This is your daily dose of <i>"What Day Is It, Anyway?"</i> – I've got the answers you're too lazy to look up yourself!

🌡️ <b>Today is {day_of_week}</b>, and on the <b>Insane Scale</b> we're clocking in at a {descriptor} {temp_f}°F!
{descriptor_comment_escaped}

🎉 <b>Name Day Alert!</b>
{names_escaped} {names_plural} celebrating their Name Day today! If you know 'em, give 'em a high-five, a donut, or at least a weird look.
Just {party_advice_escaped}

🚦 <b>Traffic Snapshot:</b> Probably still backed up on the 15. Shocking, right?

Remember: Life's too short to remember weekdays—that's my job. Stay awesome, Vegas!"""


async def send_day_message() -> bool:
    """Send 'what day is it' message via Telegram."""
    message = await format_day_message()
    return await send_telegram_message(message, chat_id=DAY_MESSAGE_USER_ID)


# =============================================================================
# ENDPOINTS
# =============================================================================

@app.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok", "service": "autostuff"}), 200


@app.route("/webhook", methods=["POST"])
async def webhook():
    """
    Telegram webhook receiver.
    Telegram sends updates to this endpoint when users interact with the bot.
    """
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Telegram not configured")
        return jsonify({"error": "Telegram not configured"}), 503
    
    try:
        # Get the update from Telegram
        update_data = request.get_json()
        if not update_data:
            logger.warning("Empty update received")
            return jsonify({"status": "ok"}), 200
        
        # Convert to telegram Update object
        update = Update.de_json(update_data)
        
        # Process the update
        tg_app = get_telegram_app()
        await tg_app.process_update(update)
        
        logger.info(f"Processed update: {update.update_id}")
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        logger.exception(f"Error processing webhook: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/set-webhook")
async def set_webhook():
    """
    Register webhook with Telegram (one-time setup).
    Usage: GET /set-webhook?key=SECRET_KEY
    
    This tells Telegram to send updates to this webhook URL.
    """
    if not check_auth(request.args.get("key")):
        return jsonify({"error": "Unauthorized"}), 403
    
    if not TELEGRAM_BOT_TOKEN:
        return jsonify({"error": "Telegram not configured"}), 503

    # Build webhook URL
    webhook_url = f"{WEBHOOK_URL}/webhook"
    
    # Set webhook with Telegram
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook"
    data = {
        "url": webhook_url,
        "allowed_updates": ["message", "callback_query"]
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=data)
            response.raise_for_status()
            result = response.json()
        
        if result.get("ok"):
            logger.info(f"Webhook set to: {webhook_url}")
            return jsonify({
                "status": "ok",
                "webhook_url": webhook_url,
                "message": "Webhook registered successfully"
            }), 200
        else:
            logger.error(f"Telegram error: {result}")
            return jsonify({
                "status": "error",
                "error": result.get("description", "Unknown error")
            }), 400
            
    except Exception as e:
        logger.exception(f"Error setting webhook: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/delete-webhook")
async def delete_webhook():
    """
    Remove webhook from Telegram.
    Usage: GET /delete-webhook?key=SECRET_KEY
    
    Use this if you want to switch back to long polling.
    """
    if not check_auth(request.args.get("key")):
        return jsonify({"error": "Unauthorized"}), 403
    
    if not TELEGRAM_BOT_TOKEN:
        return jsonify({"error": "Telegram not configured"}), 503

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteWebhook"
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url)
            response.raise_for_status()
            result = response.json()
        
        if result.get("ok"):
            logger.info("Webhook deleted")
            return jsonify({
                "status": "ok",
                "message": "Webhook removed successfully"
            }), 200
        else:
            return jsonify({
                "status": "error",
                "error": result.get("description", "Unknown error")
            }), 400
            
    except Exception as e:
        logger.exception(f"Error deleting webhook: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/webhook-info")
async def webhook_info():
    """
    Get current webhook status from Telegram.
    Usage: GET /webhook-info?key=SECRET_KEY
    """
    if not check_auth(request.args.get("key")):
        return jsonify({"error": "Unauthorized"}), 403
    
    if not TELEGRAM_BOT_TOKEN:
        return jsonify({"error": "Telegram not configured"}), 503

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getWebhookInfo"
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            result = response.json()
        
        return jsonify(result.get("result", {})), 200
            
    except Exception as e:
        logger.exception(f"Error getting webhook info: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/daily-outfit")
async def daily_outfit():
    """
    Trigger daily outfit suggestion.
    Usage: GET /daily-outfit?key=SECRET_KEY
    """
    if not check_auth(request.args.get("key")):
        return jsonify({"error": "Unauthorized"}), 403
    
    if not TELEGRAM_BOT_TOKEN:
        return jsonify({"error": "Telegram not configured"}), 503
    
    logger.info(f"Daily outfit triggered by {request.remote_addr}")
    
    message = await get_daily_outfit()
    success = await send_telegram_message(message)
    
    if success:
        return jsonify({"status": "sent", "type": "daily-outfit"}), 200
    else:
        return jsonify({"status": "failed", "error": "Telegram API error"}), 500


@app.route("/discord-day")
async def discord_day():
    """
    Trigger 'what day is it' message via Telegram.
    Usage: GET /discord-day?key=SECRET_KEY
    """
    if not check_auth(request.args.get("key")):
        return jsonify({"error": "Unauthorized"}), 403

    if not TELEGRAM_BOT_TOKEN:
        return jsonify({"error": "Telegram not configured"}), 503

    logger.info(f"Day message triggered by {request.remote_addr}")

    success = await send_day_message()

    if success:
        return jsonify({"status": "sent", "type": "day-message"}), 200
    else:
        return jsonify({"status": "failed", "error": "Telegram API error"}), 500


@app.route("/reset-laundry")
async def reset_laundry():
    """
    Trigger weekly laundry reset.
    Usage: GET /reset-laundry?key=SECRET_KEY
    """
    if not check_auth(request.args.get("key")):
        return jsonify({"error": "Unauthorized"}), 403
    
    if not TELEGRAM_BOT_TOKEN:
        return jsonify({"error": "Telegram not configured"}), 503
    
    logger.info(f"Laundry reset triggered by {request.remote_addr}")
    
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    
    from database import reset_weekly_laundry
    
    try:
        count = await reset_weekly_laundry()
        
        # Optional notification
        message = f"🧺 *Weekly laundry reset complete!*\n\n{count} items are now available."
        await send_telegram_message(message)
        
        return jsonify({"status": "reset", "count": count}), 200
        
    except Exception as e:
        logger.exception(f"Laundry reset error: {e}")
        return jsonify({"status": "failed", "error": str(e)}), 500


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    logger.info("Starting AutoStuff web app...")
    app.run(host="0.0.0.0", port=5000, debug=False)
