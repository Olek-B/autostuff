"""
Async SQLite database module for wardrobe management.
Stores clothing items, configuration, and tracks usage for laundry logic.
"""

import aiosqlite
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Any
from contextlib import asynccontextmanager

# Database location in user's home directory for PythonAnywhere persistence
DB_PATH = Path.home() / "autoclothes_wardrobe.db"


@asynccontextmanager
async def get_connection():
    """Get async database connection with row factory (context manager)."""
    conn = await aiosqlite.connect(DB_PATH)
    conn.row_factory = aiosqlite.Row
    try:
        yield conn
    finally:
        await conn.close()


async def init_database() -> None:
    """Initialize database schema with wardrobe and config tables."""
    async with get_connection() as conn:
        # Wardrobe table: stores clothing items with temperature ranges
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS wardrobe (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name TEXT NOT NULL,
                category TEXT NOT NULL CHECK(category IN ('top', 'bottom', 'shoes', 'outer')),
                min_temp INTEGER NOT NULL,
                max_temp INTEGER NOT NULL,
                last_worn_date TEXT
            )
        """)
        
        # Config table: stores API keys and user settings
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        
        await conn.commit()


async def set_config(key: str, value: str) -> None:
    """Store configuration value (API keys, tokens, settings)."""
    async with get_connection() as conn:
        await conn.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            (key, value)
        )
        await conn.commit()


async def get_config(key: str) -> Optional[str]:
    """Retrieve configuration value by key."""
    async with get_connection() as conn:
        cursor = await conn.execute(
            "SELECT value FROM config WHERE key = ?",
            (key,)
        )
        row = await cursor.fetchone()
        return row["value"] if row else None


async def get_all_config() -> dict[str, str]:
    """Retrieve all configuration values as dictionary."""
    async with get_connection() as conn:
        cursor = await conn.execute("SELECT key, value FROM config")
        return {row["key"]: row["value"] async for row in cursor}


async def add_wardrobe_item(
    item_name: str,
    category: str,
    min_temp: int,
    max_temp: int
) -> int:
    """
    Add new clothing item to wardrobe.
    Returns the ID of the inserted item.
    """
    async with get_connection() as conn:
        cursor = await conn.execute(
            """INSERT INTO wardrobe (item_name, category, min_temp, max_temp, last_worn_date)
               VALUES (?, ?, ?, ?, NULL)""",
            (item_name, category, min_temp, max_temp)
        )
        await conn.commit()
        return cursor.lastrowid


async def list_wardrobe_items() -> list[dict[str, Any]]:
    """List all wardrobe items with their details."""
    async with get_connection() as conn:
        cursor = await conn.execute(
            "SELECT id, item_name, category, min_temp, max_temp, last_worn_date FROM wardrobe ORDER BY category, item_name"
        )
        return [dict(row) async for row in cursor]


async def get_items_for_weather(
    current_temp: float,
    days_since_worn: int = 7
) -> list[dict[str, Any]]:
    """
    Filter wardrobe items suitable for current weather.
    Returns items where:
    - Current temperature is within item's min/max range
    - Item hasn't been worn in the last N days (or never worn)
    """
    cutoff_date = (datetime.now() - timedelta(days=days_since_worn)).isoformat()
    
    async with get_connection() as conn:
        cursor = await conn.execute(
            """SELECT id, item_name, category, min_temp, max_temp, last_worn_date 
               FROM wardrobe 
               WHERE ? BETWEEN min_temp AND max_temp
               AND (last_worn_date IS NULL OR last_worn_date < ?)
               ORDER BY category""",
            (current_temp, cutoff_date)
        )
        return [dict(row) async for row in cursor]


async def mark_item_worn(item_id: int) -> None:
    """Mark an item as worn today (update last_worn_date)."""
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE wardrobe SET last_worn_date = ? WHERE id = ?",
            (datetime.now().isoformat(), item_id)
        )
        await conn.commit()


async def mark_items_worn(item_ids: list[int]) -> None:
    """Mark multiple items as worn today."""
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE wardrobe SET last_worn_date = ? WHERE id IN ({})".format(
                ",".join("?" * len(item_ids))
            ),
            [datetime.now().isoformat()] + item_ids
        )
        await conn.commit()


async def reset_weekly_laundry() -> int:
    """
    Reset laundry tracking by clearing last_worn_date for all items.
    Returns the number of items reset.
    """
    async with get_connection() as conn:
        cursor = await conn.execute(
            "UPDATE wardrobe SET last_worn_date = NULL"
        )
        await conn.commit()
        return cursor.rowcount


async def delete_wardrobe_item(item_id: int) -> bool:
    """Delete an item from wardrobe by ID. Returns True if deleted."""
    async with get_connection() as conn:
        cursor = await conn.execute(
            "DELETE FROM wardrobe WHERE id = ?",
            (item_id,)
        )
        await conn.commit()
        return cursor.rowcount > 0


async def get_wardrobe_stats() -> dict[str, int]:
    """Get wardrobe statistics by category."""
    async with get_connection() as conn:
        cursor = await conn.execute(
            """SELECT category, COUNT(*) as count 
               FROM wardrobe 
               GROUP BY category"""
        )
        return {row["category"]: row["count"] async for row in cursor}
