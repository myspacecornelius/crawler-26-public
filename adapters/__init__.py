"""CRAWL Adapters — Site-specific scraping adapters."""
from .base import BaseSiteAdapter
from .registry import AdapterRegistry, get_registry, register_adapter

__all__ = ["BaseSiteAdapter", "AdapterRegistry", "get_registry", "register_adapter"]
