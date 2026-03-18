"""
Tests for services.py module.
Covers weather fetching, AI outfit selection, and fallback logic.
"""

import asyncio
import pytest
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from services import (
    get_weather,
    get_ai_outfit,
    get_fallback_outfit,
    _decode_weather_code,
    _build_outfit_prompt,
    _validate_outfit,
    WeatherData
)


class TestDecodeWeatherCode:
    """Test WMO weather code decoding."""
    
    def test_clear_sky(self):
        assert _decode_weather_code(0) == "Clear sky"
    
    def test_partly_cloudy(self):
        assert _decode_weather_code(2) == "Partly cloudy"
    
    def test_rain(self):
        assert _decode_weather_code(61) == "Slight rain"
        assert _decode_weather_code(65) == "Heavy rain"
    
    def test_snow(self):
        assert _decode_weather_code(71) == "Slight snow"
        assert _decode_weather_code(75) == "Heavy snow"
    
    def test_thunderstorm(self):
        assert _decode_weather_code(95) == "Thunderstorm"
    
    def test_unknown_code(self):
        assert _decode_weather_code(999) == "Unknown conditions"


class TestWeatherData:
    """Test WeatherData dataclass."""
    
    def test_weather_data_creation(self):
        weather = WeatherData(
            temperature=22.5,
            conditions="Clear sky"
        )
        assert weather.temperature == 22.5
        assert weather.conditions == "Clear sky"
        assert weather.humidity is None
        assert weather.wind_speed is None
    
    def test_weather_data_with_all_fields(self):
        weather = WeatherData(
            temperature=22.5,
            conditions="Partly cloudy",
            humidity=65,
            wind_speed=12.5
        )
        assert weather.humidity == 65
        assert weather.wind_speed == 12.5


@pytest.mark.asyncio
async def test_get_weather_success():
    """Test successful weather fetch from Open-Meteo."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "current": {
            "temperature_2m": 22.5,
            "weather_code": 0,
            "humidity": 65,
            "wind_speed_10m": 10.2
        }
    }
    
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client_class.return_value = mock_client
        
        weather = await get_weather(51.5074, -0.1278)
        
        assert weather.temperature == 22.5
        assert weather.conditions == "Clear sky"
        assert weather.humidity == 65
        assert weather.wind_speed == 10.2
        
        # Verify API call parameters
        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args
        assert call_args[1]["params"]["latitude"] == 51.5074
        assert call_args[1]["params"]["longitude"] == -0.1278


@pytest.mark.asyncio
async def test_get_weather_default_values():
    """Test weather fetch with missing optional fields."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "current": {
            "temperature_2m": 20.0,
            "weather_code": 3
        }
    }
    
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client_class.return_value = mock_client
        
        weather = await get_weather(51.5074, -0.1278)
        
        assert weather.temperature == 20.0
        assert weather.conditions == "Overcast"
        assert weather.humidity is None
        assert weather.wind_speed is None


@pytest.mark.asyncio
async def test_get_weather_http_error():
    """Test weather fetch handles HTTP errors."""
    import httpx
    
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.HTTPError("Connection failed")
        mock_client.__aenter__.return_value = mock_client
        mock_client_class.return_value = mock_client
        
        with pytest.raises(httpx.HTTPError):
            await get_weather(51.5074, -0.1278)


class TestBuildOutfitPrompt:
    """Test prompt building for Groq API."""
    
    def test_basic_prompt(self):
        weather = WeatherData(temperature=22.0, conditions="Clear sky")
        items = {
            "top": ["Blue Shirt", "White Tee"],
            "bottom": ["Jeans", "Shorts"]
        }
        
        prompt = _build_outfit_prompt(weather, items)
        
        assert "22.0°C" in prompt
        assert "Clear sky" in prompt
        assert "Blue Shirt" in prompt
        assert "Jeans" in prompt
        assert "Tops:" in prompt
        assert "Bottoms:" in prompt
    
    def test_prompt_with_all_categories(self):
        weather = WeatherData(temperature=15.0, conditions="Partly cloudy")
        items = {
            "top": ["Shirt"],
            "bottom": ["Jeans"],
            "outer": ["Jacket"],
            "shoes": ["Sneakers"]
        }
        
        prompt = _build_outfit_prompt(weather, items)
        
        assert "Outerwear:" in prompt
        assert "Shoes:" in prompt
        assert "Jacket" in prompt
        assert "Sneakers" in prompt
    
    def test_prompt_with_full_weather_data(self):
        weather = WeatherData(
            temperature=18.0,
            conditions="Light rain",
            humidity=80,
            wind_speed=15.0
        )
        items = {"top": ["Shirt"]}
        
        prompt = _build_outfit_prompt(weather, items)
        
        assert "Humidity: 80%" in prompt
        assert "Wind: 15.0 km/h" in prompt
    
    def test_prompt_fahrenheit_conversion(self):
        weather = WeatherData(temperature=20.0, conditions="Clear")
        items = {"top": ["Shirt"]}
        
        prompt = _build_outfit_prompt(weather, items)
        
        # 20°C = 68°F
        assert "68.0°F" in prompt


class TestValidateOutfit:
    """Test outfit validation and enrichment."""
    
    def test_valid_outfit(self):
        item_map = {
            "Blue Shirt": {"id": 1, "category": "top"},
            "Jeans": {"id": 2, "category": "bottom"}
        }
        outfit = {
            "top": "Blue Shirt",
            "bottom": "Jeans",
            "reasoning": "Nice day"
        }
        
        result = _validate_outfit(outfit, item_map)
        
        assert result["top"] == "Blue Shirt"
        assert result["top_id"] == 1
        assert result["bottom"] == "Jeans"
        assert result["bottom_id"] == 2
        assert result["reasoning"] == "Nice day"
    
    def test_outfit_with_outer(self):
        item_map = {
            "Shirt": {"id": 1, "category": "top"},
            "Jeans": {"id": 2, "category": "bottom"},
            "Jacket": {"id": 3, "category": "outer"}
        }
        outfit = {
            "top": "Shirt",
            "bottom": "Jeans",
            "outer": "Jacket",
            "reasoning": "Cool weather"
        }
        
        result = _validate_outfit(outfit, item_map)
        
        assert result["outer"] == "Jacket"
        assert result["outer_id"] == 3
    
    def test_invalid_item_fallback(self):
        item_map = {
            "Blue Shirt": {"id": 1, "item_name": "Blue Shirt", "category": "top"},
            "White Shirt": {"id": 2, "item_name": "White Shirt", "category": "top"},
            "Jeans": {"id": 3, "item_name": "Jeans", "category": "bottom"}
        }
        outfit = {
            "top": "NonExistent Shirt",  # Invalid
            "bottom": "Jeans",
            "reasoning": "Test"
        }

        result = _validate_outfit(outfit, item_map)

        # Should fallback to first available top
        assert result["top"] in ["Blue Shirt", "White Shirt"]
        assert "fallback" in result["reasoning"].lower()
    
    def test_missing_category(self):
        item_map = {
            "Shirt": {"id": 1, "category": "top"}
        }
        outfit = {
            "top": "Shirt",
            "reasoning": "No bottoms available"
        }
        
        result = _validate_outfit(outfit, item_map)
        
        assert result["top"] == "Shirt"
        assert "bottom" not in result


@pytest.mark.asyncio
async def test_get_ai_outfit_no_items():
    """Test AI outfit with no available items raises error."""
    weather = WeatherData(temperature=22.0, conditions="Clear")
    
    with pytest.raises(ValueError, match="No available items"):
        await get_ai_outfit(weather, [], "fake_api_key")


@pytest.mark.asyncio
async def test_get_ai_outfit_success():
    """Test successful AI outfit generation."""
    weather = WeatherData(temperature=22.0, conditions="Clear sky")
    items = [
        {"id": 1, "item_name": "Blue Shirt", "category": "top"},
        {"id": 2, "item_name": "Jeans", "category": "bottom"}
    ]

    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            message=MagicMock(
                content='{"top": "Blue Shirt", "bottom": "Jeans", "reasoning": "Great day"}'
            )
        )
    ]

    # Create proper async mock for the API call
    async def mock_create(*args, **kwargs):
        return mock_response

    with patch("services.AsyncGroq") as mock_groq_class:
        mock_client = MagicMock()
        mock_client.chat.completions.create = mock_create
        mock_groq_class.return_value = mock_client

        outfit = await get_ai_outfit(weather, items, "test_api_key")

        assert outfit["top"] == "Blue Shirt"
        assert outfit["bottom"] == "Jeans"
        assert outfit["reasoning"] == "Great day"


@pytest.mark.asyncio
async def test_get_ai_outfit_invalid_json_fallback():
    """Test AI outfit handles invalid JSON gracefully."""
    weather = WeatherData(temperature=22.0, conditions="Clear")
    items = [
        {"id": 1, "item_name": "Blue Shirt", "category": "top"},
        {"id": 2, "item_name": "Jeans", "category": "bottom"}
    ]
    
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content="Invalid JSON response"))
    ]
    
    with patch("groq.AsyncGroq") as mock_groq_class:
        mock_client = AsyncMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_groq_class.return_value = mock_client
        
        with pytest.raises(Exception):  # json.JSONDecodeError
            await get_ai_outfit(weather, items, "test_api_key")


@pytest.mark.asyncio
async def test_get_fallback_outfit():
    """Test fallback outfit generation."""
    weather = WeatherData(temperature=20.0, conditions="Cloudy")
    items = [
        {"id": 1, "item_name": "Blue Shirt", "category": "top"},
        {"id": 2, "item_name": "Jeans", "category": "bottom"},
        {"id": 3, "item_name": "Jacket", "category": "outer"}
    ]
    
    outfit = await get_fallback_outfit(weather, items)
    
    assert "top" in outfit or "bottom" in outfit
    assert "reasoning" in outfit
    assert "Cloudy" in outfit["reasoning"]
    assert "20.0" in outfit["reasoning"]


@pytest.mark.asyncio
async def test_get_fallback_outfit_empty():
    """Test fallback outfit with no items."""
    weather = WeatherData(temperature=20.0, conditions="Clear")
    
    outfit = await get_fallback_outfit(weather, [])
    
    assert outfit["reasoning"] is not None
    assert "top" not in outfit
    assert "bottom" not in outfit


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
