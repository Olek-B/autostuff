"""
AutoStuff Web App - Flask endpoints for scheduled tasks.
Deploy on PythonAnywhere free tier and trigger via cron-job.org

Endpoints:
    GET /daily-outfit?key=SECRET_KEY  - Send daily outfit suggestion
    GET /discord-day?key=SECRET_KEY   - Send "what day is it" message
    GET /reset-laundry?key=SECRET_KEY - Reset weekly laundry tracking
    GET /health                       - Health check

PythonAnywhere Setup:
    1. Upload files to /home/yourusername/autoclothes/
    2. Create web app pointing to this file
    3. Set environment variables in PythonAnywhere dashboard
    4. Configure cron-job.org to hit endpoints on schedule

cron-job.org Schedule:
    Daily outfit:    0 7 * * *    → https://yourusername.pythonanywhere.com/daily-outfit?key=xxx
    Discord day:     0 8 * * *    → https://yourusername.pythonanywhere.com/discord-day?key=xxx
    Weekly laundry:  0 2 * * 0    → https://yourusername.pythonanywhere.com/reset-laundry?key=xxx
"""

import os
import logging
from datetime import datetime, timedelta
from flask import Flask, request, jsonify

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

SECRET_KEY = os.environ.get("SECRET_KEY")
ALLOWED_USER_ID = int(os.environ.get("ALLOWED_USER_ID", "0"))
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "0"))
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
LATITUDE = float(os.environ.get("LATITUDE", "51.5074"))
LONGITUDE = float(os.environ.get("LONGITUDE", "-0.1278"))

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

async def send_telegram_message(text: str) -> bool:
    """Send message via Telegram bot API."""
    import httpx
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": ALLOWED_USER_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=data, timeout=10.0)
            response.raise_for_status()
            return True
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
            return "🎯 *Today's Outfit*\n\n❌ No suitable clothes for this weather.\n\n💡 Add more versatile items to your wardrobe!"
        
        # Get AI outfit
        try:
            outfit = await get_ai_outfit(weather, available_items, GROQ_API_KEY)
        except Exception:
            outfit = await get_fallback_outfit(weather, available_items)
        
        # Format message
        message = "☀️ *Good Morning!*\n\n🎯 *Today's Outfit*\n\n"
        
        if outfit.get("outer"):
            message += f"🧥 Outer: {outfit['outer']}\n"
        if outfit.get("top"):
            message += f"👕 Top: {outfit['top']}\n"
        if outfit.get("bottom"):
            message += f"👖 Bottom: {outfit['bottom']}\n"
        
        message += f"\n💡 {outfit.get('reasoning', 'Enjoy your day!')}"
        
        # Mark items as worn
        worn_ids = [outfit.get("top_id"), outfit.get("bottom_id"), outfit.get("outer_id")]
        worn_ids = [id_ for id_ in worn_ids if id_ is not None]
        if worn_ids:
            await mark_items_worn(worn_ids)
        
        return message
        
    except Exception as e:
        logger.exception(f"Error generating outfit: {e}")
        return "⚠️ Outfit service temporarily unavailable."


# =============================================================================
# DISCORD HELPERS
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


async def format_discord_message() -> str:
    """Format the complete daily Discord message."""
    today = datetime.now()
    day_of_week = today.strftime("%A")
    temp_f, descriptor, descriptor_comment = await get_weather_vegas()
    names, names_plural = await get_name_days()
    party_advice = get_party_advice()
    
    return f"""GOOOOOD MORNING, LAS VEGAS! 
This is your daily dose of "What Day Is It, Anyway?" – I've got the answers you're too lazy to look up yourself!

🌡️ **Today is {day_of_week}**, and on the **Insane Scale** we're clocking in at a {descriptor} {temp_f}°F! 
{descriptor_comment} 

🎉 **Name Day Alert!** 
{names} {names_plural} celebrating their Name Day today! If you know 'em, give 'em a high-five, a donut, or at least a weird look. 
Just {party_advice}

🚦 **Traffic Snapshot:** Probably still backed up on the 15. Shocking, right? 

Remember: Life's too short to remember weekdays—that's my job. Stay awesome, Vegas!"""


async def send_discord_day_message() -> bool:
    """Send 'what day is it' message via Discord."""
    import discord
    
    try:
        intents = discord.Intents.default()
        client = discord.Client(intents=intents)
        
        @client.event
        async def on_ready():
            channel = client.get_channel(CHANNEL_ID)
            if channel:
                message = await format_discord_message()
                await channel.send(message)
                logger.info(f"Sent Discord message to channel {CHANNEL_ID}")
            else:
                logger.error(f"Discord channel {CHANNEL_ID} not found")
            await client.close()
        
        await client.start(DISCORD_BOT_TOKEN)
        return True
        
    except Exception as e:
        logger.error(f"Discord error: {e}")
        return False


# =============================================================================
# ENDPOINTS
# =============================================================================

@app.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok", "service": "autostuff"}), 200


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
    Trigger 'what day is it' Discord message.
    Usage: GET /discord-day?key=SECRET_KEY
    """
    if not check_auth(request.args.get("key")):
        return jsonify({"error": "Unauthorized"}), 403
    
    if not DISCORD_BOT_TOKEN:
        return jsonify({"error": "Discord not configured"}), 503
    
    logger.info(f"Discord day message triggered by {request.remote_addr}")
    
    success = await send_discord_day_message()
    
    if success:
        return jsonify({"status": "sent", "type": "discord-day"}), 200
    else:
        return jsonify({"status": "failed", "error": "Discord API error"}), 500


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
