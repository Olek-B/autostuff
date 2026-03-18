"""
Centralized configuration management with feature toggles.
Loads from environment variables and provides feature enable/disable checks.
"""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Config:
    """Application configuration with feature toggles."""
    
    # General
    allowed_user_id: int = field(default_factory=lambda: int(os.environ.get("ALLOWED_USER_ID", "0")))
    latitude: float = field(default_factory=lambda: float(os.environ.get("LATITUDE", "51.5074")))
    longitude: float = field(default_factory=lambda: float(os.environ.get("LONGITUDE", "-0.1278")))
    
    # Telegram Bot
    telegram_bot_token: Optional[str] = field(default_factory=lambda: os.environ.get("TELEGRAM_BOT_TOKEN"))
    
    # AI Services
    groq_api_key: Optional[str] = field(default_factory=lambda: os.environ.get("GROQ_API_KEY"))
    
    # Feature Toggles - AutoClothes
    autoclothes_enabled: bool = field(default_factory=lambda: os.environ.get("AUTOCLOTHES_ENABLED", "true").lower() != "false")
    auto_outfit_disabled: bool = field(default_factory=lambda: os.environ.get("AUTO_OUTFIT_DISABLED", "false").lower() == "true")
    laundry_notification: bool = field(default_factory=lambda: os.environ.get("LAUNDRY_NOTIFICATION", "false").lower() == "true")
    
    # Feature Toggles - Future Features
    news_tracking_enabled: bool = field(default_factory=lambda: os.environ.get("NEWS_TRACKING_ENABLED", "false").lower() == "true")
    price_tracking_enabled: bool = field(default_factory=lambda: os.environ.get("PRICE_TRACKING_ENABLED", "false").lower() == "true")
    
    # Logging
    log_level: str = field(default_factory=lambda: os.environ.get("LOG_LEVEL", "INFO"))
    
    def validate(self) -> list[str]:
        """
        Validate configuration and return list of errors.
        Returns empty list if configuration is valid.
        """
        errors = []
        
        # Check AutoClothes dependencies
        if self.autoclothes_enabled:
            if not self.telegram_bot_token:
                errors.append("AUTOCLOTHES_ENABLED requires TELEGRAM_BOT_TOKEN")
            if not self.groq_api_key:
                errors.append("AUTOCLOTHES_ENABLED requires GROQ_API_KEY for AI features")
        
        return errors
    
    def is_feature_enabled(self, feature: str) -> bool:
        """Check if a specific feature is enabled."""
        feature_map = {
            "autoclothes": self.autoclothes_enabled,
            "news_tracking": self.news_tracking_enabled,
            "price_tracking": self.price_tracking_enabled,
        }
        return feature_map.get(feature, False)


# Global config instance
config = Config()


def get_config() -> Config:
    """Get the global configuration instance."""
    return config


def is_feature_enabled(feature: str) -> bool:
    """Check if a feature is enabled in the global config."""
    return config.is_feature_enabled(feature)
