# AutoClothes

AI-powered daily outfit suggestions using Groq API, weather data, and your personal wardrobe inventory.

## Components

- **Telegram Bot** (`bot.py`): Full-featured bot with wardrobe management and AI outfit suggestions
- **Discord Bot** (`discord_bot.py`): Simple daily message sender via Flask webhook

## Features

- 🌤️ **Weather Integration**: Real-time weather via Open-Meteo API
- 🤖 **AI Styling**: Groq LLM suggests outfits based on weather and available clothes
- 📅 **Laundry Tracking**: Prevents outfit repetition within 7-day window
- ⏰ **Daily Suggestions**: Automatic outfit push at 7:00 AM
- 🔒 **Security**: OWASP-compliant with strict user authorization

## Prerequisites

1. **Telegram Bot Token**: Create via [@BotFather](https://t.me/BotFather)
2. **Groq API Key**: Get from [Groq Console](https://console.groq.com)
3. **PythonAnywhere Account**: Free tier supported

## Local Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Copy environment file and configure
cp .env.example .env
# Edit .env with your credentials

# Run the bot
python bot.py
```

## PythonAnywhere Deployment

### Step 1: Upload Files

Upload these files to your PythonAnywhere home directory:
```
/home/yourusername/autoclothes/
├── bot.py
├── database.py
├── services.py
├── requirements.txt
└── .env (with your credentials)
```

### Step 2: Install Dependencies

Open a **Bash console** on PythonAnywhere and run:
```bash
cd ~/autoclothes
pip install -r requirements.txt --user
```

### Step 3: Configure Environment Variables

In PythonAnywhere dashboard:

1. Go to **Web** tab (or **Always-on tasks** for free tier)
2. For **Always-on tasks**, environment variables are set via the script

Alternatively, create a wrapper script `run_bot.sh`:
```bash
#!/bin/bash
export ALLOWED_USER_ID=123456789
export TELEGRAM_BOT_TOKEN=your_token
export GROQ_API_KEY=your_key
export LATITUDE=51.5074
export LONGITUDE=-0.1278

cd /home/yourusername/autoclothes
python bot.py
```

### Step 4: Create Always-On Task

**Important**: PythonAnywhere free tier doesn't support webhooks. Use **long polling** via an Always-On task:

1. Go to **Tasks** tab in PythonAnywhere dashboard
2. Under **Always-on tasks**, click **Add a new always-on task**
3. Enter the command:
   ```
   /home/yourusername/.local/bin/python /home/yourusername/autoclothes/bot.py
   ```
4. Click **Create**

The bot will start immediately and run continuously.

### Step 5: Verify Bot is Running

Check the **Always-on tasks** log for:
```
Starting bot with long polling...
Scheduled daily outfit job at 7:00 AM
Scheduled weekly laundry job on Sunday at 2:00 AM
```

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

Categories: `top`, `bottom`, `shoes`, `outer`

## Scheduled Jobs

| Job | Schedule | Description |
|-----|----------|-------------|
| Daily Outfit | 7:00 AM every day | Pushes outfit suggestion |
| Laundry Reset | 2:00 AM every Sunday | Clears wear history |

## Security Features

- **User Authorization**: Only `ALLOWED_USER_ID` can interact with bot
- **SQL Injection Prevention**: Parameterized queries throughout
- **Input Validation**: Temperature ranges and categories validated
- **Error Handling**: Graceful failures without exposing stack traces
- **Secrets Management**: API keys via environment variables

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

### Database errors
- Database is stored at `~/autoclothes_wardrobe.db`
- Delete and restart to reinitialize if corrupted

## API Rate Limits

| Service | Limit |
|---------|-------|
| Open-Meteo | Free, no key required |
| Groq | Varies by plan (free tier available) |
| Telegram | 30 messages/second |

## License

MIT License

---

# Discord Bot Setup

Quick daily message sender using Discord + Flask webhook.

## Prerequisites

1. **Discord Bot Token**: Create at [Discord Developer Portal](https://discord.com/developers/applications)
2. **Channel ID**: Enable Developer Mode in Discord to copy channel IDs

## Setup

```bash
# Install dependencies (in addition to existing requirements.txt)
pip install discord.py flask

# Copy environment file and configure Discord section
cp .env.example .env
# Edit .env with your Discord credentials
```

## Running Locally

```bash
python discord_bot.py
```

Flask server starts on port 5000.

## PythonAnywhere Deployment

### Step 1: Configure Environment Variables

In PythonAnywhere dashboard, set these environment variables:
- `DISCORD_BOT_TOKEN` - Your Discord bot token
- `CHANNEL_ID` - Target channel ID
- `SECRET_KEY` - Random secret for authentication (e.g., `openssl rand -hex 16`)

### Step 2: Create Always-On Task

1. Go to **Tasks** tab
2. Click **Add a new always-on task**
3. Enter command:
   ```
   /home/yourusername/.local/bin/python /home/yourusername/autoclothes/discord_bot.py
   ```

### Step 3: Set Up Cron Job (Optional)

To trigger the daily message at a specific time, set up a cron job:

1. Go to **Tasks** tab → **Scheduled tasks**
2. Add a new cron job with:
   ```bash
   curl "http://your-username.pythonanywhere.com/daily?key=YOUR_SECRET_KEY"
   ```
3. Set schedule (e.g., 7:00 AM daily)

Or use external cron service (e.g., cron-job.org, GitHub Actions).

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /daily?key=SECRET_KEY` | Trigger daily message |
| `GET /health` | Health check |

## Example Usage

```bash
# Trigger daily message
curl "http://localhost:5000/daily?key=your_secret_key"

# Check health
curl "http://localhost:5000/health"
```

## Security

- **SECRET_KEY** prevents unauthorized webhook calls
- Use HTTPS in production (PythonAnywhere provides HTTPS)
- Keep your secret key private
