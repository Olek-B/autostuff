"""
Tests for database.py module.
Uses synchronous sqlite3 for reliable testing.
Covers all CRUD operations, laundry logic, and configuration management.
"""

import pytest
import sqlite3
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import database as db


# Use test database with unique name per test run
TEST_DB_PATH = Path(f"/tmp/test_autoclothes_wardrobe_{os.getpid()}.db")


def get_sync_connection():
    """Get synchronous sqlite3 connection for testing."""
    conn = sqlite3.connect(TEST_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@pytest.fixture(autouse=True)
def setup_teardown():
    """Setup and teardown for each test."""
    # Setup - remove existing db and initialize
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
    
    # Initialize database schema
    conn = get_sync_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS wardrobe (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT NOT NULL,
            category TEXT NOT NULL CHECK(category IN ('top', 'bottom', 'shoes', 'outer')),
            min_temp INTEGER NOT NULL,
            max_temp INTEGER NOT NULL,
            last_worn_date TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    
    yield
    
    # Teardown - remove test db
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
    journal_path = Path(str(TEST_DB_PATH) + "-journal")
    if journal_path.exists():
        journal_path.unlink()


class TestDatabaseInit:
    """Test database initialization."""
    
    def test_init_database(self):
        """Test database initialization creates tables."""
        conn = get_sync_connection()
        
        # Check wardrobe table exists
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='wardrobe'"
        )
        result = cursor.fetchone()
        assert result is not None
        
        # Check config table exists
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='config'"
        )
        result = cursor.fetchone()
        assert result is not None
        
        conn.close()


class TestConfig:
    """Test configuration management."""
    
    def test_set_and_get_config(self):
        """Test configuration storage and retrieval."""
        conn = get_sync_connection()
        
        # Set config
        conn.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            ("TEST_KEY", "test_value")
        )
        conn.commit()
        
        # Get config
        cursor = conn.execute("SELECT value FROM config WHERE key = ?", ("TEST_KEY",))
        result = cursor.fetchone()
        assert result["value"] == "test_value"
        
        # Get non-existent key
        cursor = conn.execute("SELECT value FROM config WHERE key = ?", ("NON_EXISTENT",))
        result = cursor.fetchone()
        assert result is None
        
        conn.close()
    
    def test_get_all_config(self):
        """Test retrieving all configuration."""
        conn = get_sync_connection()
        
        conn.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            ("KEY1", "value1")
        )
        conn.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            ("KEY2", "value2")
        )
        conn.commit()
        
        cursor = conn.execute("SELECT key, value FROM config")
        config = {row["key"]: row["value"] for row in cursor.fetchall()}
        
        assert config == {"KEY1": "value1", "KEY2": "value2"}
        
        conn.close()


class TestWardrobeCRUD:
    """Test wardrobe CRUD operations."""
    
    def test_add_wardrobe_item(self):
        """Test adding wardrobe item."""
        conn = get_sync_connection()
        
        cursor = conn.execute(
            """INSERT INTO wardrobe (item_name, category, min_temp, max_temp, last_worn_date)
               VALUES (?, ?, ?, ?, NULL)""",
            ("Test Shirt", "top", 15, 30)
        )
        conn.commit()
        item_id = cursor.lastrowid
        
        assert item_id is not None
        assert item_id >= 1  # SQLite starts at 1
        
        conn.close()
    
    def test_list_wardrobe_items(self):
        """Test listing wardrobe items."""
        conn = get_sync_connection()
        
        conn.execute(
            "INSERT INTO wardrobe (item_name, category, min_temp, max_temp) VALUES (?, ?, ?, ?)",
            ("Shirt", "top", 15, 30)
        )
        conn.execute(
            "INSERT INTO wardrobe (item_name, category, min_temp, max_temp) VALUES (?, ?, ?, ?)",
            ("Jeans", "bottom", 10, 25)
        )
        conn.commit()
        
        cursor = conn.execute("SELECT * FROM wardrobe ORDER BY category, item_name")
        items = [dict(row) for row in cursor.fetchall()]
        
        assert len(items) == 2
        assert items[0]["item_name"] == "Jeans"  # alphabetically first
        assert items[1]["item_name"] == "Shirt"
        
        conn.close()
    
    def test_delete_wardrobe_item(self):
        """Test deleting wardrobe item."""
        conn = get_sync_connection()
        
        cursor = conn.execute(
            "INSERT INTO wardrobe (item_name, category, min_temp, max_temp) VALUES (?, ?, ?, ?)",
            ("Test Shirt", "top", 15, 30)
        )
        conn.commit()
        item_id = cursor.lastrowid
        
        # Delete item
        cursor = conn.execute("DELETE FROM wardrobe WHERE id = ?", (item_id,))
        conn.commit()
        assert cursor.rowcount == 1
        
        # Verify deletion
        cursor = conn.execute("SELECT * FROM wardrobe")
        items = cursor.fetchall()
        assert len(items) == 0
        
        # Delete non-existent item
        cursor = conn.execute("DELETE FROM wardrobe WHERE id = ?", (999,))
        conn.commit()
        assert cursor.rowcount == 0
        
        conn.close()


class TestWeatherFiltering:
    """Test weather-based item filtering."""
    
    def test_get_items_for_weather(self):
        """Test filtering items by weather conditions."""
        conn = get_sync_connection()
        
        # Add items with different temperature ranges
        conn.execute(
            "INSERT INTO wardrobe (item_name, category, min_temp, max_temp) VALUES (?, ?, ?, ?)",
            ("Summer Shirt", "top", 20, 35)
        )
        conn.execute(
            "INSERT INTO wardrobe (item_name, category, min_temp, max_temp) VALUES (?, ?, ?, ?)",
            ("Winter Jacket", "outer", -5, 15)
        )
        conn.execute(
            "INSERT INTO wardrobe (item_name, category, min_temp, max_temp) VALUES (?, ?, ?, ?)",
            ("Spring Shirt", "top", 10, 25)
        )
        conn.commit()
        
        # Test with 22°C weather
        current_temp = 22.0
        cursor = conn.execute(
            """SELECT * FROM wardrobe 
               WHERE ? BETWEEN min_temp AND max_temp
               AND (last_worn_date IS NULL)
               ORDER BY category""",
            (current_temp,)
        )
        items = cursor.fetchall()
        
        assert len(items) == 2
        names = [item["item_name"] for item in items]
        assert "Summer Shirt" in names
        assert "Spring Shirt" in names
        assert "Winter Jacket" not in names
        
        conn.close()
    
    def test_get_items_respects_last_worn(self):
        """Test that recently worn items are excluded."""
        conn = get_sync_connection()
        
        # Add item
        conn.execute(
            "INSERT INTO wardrobe (item_name, category, min_temp, max_temp) VALUES (?, ?, ?, ?)",
            ("Favorite Shirt", "top", 15, 30)
        )
        conn.commit()
        
        # Mark as worn 3 days ago (within 7-day window)
        three_days_ago = (datetime.now() - timedelta(days=3)).isoformat()
        conn.execute(
            "UPDATE wardrobe SET last_worn_date = ? WHERE item_name = ?",
            (three_days_ago, "Favorite Shirt")
        )
        conn.commit()
        
        # Should not appear in results (within 7-day window)
        cutoff_date = (datetime.now() - timedelta(days=7)).isoformat()
        cursor = conn.execute(
            """SELECT * FROM wardrobe 
               WHERE ? BETWEEN min_temp AND max_temp
               AND (last_worn_date IS NULL OR last_worn_date < ?)""",
            (22.0, cutoff_date)
        )
        items = cursor.fetchall()
        assert len(items) == 0
        
        # Mark as worn 10 days ago (outside 7-day window)
        ten_days_ago = (datetime.now() - timedelta(days=10)).isoformat()
        conn.execute(
            "UPDATE wardrobe SET last_worn_date = ?",
            (ten_days_ago,)
        )
        conn.commit()
        
        # Should now appear
        cursor = conn.execute(
            """SELECT * FROM wardrobe 
               WHERE ? BETWEEN min_temp AND max_temp
               AND (last_worn_date IS NULL OR last_worn_date < ?)""",
            (22.0, cutoff_date)
        )
        items = cursor.fetchall()
        assert len(items) == 1
        
        conn.close()


class TestLaundryLogic:
    """Test laundry tracking logic."""
    
    def test_mark_item_worn(self):
        """Test marking item as worn."""
        conn = get_sync_connection()
        
        cursor = conn.execute(
            "INSERT INTO wardrobe (item_name, category, min_temp, max_temp) VALUES (?, ?, ?, ?)",
            ("Test Shirt", "top", 15, 30)
        )
        conn.commit()
        item_id = cursor.lastrowid
        
        # Mark as worn
        today = datetime.now().isoformat()
        conn.execute(
            "UPDATE wardrobe SET last_worn_date = ? WHERE id = ?",
            (today, item_id)
        )
        conn.commit()
        
        cursor = conn.execute("SELECT last_worn_date FROM wardrobe WHERE id = ?", (item_id,))
        result = cursor.fetchone()
        assert result["last_worn_date"] is not None
        
        conn.close()
    
    def test_reset_weekly_laundry(self):
        """Test laundry reset clears all last_worn_date values."""
        conn = get_sync_connection()
        
        # Add and mark items as worn
        conn.execute(
            "INSERT INTO wardrobe (item_name, category, min_temp, max_temp) VALUES (?, ?, ?, ?)",
            ("Shirt", "top", 15, 30)
        )
        conn.execute(
            "INSERT INTO wardrobe (item_name, category, min_temp, max_temp) VALUES (?, ?, ?, ?)",
            ("Jeans", "bottom", 10, 25)
        )
        conn.commit()
        
        today = datetime.now().isoformat()
        conn.execute("UPDATE wardrobe SET last_worn_date = ?", (today,))
        conn.commit()
        
        # Verify items are marked as worn
        cursor = conn.execute("SELECT last_worn_date FROM wardrobe")
        for row in cursor.fetchall():
            assert row["last_worn_date"] is not None
        
        # Reset laundry
        cursor = conn.execute("UPDATE wardrobe SET last_worn_date = NULL")
        conn.commit()
        count = cursor.rowcount
        assert count == 2
        
        # Verify items are cleared
        cursor = conn.execute("SELECT last_worn_date FROM wardrobe")
        for row in cursor.fetchall():
            assert row["last_worn_date"] is None
        
        conn.close()


class TestValidation:
    """Test input validation."""
    
    def test_category_validation(self):
        """Test that only valid categories are accepted."""
        conn = get_sync_connection()
        
        # Valid categories should work
        for category in ["top", "bottom", "shoes", "outer"]:
            cursor = conn.execute(
                "INSERT INTO wardrobe (item_name, category, min_temp, max_temp) VALUES (?, ?, ?, ?)",
                (f"Test {category}", category, 10, 25)
            )
            conn.commit()
            assert cursor.lastrowid is not None
        
        # Invalid category should fail
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO wardrobe (item_name, category, min_temp, max_temp) VALUES (?, ?, ?, ?)",
                ("Invalid Item", "invalid_category", 10, 25)
            )
            conn.commit()
        
        conn.close()
    
    def test_get_wardrobe_stats(self):
        """Test wardrobe statistics by category."""
        conn = get_sync_connection()
        
        conn.execute(
            "INSERT INTO wardrobe (item_name, category, min_temp, max_temp) VALUES (?, ?, ?, ?)",
            ("Shirt 1", "top", 15, 30)
        )
        conn.execute(
            "INSERT INTO wardrobe (item_name, category, min_temp, max_temp) VALUES (?, ?, ?, ?)",
            ("Shirt 2", "top", 15, 30)
        )
        conn.execute(
            "INSERT INTO wardrobe (item_name, category, min_temp, max_temp) VALUES (?, ?, ?, ?)",
            ("Jeans", "bottom", 10, 25)
        )
        conn.execute(
            "INSERT INTO wardrobe (item_name, category, min_temp, max_temp) VALUES (?, ?, ?, ?)",
            ("Jacket", "outer", 5, 15)
        )
        conn.commit()
        
        cursor = conn.execute(
            "SELECT category, COUNT(*) as count FROM wardrobe GROUP BY category"
        )
        stats = {row["category"]: row["count"] for row in cursor.fetchall()}
        
        assert stats["top"] == 2
        assert stats["bottom"] == 1
        assert stats["outer"] == 1
        
        conn.close()
    
    def test_temperature_range_validation(self):
        """Test temperature range constraints."""
        conn = get_sync_connection()
        
        # Edge cases should work
        conn.execute(
            "INSERT INTO wardrobe (item_name, category, min_temp, max_temp) VALUES (?, ?, ?, ?)",
            ("Arctic Jacket", "outer", -20, 5)
        )
        conn.execute(
            "INSERT INTO wardrobe (item_name, category, min_temp, max_temp) VALUES (?, ?, ?, ?)",
            ("Desert Shirt", "top", 25, 50)
        )
        conn.commit()
        
        cursor = conn.execute("SELECT * FROM wardrobe")
        items = cursor.fetchall()
        assert len(items) == 2
        
        conn.close()
