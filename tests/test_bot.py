"""
Tests for bot.py command handlers and authorization.
Covers user security, command parsing, and error handling.
"""

import asyncio
import pytest
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

# Set test environment before importing bot
os.environ["ALLOWED_USER_ID"] = "123456789"
os.environ["TELEGRAM_BOT_TOKEN"] = "test_token"

from bot import (
    is_authorized,
    cmd_start,
    cmd_help,
    cmd_outfit,
    cmd_add,
    cmd_list,
    cmd_reset_laundry,
    _format_outfit_message,
    daily_outfit_job,
    weekly_laundry_job,
    ALLOWED_USER_ID
)


class TestAuthorization:
    """Test user authorization middleware."""
    
    def test_authorized_user(self):
        """Test authorized user passes check."""
        mock_update = MagicMock()
        mock_update.effective_user.id = 123456789
        
        assert is_authorized(mock_update) is True
    
    def test_unauthorized_user(self):
        """Test unauthorized user is rejected."""
        mock_update = MagicMock()
        mock_update.effective_user.id = 999999999
        mock_update.effective_user.username = "hacker"
        
        assert is_authorized(mock_update) is False
    
    def test_no_user(self):
        """Test update with no user is rejected."""
        mock_update = MagicMock()
        mock_update.effective_user = None
        
        assert is_authorized(mock_update) is False


@pytest.fixture
def mock_context():
    """Create mock context for command handlers."""
    context = MagicMock()
    context.args = []
    return context


@pytest.fixture
def authorized_update():
    """Create authorized update for testing."""
    update = MagicMock()
    update.effective_user.id = 123456789
    update.effective_user.username = "testuser"
    update.message = AsyncMock()
    update.message.reply_text = AsyncMock()
    update.message.text = ""
    return update


@pytest.fixture
def unauthorized_update():
    """Create unauthorized update for testing."""
    update = MagicMock()
    update.effective_user.id = 999999999
    update.effective_user.username = "hacker"
    update.message = AsyncMock()
    update.message.reply_text = AsyncMock()
    return update


@pytest.mark.asyncio
async def test_cmd_start_authorized(authorized_update, mock_context):
    """Test /start command for authorized user."""
    await cmd_start(authorized_update, mock_context)
    
    authorized_update.message.reply_text.assert_called_once()
    call_args = authorized_update.message.reply_text.call_args[0][0]
    assert "Welcome" in call_args
    assert "/outfit" in call_args


@pytest.mark.asyncio
async def test_cmd_start_unauthorized(unauthorized_update, mock_context):
    """Test /start command for unauthorized user."""
    await cmd_start(unauthorized_update, mock_context)
    
    # Should silently drop (no reply)
    unauthorized_update.message.reply_text.assert_not_called()


@pytest.mark.asyncio
async def test_cmd_help(authorized_update, mock_context):
    """Test /help command."""
    await cmd_help(authorized_update, mock_context)
    
    authorized_update.message.reply_text.assert_called_once()
    call_args = authorized_update.message.reply_text.call_args[0][0]
    assert "Help" in call_args
    assert "/add" in call_args


@pytest.mark.asyncio
async def test_cmd_help_unauthorized(unauthorized_update, mock_context):
    """Test /help command for unauthorized user."""
    await cmd_help(unauthorized_update, mock_context)
    unauthorized_update.message.reply_text.assert_not_called()


@pytest.mark.asyncio
async def test_cmd_outfit_success(authorized_update, mock_context):
    """Test /outfit command successful generation."""
    with patch("bot.generate_outfit") as mock_generate:
        mock_generate.return_value = {
            "top": "Blue Shirt",
            "bottom": "Jeans",
            "reasoning": "Nice weather"
        }
        
        await cmd_outfit(authorized_update, mock_context)
        
        # Should reply with outfit
        assert authorized_update.message.reply_text.call_count >= 1


@pytest.mark.asyncio
async def test_cmd_outfit_no_items(authorized_update, mock_context):
    """Test /outfit when no suitable items found."""
    with patch("bot.generate_outfit") as mock_generate:
        mock_generate.return_value = None
        
        await cmd_outfit(authorized_update, mock_context)
        
        call_args = authorized_update.message.reply_text.call_args[0][0]
        assert "No suitable clothes" in call_args


@pytest.mark.asyncio
async def test_cmd_outfit_service_error(authorized_update, mock_context):
    """Test /outfit handles service errors gracefully."""
    from groq import APIError as GroqAPIError
    
    with patch("bot.generate_outfit") as mock_generate:
        # Create Groq API error with correct signature
        error = GroqAPIError(
            message="API Error",
            request=MagicMock(),
            body=None
        )
        mock_generate.side_effect = error
        
        await cmd_outfit(authorized_update, mock_context)
        
        # Should show user-friendly error, not stack trace
        call_args = authorized_update.message.reply_text.call_args[0][0]
        assert "temporarily unavailable" in call_args.lower()


@pytest.mark.asyncio
async def test_cmd_add_valid(authorized_update, mock_context):
    """Test /add command with valid arguments."""
    authorized_update.message.text = '/add "Test Shirt" top 15 30'
    mock_context.args = ["Test Shirt", "top", "15", "30"]
    
    with patch("bot.db.add_wardrobe_item") as mock_add:
        mock_add.return_value = 1
        
        await cmd_add(authorized_update, mock_context)
        
        mock_add.assert_called_once_with("Test Shirt", "top", 15, 30)
        authorized_update.message.reply_text.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_add_invalid_category(authorized_update, mock_context):
    """Test /add command with invalid category."""
    authorized_update.message.text = '/add "Shirt" invalid 15 30'
    mock_context.args = ["Shirt", "invalid", "15", "30"]
    
    await cmd_add(authorized_update, mock_context)
    
    call_args = authorized_update.message.reply_text.call_args[0][0]
    assert "Invalid category" in call_args


@pytest.mark.asyncio
async def test_cmd_add_invalid_temperature(authorized_update, mock_context):
    """Test /add command with invalid temperature."""
    authorized_update.message.text = '/add "Shirt" top abc 30'
    mock_context.args = ["Shirt", "top", "abc", "30"]
    
    await cmd_add(authorized_update, mock_context)
    
    call_args = authorized_update.message.reply_text.call_args[0][0]
    assert "Invalid temperature" in call_args


@pytest.mark.asyncio
async def test_cmd_add_missing_args(authorized_update, mock_context):
    """Test /add command with missing arguments."""
    authorized_update.message.text = '/add "Shirt"'
    mock_context.args = ["Shirt"]
    
    await cmd_add(authorized_update, mock_context)
    
    call_args = authorized_update.message.reply_text.call_args[0][0]
    assert "Invalid format" in call_args


@pytest.mark.asyncio
async def test_cmd_add_temperature_range_validation(authorized_update, mock_context):
    """Test /add command validates temperature range."""
    # min_temp >= max_temp
    authorized_update.message.text = '/add "Shirt" top 30 15'
    mock_context.args = ["Shirt", "top", "30", "15"]
    
    await cmd_add(authorized_update, mock_context)
    
    call_args = authorized_update.message.reply_text.call_args[0][0]
    assert "min_temp must be less than max_temp" in call_args


@pytest.mark.asyncio
async def test_cmd_add_unauthorized(unauthorized_update, mock_context):
    """Test /add command for unauthorized user."""
    await cmd_add(unauthorized_update, mock_context)
    unauthorized_update.message.reply_text.assert_not_called()


@pytest.mark.asyncio
async def test_cmd_list_success(authorized_update, mock_context):
    """Test /list command shows wardrobe."""
    mock_items = [
        {"item_name": "Shirt", "category": "top", "min_temp": 15, "max_temp": 30, "last_worn_date": None},
        {"item_name": "Jeans", "category": "bottom", "min_temp": 10, "max_temp": 25, "last_worn_date": "2024-01-01"}
    ]
    
    with patch("bot.db.list_wardrobe_items") as mock_list:
        mock_list.return_value = mock_items
        
        await cmd_list(authorized_update, mock_context)
        
        authorized_update.message.reply_text.assert_called_once()
        call_args = authorized_update.message.reply_text.call_args[0][0]
        assert "Shirt" in call_args
        assert "Jeans" in call_args


@pytest.mark.asyncio
async def test_cmd_list_empty(authorized_update, mock_context):
    """Test /list command with empty wardrobe."""
    with patch("bot.db.list_wardrobe_items") as mock_list:
        mock_list.return_value = []
        
        await cmd_list(authorized_update, mock_context)
        
        call_args = authorized_update.message.reply_text.call_args[0][0]
        assert "empty" in call_args.lower()


@pytest.mark.asyncio
async def test_cmd_reset_laundry(authorized_update, mock_context):
    """Test /reset_laundry command."""
    with patch("bot.db.reset_weekly_laundry") as mock_reset:
        mock_reset.return_value = 5
        
        await cmd_reset_laundry(authorized_update, mock_context)
        
        mock_reset.assert_called_once()
        call_args = authorized_update.message.reply_text.call_args[0][0]
        assert "reset complete" in call_args.lower()


class TestFormatOutfitMessage:
    """Test outfit message formatting."""
    
    def test_basic_outfit(self):
        outfit = {
            "top": "Blue Shirt",
            "bottom": "Jeans",
            "reasoning": "Great day"
        }
        
        message = _format_outfit_message(outfit)
        
        assert "Blue Shirt" in message
        assert "Jeans" in message
        assert "👕" in message
        assert "👖" in message
        assert "Great day" in message
    
    def test_outfit_with_outer(self):
        outfit = {
            "top": "Shirt",
            "bottom": "Jeans",
            "outer": "Jacket",
            "reasoning": "Cool weather"
        }
        
        message = _format_outfit_message(outfit)
        
        assert "Jacket" in message
        assert "🧥" in message
    
    def test_outfit_missing_reasoning(self):
        outfit = {
            "top": "Shirt",
            "bottom": "Jeans"
        }
        
        message = _format_outfit_message(outfit)
        
        assert "Enjoy your day" in message


@pytest.mark.asyncio
async def test_daily_outfit_job():
    """Test daily outfit scheduled job."""
    mock_context = MagicMock()
    mock_context.bot.send_message = AsyncMock()

    with patch("bot.db.get_all_config") as mock_config:
        mock_config.return_value = {}
        
        with patch("bot.generate_outfit") as mock_generate:
            mock_generate.return_value = {
                "top": "Shirt",
                "bottom": "Jeans",
                "reasoning": "Morning outfit"
            }

            await daily_outfit_job(mock_context)

            mock_context.bot.send_message.assert_called_once()
            call_args = mock_context.bot.send_message.call_args
            assert call_args[1]["chat_id"] == ALLOWED_USER_ID
            assert "Good Morning" in call_args[1]["text"]


@pytest.mark.asyncio
async def test_daily_outfit_job_disabled():
    """Test daily job respects disable setting."""
    mock_context = MagicMock()
    mock_context.bot.send_message = AsyncMock()
    
    with patch("bot.db.get_all_config") as mock_config:
        mock_config.return_value = {"AUTO_OUTFIT_DISABLED": "true"}
        
        await daily_outfit_job(mock_context)
        
        mock_context.bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_daily_outfit_job_no_items():
    """Test daily job handles no suitable items."""
    mock_context = MagicMock()
    mock_context.bot.send_message = AsyncMock()
    
    with patch("bot.generate_outfit") as mock_generate:
        mock_generate.return_value = None
        
        await daily_outfit_job(mock_context)
        
        mock_context.bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_weekly_laundry_job():
    """Test weekly laundry reset job."""
    mock_context = MagicMock()
    mock_context.bot.send_message = AsyncMock()
    
    with patch("bot.db.reset_weekly_laundry") as mock_reset:
        mock_reset.return_value = 10
        
        await weekly_laundry_job(mock_context)
        
        mock_reset.assert_called_once()


@pytest.mark.asyncio
async def test_weekly_laundry_job_with_notification():
    """Test weekly job sends notification when enabled."""
    mock_context = MagicMock()
    mock_context.bot.send_message = AsyncMock()
    
    with patch("bot.db.get_all_config") as mock_config:
        mock_config.return_value = {"LAUNDRY_NOTIFICATION": "true"}
        
        with patch("bot.db.reset_weekly_laundry") as mock_reset:
            mock_reset.return_value = 5
            
            await weekly_laundry_job(mock_context)
            
            mock_context.bot.send_message.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
