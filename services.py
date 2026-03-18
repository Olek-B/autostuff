"""
External service integrations: Weather (Open-Meteo) and AI (Groq).
All functions are async and include proper error handling.
"""

import json
import asyncio
from typing import Optional, Any
from dataclasses import dataclass

import httpx
from groq import AsyncGroq, APIError as GroqAPIError

from database import get_items_for_weather, mark_items_worn


@dataclass
class WeatherData:
    """Current weather conditions."""
    temperature: float
    conditions: str
    humidity: Optional[int] = None
    wind_speed: Optional[float] = None


# Open-Meteo API endpoint (free, no authentication required)
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


async def get_weather(
    latitude: float,
    longitude: float,
    timeout: float = 10.0
) -> WeatherData:
    """
    Fetch current weather from Open-Meteo API.
    
    Args:
        latitude: User's latitude coordinate
        longitude: User's longitude coordinate
        timeout: Request timeout in seconds
    
    Returns:
        WeatherData with current temperature and conditions
    
    Raises:
        httpx.HTTPError: On network/API failures
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,weather_code,humidity,wind_speed_10m",
        "timezone": "auto"
    }
    
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(OPEN_METEO_URL, params=params)
        response.raise_for_status()
        data = response.json()
    
    current = data.get("current", {})
    
    # Map WMO weather codes to human-readable conditions
    weather_code = current.get("weather_code", 0)
    conditions = _decode_weather_code(weather_code)
    
    return WeatherData(
        temperature=current.get("temperature_2m", 20.0),
        conditions=conditions,
        humidity=current.get("humidity"),
        wind_speed=current.get("wind_speed_10m")
    )


def _decode_weather_code(code: int) -> str:
    """Decode WMO weather code to human-readable string."""
    codes = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Foggy",
        48: "Depositing rime fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",
        71: "Slight snow",
        73: "Moderate snow",
        75: "Heavy snow",
        77: "Snow grains",
        80: "Slight rain showers",
        81: "Moderate rain showers",
        82: "Violent rain showers",
        85: "Slight snow showers",
        86: "Heavy snow showers",
        95: "Thunderstorm",
        96: "Thunderstorm with slight hail",
        99: "Thunderstorm with heavy hail"
    }
    return codes.get(code, "Unknown conditions")


async def get_ai_outfit(
    weather: WeatherData,
    available_items: list[dict[str, Any]],
    groq_api_key: str,
    timeout: float = 30.0
) -> dict[str, Any]:
    """
    Use Groq AI to select outfit based on weather and available items.
    
    Args:
        weather: Current weather conditions
        available_items: List of suitable clothing items from DB
        groq_api_key: Groq API key for authentication
        timeout: Request timeout in seconds
    
    Returns:
        Dict with outfit selection: {'top', 'bottom', 'outer'?, 'reasoning'}
    
    Raises:
        GroqAPIError: On Groq API failures
        ValueError: If no items available
    """
    if not available_items:
        raise ValueError("No available items for outfit selection")
    
    # Group items by category for cleaner prompt
    items_by_category: dict[str, list[str]] = {}
    item_map: dict[str, dict[str, Any]] = {}
    
    for item in available_items:
        category = item["category"]
        if category not in items_by_category:
            items_by_category[category] = []
        items_by_category[category].append(item["item_name"])
        item_map[item["item_name"]] = item
    
    # Build prompt with weather context and available items
    prompt = _build_outfit_prompt(weather, items_by_category)
    
    client = AsyncGroq(api_key=groq_api_key)
    
    response = await client.chat.completions.create(
        model="llama-3.1-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a fashion assistant helping users choose daily outfits. "
                    "Return ONLY valid JSON with keys: 'top', 'bottom', 'outer' (optional), 'reasoning'. "
                    "Do NOT invent items - only use items from the provided list. "
                    "The 'outer' field should only be included if weather warrants it."
                )
            },
            {"role": "user", "content": prompt}
        ],
        temperature=0.3,
        max_tokens=500,
        response_format={"type": "json_object"}
    )
    
    content = response.choices[0].message.content
    if not content:
        raise ValueError("Empty response from Groq API")
    
    outfit = json.loads(content)
    
    # Validate and enrich outfit with item IDs for tracking
    return _validate_outfit(outfit, item_map)


def _build_outfit_prompt(weather: WeatherData, items: dict[str, list[str]]) -> str:
    """Build the prompt for Groq API with weather and items context."""
    temp = weather.temperature
    temp_f = (temp * 9/5) + 32
    
    prompt = f"""Current weather conditions:
- Temperature: {temp:.1f}°C ({temp_f:.1f}°F)
- Conditions: {weather.conditions}"""

    if weather.humidity:
        prompt += f"\n- Humidity: {weather.humidity}%"
    if weather.wind_speed:
        prompt += f"\n- Wind: {weather.wind_speed} km/h"
    
    prompt += "\n\nAvailable wardrobe items:"
    
    if "top" in items:
        prompt += f"\nTops: {', '.join(items['top'])}"
    if "bottom" in items:
        prompt += f"\nBottoms: {', '.join(items['bottom'])}"
    if "outer" in items:
        prompt += f"\nOuterwear: {', '.join(items['outer'])}"
    if "shoes" in items:
        prompt += f"\nShoes: {', '.join(items['shoes'])}"
    
    prompt += """

Select an appropriate outfit. Consider:
- Layering for cooler temperatures
- Breathable fabrics for warm weather
- Outerwear if windy or precipitation expected

Return JSON format: {"top": "...", "bottom": "...", "outer": "...", "reasoning": "..."}"""
    
    return prompt


def _validate_outfit(
    outfit: dict[str, Any],
    item_map: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """
    Validate AI outfit response and enrich with item IDs.
    Falls back to random selection if AI returns invalid items.
    """
    validated: dict[str, Any] = {"reasoning": outfit.get("reasoning", "AI-selected outfit")}
    
    for category in ["top", "bottom", "outer"]:
        selected = outfit.get(category)
        if selected and selected in item_map:
            validated[category] = selected
            validated[f"{category}_id"] = item_map[selected]["id"]
        else:
            # Fallback: pick first available item of category
            fallback_items = [
                item for item in item_map.values()
                if item["category"] == category
            ]
            if fallback_items:
                fallback = fallback_items[0]
                validated[category] = fallback["item_name"]
                validated[f"{category}_id"] = fallback["id"]
                validated["reasoning"] += f" (AI suggestion for {category} was invalid, using fallback)"
    
    return validated


async def get_fallback_outfit(
    weather: WeatherData,
    available_items: list[dict[str, Any]]
) -> dict[str, Any]:
    """
    Generate fallback outfit by randomly selecting from available items.
    Used when Groq API fails or returns invalid JSON.
    """
    import random
    
    outfit = {"reasoning": f"Auto-selected based on {weather.conditions} weather ({weather.temperature:.1f}°C)"}
    
    items_by_category: dict[str, list[dict[str, Any]]] = {}
    for item in available_items:
        cat = item["category"]
        if cat not in items_by_category:
            items_by_category[cat] = []
        items_by_category[cat].append(item)
    
    for category in ["top", "bottom", "outer"]:
        if category in items_by_category:
            selected = random.choice(items_by_category[category])
            outfit[category] = selected["item_name"]
            outfit[f"{category}_id"] = selected["id"]
    
    return outfit
