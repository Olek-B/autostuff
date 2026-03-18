"""
Discord Bot with Flask webhook for daily messages.
Run as an always-on task or deploy separately.

Usage:
    python discord_bot.py

Environment Variables:
    DISCORD_BOT_TOKEN - Your Discord bot token
    CHANNEL_ID - Target channel ID for daily messages
    SECRET_KEY - Secret for authenticating /daily endpoint
    PORT - Flask port (default: 5000)
"""

import os
import threading
import logging

import discord
from flask import Flask, request

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

DISCORD_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])
SECRET_KEY = os.environ["SECRET_KEY"]
PORT = int(os.environ.get("PORT", 5000))

# =============================================================================
# FLASK APP
# =============================================================================

app = Flask(__name__)


def send_discord_message():
    """Run the bot, send the message, then disconnect."""
    class TempClient(discord.Client):
        async def on_ready(self):
            logger.info(f"Discord bot logged in as {self.user}")
            channel = self.get_channel(CHANNEL_ID)
            if channel:
                await channel.send("Good morning! Daily message from Flask.")
                logger.info(f"Message sent to channel {CHANNEL_ID}")
            else:
                logger.error(f"Channel {CHANNEL_ID} not found")
            await self.close()
            logger.info("Discord bot disconnected")

    intents = discord.Intents.default()
    client = TempClient(intents=intents)
    client.run(DISCORD_TOKEN)


@app.route("/daily")
def daily():
    """
    Trigger daily message via HTTP request.
    Usage: GET /daily?key=YOUR_SECRET_KEY
    """
    if request.args.get("key") != SECRET_KEY:
        logger.warning(f"Unauthorized access attempt from {request.remote_addr}")
        return "Unauthorized", 403

    logger.info(f"Daily message triggered by {request.remote_addr}")
    
    # Run the bot in a separate thread so Flask doesn't block
    threading.Thread(target=send_discord_message, daemon=True).start()
    
    return "Message sending initiated", 200


@app.route("/health")
def health():
    """Health check endpoint for monitoring."""
    return "OK", 200


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    logger.info(f"Starting Flask server on port {PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
