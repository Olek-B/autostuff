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
├── bot.py                  # Main Telegram bot (feature aggregator)
├── discord_bot.py          # Standalone Discord bot (independent)
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

# Run the Telegram bot
python bot.py

# Run the Discord bot (separate terminal)
python discord_bot.py
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

## PythonAnywhere Deployment

### Telegram Bot

1. **Upload Files** to your PythonAnywhere home directory:
   ```
   /home/yourusername/autoclothes/
   ├── bot.py
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

3. **Create Always-On Task**:
   - Go to **Tasks** tab → **Always-on tasks**
   - Click **Add a new always-on task**
   - Command: `/home/yourusername/.local/bin/python /home/yourusername/autoclothes/bot.py`

### Discord Bot (Separate)

1. **Create Separate Always-On Task**:
   - Command: `/home/yourusername/.local/bin/python /home/yourusername/autoclothes/discord_bot.py`

2. **Optional: Set up webhook trigger** via cron job or external service

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

# Discord Bot (Standalone)

A simple bot that sends morning messages to remind your friends what day it is.

## Setup

```bash
# Install additional dependencies
pip install discord.py flask

# Configure in .env
DISCORD_BOT_TOKEN=your_token
CHANNEL_ID=your_channel_id
SECRET_KEY=your_secret
```

## Run Locally

```bash
python discord_bot.py
```

## Deploy on PythonAnywhere

Create a separate **Always-On Task**:
```
/home/yourusername/.local/bin/python /home/yourusername/autoclothes/discord_bot.py
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /daily?key=SECRET_KEY` | Trigger daily message |
| `GET /health` | Health check |
