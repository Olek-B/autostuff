"""
AutoClothes module - AI-powered daily outfit suggestions.
Depends on: weather service, AI service, database
"""

from .handlers import register_handlers
from .scheduler import register_schedulers

__all__ = ["register_handlers", "register_schedulers"]
