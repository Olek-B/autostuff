# AutoStuff

A modular automation bot for daily tasks, tracking, and notifications. Built with an extensible architecture that lets you enable/disable features as needed.

## Features

### 👔 AutoClothes (Enabled by default)

AI-powered daily outfit suggestions using weather data and your personal wardrobe inventory.

- 🌤️ **Weather Integration**: Real-time weather via Open-Meteo API
- 🤖 **AI Styling**: Groq LLM suggests outfits based on weather and available clothes
- 📅 **Laundry Tracking**: Prevents outfit repetition within 7-day window
- ⏰ **Daily Suggestions**: Automatic outfit push at 7:00 AM

### 🤖 Discord Bot (Standalone experiment)

A friendly experiment that sends morning messages to remind friends what day it is. Runs completely independently from the Telegram bot.

### 🔮 Coming Soon

- 📰 **News Tracking**: Daily news digests on topics you care about
- 💰 **Price Tracking**: Monitor product prices and get alerts on drops

## Architecture

```
autoclothes/
├── bot.py                  # Telegram bot (long polling, local dev)
├── web_app.py              # Flask web app (webhooks, PythonAnywhere free tier)
├── config.py               # Configuration with feature toggles
├── database.py             # Shared database layer
├── services.py             # Shared services (weather, AI)
├── modules/                # Feature modules
│   ├── __init__.py
│   └── autoclothes/        # AutoClothes feature module
│       ├── __init__.py
│       ├── handlers.py     # Telegram command handlers
│       └── scheduler.py    # Scheduled jobs (daily outfit, weekly laundry)
└── tests/
```

### Feature Dependencies

```
AutoClothes requires:
├── TELEGRAM_BOT_TOKEN (for bot interface)
└── GROQ_API_KEY (for AI outfit suggestions)

News Tracking (future) requires:
└── TELEGRAM_BOT_TOKEN or DISCORD_BOT_TOKEN

Price Tracking (future) requires:
└── TELEGRAM_BOT_TOKEN or DISCORD_BOT_TOKEN
```

## Quick Start

### Local Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env with your credentials

# Run the Telegram bot (long polling)
python bot.py

# Run the web app (for webhooks)
python web_app.py
```

### Environment Configuration

Edit `.env` with your settings:

```bash
# Required for AutoClothes
TELEGRAM_BOT_TOKEN=your_token_here
GROQ_API_KEY=your_key_here

# Feature toggles
AUTOCLOTHES_ENABLED=true
AUTO_OUTFIT_DISABLED=false
LAUNDRY_NOTIFICATION=false

# Future features
NEWS_TRACKING_ENABLED=false
PRICE_TRACKING_ENABLED=false
```

## PythonAnywhere Deployment (Free Tier)

PythonAnywhere free tier doesn't include always-on tasks, but you can use:
- **Free web app** + **cron-job.org** for scheduled tasks

### Option 1: Web App + cron-job.org (Free)

1. **Upload Files** to your PythonAnywhere home directory:
   ```
   /home/yourusername/autoclothes/
   ├── web_app.py           # Flask web app for webhooks
   ├── bot.py               # (optional, for local dev)
   ├── config.py
   ├── database.py
   ├── services.py
   ├── modules/
   ├── requirements.txt
   └── .env
   ```

2. **Install Dependencies**:
   ```bash
   cd ~/autoclothes
   pip install -r requirements.txt --user
   ```

3. **Configure Web App**:
   - Go to **Web** tab in PythonAnywhere
   - Click **Add a new web app**
   - Choose **Flask** → **Python 3.10** (or your version)
   - Set source code path: `/home/yourusername/autoclothes/web_app.py`
   - Edit WSGI configuration file:
     ```python
     import sys
     path = '/home/yourusername/autoclothes'
     if path not in sys.path:
         sys.path.insert(0, path)
     
     from web_app import app as application
     ```

4. **Set Environment Variables** (in Web tab → Virtualenv):
   ```bash
   SECRET_KEY=your_random_secret
   ALLOWED_USER_ID=123456789
   TELEGRAM_BOT_TOKEN=your_token
   GROQ_API_KEY=your_key
   DISCORD_BOT_TOKEN=your_discord_token
   CHANNEL_ID=your_channel_id
   LATITUDE=51.5074
   LONGITUDE=-0.1278
   ```

5. **Configure cron-job.org** (free external cron service):
   
   Sign up at [cron-job.org](https://cron-job.org) and add these URLs:
   
   | Task | URL | Schedule |
   |------|-----|----------|
   | Daily Outfit | `https://yourusername.pythonanywhere.com/daily-outfit?key=YOUR_SECRET` | `0 7 * * *` (7:00 AM) |
   | Discord Day | `https://yourusername.pythonanywhere.com/discord-day?key=YOUR_SECRET` | `0 8 * * *` (8:00 AM) |
   | Weekly Laundry | `https://yourusername.pythonanywhere.com/reset-laundry?key=YOUR_SECRET` | `0 2 * * 0` (Sunday 2:00 AM) |

6. **Test Endpoints**:
   ```bash
   curl "https://yourusername.pythonanywhere.com/health"
   curl "https://yourusername.pythonanywhere.com/daily-outfit?key=YOUR_SECRET"
   ```

### Option 2: Always-On Task (Paid Tier)

If you have a paid PythonAnywhere account:

1. **Telegram Bot** - Create Always-On Task:
   ```
   /home/yourusername/.local/bin/python /home/yourusername/autoclothes/bot.py
   ```

2. **Discord Bot** - Create Always-On Task:
   ```
   /home/yourusername/.local/bin/python /home/yourusername/autoclothes/discord_bot.py
   ```

### Option 3: Local + Webhook (Hybrid)

Run the web app on PythonAnywhere (free) and run bots locally:

1. Deploy `web_app.py` on PythonAnywhere
2. Run `bot.py` and `discord_bot.py` on your local machine or Raspberry Pi
3. Use PythonAnywhere web app only for scheduled tasks via cron-job.org

## Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message and bot info |
| `/outfit` | Generate outfit for current weather |
| `/add <name> <category> <min> <max>` | Add clothing item |
| `/list` | View wardrobe inventory |
| `/reset_laundry` | Clear wear history manually |
| `/help` | Show help message |

### Adding Items

```
/add "Blue Oxford Shirt" top 15 30
/add "Black Jeans" bottom 10 25
/add "Leather Jacket" outer 5 18
/add "White Sneakers" shoes 10 35
```

**Categories**: `top`, `bottom`, `shoes`, `outer`

## Scheduled Jobs

| Job | Schedule | Module |
|-----|----------|--------|
| Daily Outfit | 7:00 AM every day | AutoClothes |
| Laundry Reset | 2:00 AM every Sunday | AutoClothes |

## Adding New Features

The modular architecture makes it easy to add new features:

1. **Create a new module** in `modules/your_feature/`:
   ```
   modules/
   └── news_tracker/
       ├── __init__.py
       ├── handlers.py      # Command handlers
       └── scheduler.py     # Scheduled jobs (optional)
   ```

2. **Update `config.py`** with feature toggle:
   ```python
   news_tracking_enabled: bool = field(
       default_factory=lambda: os.environ.get("NEWS_TRACKING_ENABLED", "false").lower() == "true"
   )
   ```

3. **Register in `bot.py`**:
   ```python
   if config.is_feature_enabled("news_tracking"):
       from modules.news_tracker import register_handlers
       register_handlers(application)
   ```

4. **Update `.env.example`** with new feature toggle

5. **Add tests** in `tests/`

## Security Features

- **User Authorization**: Only `ALLOWED_USER_ID` can interact with bot
- **SQL Injection Prevention**: Parameterized queries throughout
- **Input Validation**: Temperature ranges and categories validated
- **Error Handling**: Graceful failures without exposing stack traces
- **Secrets Management**: API keys via environment variables only

## Database Schema

### wardrobe
```sql
CREATE TABLE wardrobe (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_name TEXT NOT NULL,
    category TEXT NOT NULL,
    min_temp INTEGER NOT NULL,
    max_temp INTEGER NOT NULL,
    last_worn_date TEXT
);
```

### config
```sql
CREATE TABLE config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

## Troubleshooting

### Bot not responding
1. Check Always-on task is running (green indicator)
2. Verify `ALLOWED_USER_ID` matches your Telegram ID
3. Check logs for errors

### "Service temporarily unavailable"
- Groq API may be rate-limited or down
- Check your API key is valid
- Network issues on PythonAnywhere

### No outfit suggestions
- Ensure wardrobe has items for current temperature
- Check `/list` to verify items exist
- Verify weather API is working (latitude/longitude correct)

### Module not loading
- Check feature is enabled in `.env` (`AUTOCLOTHES_ENABLED=true`)
- Verify all dependencies are configured
- Check logs for specific error messages

## API Rate Limits

| Service | Limit |
|---------|-------|
| Open-Meteo | Free, no key required |
| Groq | Varies by plan (free tier available) |
| Telegram | 30 messages/second |

## License

MIT License

---

# Discord "What Day Is It" Bot

A friendly experiment to remind your Las Vegas friends what day it is via Discord.

Sends a daily morning message with:
- 🌡️ Las Vegas weather with funny commentary
- 🎉 Name days (from imieniny.vercel.app)
- 🚦 Traffic jokes
- 🎊 Weekend party advice

## Deploy on PythonAnywhere

The Discord bot is built into the web app. Configure in `.env`:

```bash
DISCORD_BOT_TOKEN=your_token
CHANNEL_ID=your_channel_id
```

Then set up cron-job.org to hit:
```
https://yourusername.pythonanywhere.com/discord-day?key=SECRET_KEY
```
