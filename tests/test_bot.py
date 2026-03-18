"""
Tests for AutoClothes module handlers.
Covers user security, command parsing, and error handling.
"""

import asyncio
import pytest
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

# Set test environment before importing
os.environ["ALLOWED_USER_ID"] = "123456789"
os.environ["TELEGRAM_BOT_TOKEN"] = "test_token"
os.environ["GROQ_API_KEY"] = "test_key"
os.environ["AUTOCLOTHES_ENABLED"] = "true"

from config import config
from modules.autoclothes.handlers import (
    is_authorized,
    cmd_start,
    cmd_help,
    cmd_outfit,
    cmd_add,
    cmd_list,
    cmd_reset_laundry,
    _format_outfit_message,
    generate_outfit,
)


class TestAuthorization:
    """Test user authorization."""

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
async def test_cmd_outfit_success(authorized_update, mock_context):
    """Test /outfit command successful generation."""
    with patch("modules.autoclothes.handlers.generate_outfit") as mock_generate:
        mock_generate.return_value = {
            "top": "Blue Shirt",
            "bottom": "Jeans",
            "reasoning": "Nice weather"
        }

        with patch("modules.autoclothes.handlers.mark_items_worn") as mock_mark:
            mock_mark.return_value = None

            await cmd_outfit(authorized_update, mock_context)

            assert authorized_update.message.reply_text.call_count >= 1


@pytest.mark.asyncio
async def test_cmd_outfit_no_items(authorized_update, mock_context):
    """Test /outfit when no suitable items found."""
    with patch("modules.autoclothes.handlers.generate_outfit") as mock_generate:
        mock_generate.return_value = None

        await cmd_outfit(authorized_update, mock_context)

        call_args = authorized_update.message.reply_text.call_args[0][0]
        assert "No suitable clothes" in call_args


@pytest.mark.asyncio
async def test_cmd_add_valid(authorized_update, mock_context):
    """Test /add command with valid arguments."""
    authorized_update.message.text = '/add "Test Shirt" top 15 30'
    mock_context.args = ["Test Shirt", "top", "15", "30"]

    with patch("modules.autoclothes.handlers.add_wardrobe_item") as mock_add:
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
async def test_cmd_list_success(authorized_update, mock_context):
    """Test /list command shows wardrobe."""
    mock_items = [
        {"item_name": "Shirt", "category": "top", "min_temp": 15, "max_temp": 30, "last_worn_date": None},
        {"item_name": "Jeans", "category": "bottom", "min_temp": 10, "max_temp": 25, "last_worn_date": "2024-01-01"}
    ]

    with patch("modules.autoclothes.handlers.list_wardrobe_items") as mock_list:
        mock_list.return_value = mock_items

        await cmd_list(authorized_update, mock_context)

        authorized_update.message.reply_text.assert_called_once()
        call_args = authorized_update.message.reply_text.call_args[0][0]
        assert "Shirt" in call_args


@pytest.mark.asyncio
async def test_cmd_reset_laundry(authorized_update, mock_context):
    """Test /reset_laundry command."""
    with patch("modules.autoclothes.handlers.reset_weekly_laundry") as mock_reset:
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
