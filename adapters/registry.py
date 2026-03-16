"""
CRAWL — Adapter Registry & Plugin Discovery System

Provides a centralized registry for site adapters with:
- Decorator-based registration (@register_adapter)
- Auto-discovery from the adapters/ package
- Metadata support (verticals, rate limits, credentials)
- Runtime lookup by name
"""

import importlib
import logging
import pkgutil
from pathlib import Path
from typing import Dict, List, Optional, Type

from .base import BaseSiteAdapter

logger = logging.getLogger(__name__)


class AdapterMetadata:
    """Metadata describing an adapter's capabilities and requirements."""

    def __init__(
        self,
        name: str,
        adapter_class: Type[BaseSiteAdapter],
        *,
        verticals: Optional[List[str]] = None,
        rate_limit_rpm: int = 60,
        requires_auth: bool = False,
        required_credentials: Optional[List[str]] = None,
        description: str = "",
    ):
        self.name = name
        self.adapter_class = adapter_class
        self.verticals = verticals or []
        self.rate_limit_rpm = rate_limit_rpm
        self.requires_auth = requires_auth
        self.required_credentials = required_credentials or []
        self.description = description

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "adapter_class": self.adapter_class.__name__,
            "verticals": self.verticals,
            "rate_limit_rpm": self.rate_limit_rpm,
            "requires_auth": self.requires_auth,
            "required_credentials": self.required_credentials,
            "description": self.description,
        }


class AdapterRegistry:
    """
    Central registry for all site adapters.

    Supports three discovery mechanisms (in order):
    1. Explicit registration via register() or @register_adapter decorator
    2. Auto-discovery: scan the adapters/ package for BaseSiteAdapter subclasses
    3. Entry points: load adapters from installed packages (setuptools)

    Usage:
        registry = AdapterRegistry()
        registry.auto_discover()
        adapter_cls = registry.get("openvc")
    """

    def __init__(self):
        self._adapters: Dict[str, AdapterMetadata] = {}

    def register(
        self,
        name: str,
        adapter_class: Type[BaseSiteAdapter],
        **metadata_kwargs,
    ):
        """Register an adapter class under a given name."""
        meta = AdapterMetadata(name, adapter_class, **metadata_kwargs)
        self._adapters[name] = meta
        logger.debug(f"Registered adapter: {name} ({adapter_class.__name__})")

    def get(self, name: str) -> Optional[Type[BaseSiteAdapter]]:
        """Look up an adapter class by name."""
        meta = self._adapters.get(name)
        return meta.adapter_class if meta else None

    def get_metadata(self, name: str) -> Optional[AdapterMetadata]:
        """Get full metadata for an adapter."""
        return self._adapters.get(name)

    def list_adapters(self) -> List[str]:
        """Return all registered adapter names."""
        return list(self._adapters.keys())

    def list_metadata(self) -> List[dict]:
        """Return metadata dicts for all registered adapters."""
        return [m.to_dict() for m in self._adapters.values()]

    def filter_by_vertical(self, vertical: str) -> List[str]:
        """Return adapter names that support a given vertical."""
        return [
            name
            for name, meta in self._adapters.items()
            if vertical.lower() in [v.lower() for v in meta.verticals]
        ]

    def auto_discover(self):
        """
        Scan all modules in the adapters/ package and register any
        BaseSiteAdapter subclass that has an ADAPTER_NAME class attribute.
        """
        adapters_dir = Path(__file__).parent
        package_name = __package__ or "adapters"

        for module_info in pkgutil.iter_modules([str(adapters_dir)]):
            if module_info.name.startswith("_") or module_info.name in ("base", "registry"):
                continue
            try:
                module = importlib.import_module(f".{module_info.name}", package=package_name)
                self._scan_module(module)
            except Exception as e:
                logger.warning(f"Failed to import adapter module '{module_info.name}': {e}")

    def discover_entry_points(self, group: str = "crawl.adapters"):
        """
        Load adapters from setuptools entry points.
        Third-party packages can register adapters via:
            [project.entry-points."crawl.adapters"]
            my_adapter = "my_package.adapters:MyAdapter"
        """
        try:
            from importlib.metadata import entry_points

            eps = entry_points()
            # Python 3.12+ returns a SelectableGroups, older returns dict
            if hasattr(eps, "select"):
                adapter_eps = eps.select(group=group)
            else:
                adapter_eps = eps.get(group, [])

            for ep in adapter_eps:
                try:
                    cls = ep.load()
                    if isinstance(cls, type) and issubclass(cls, BaseSiteAdapter):
                        name = getattr(cls, "ADAPTER_NAME", ep.name)
                        self._register_from_class(name, cls)
                except Exception as e:
                    logger.warning(f"Failed to load entry point '{ep.name}': {e}")
        except ImportError:
            pass

    def _scan_module(self, module):
        """Scan a module for BaseSiteAdapter subclasses and register them."""
        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            if (
                isinstance(obj, type)
                and issubclass(obj, BaseSiteAdapter)
                and obj is not BaseSiteAdapter
            ):
                name = getattr(obj, "ADAPTER_NAME", None)
                if name is None:
                    # Derive name from class: OpenVCAdapter -> openvc
                    name = attr_name.replace("Adapter", "").lower()
                    # Convert CamelCase to snake_case
                    import re
                    name = re.sub(r"(?<=[a-z])(?=[A-Z])", "_", name).lower()
                self._register_from_class(name, obj)

    def _register_from_class(self, name: str, cls: Type[BaseSiteAdapter]):
        """Register an adapter class, pulling metadata from class attributes."""
        if name in self._adapters:
            return  # Already registered (explicit registration takes priority)

        self.register(
            name=name,
            adapter_class=cls,
            verticals=getattr(cls, "VERTICALS", []),
            rate_limit_rpm=getattr(cls, "RATE_LIMIT_RPM", 60),
            requires_auth=getattr(cls, "REQUIRES_AUTH", False),
            required_credentials=getattr(cls, "REQUIRED_CREDENTIALS", []),
            description=getattr(cls, "DESCRIPTION", cls.__doc__ or ""),
        )


def register_adapter(
    name: str,
    *,
    verticals: Optional[List[str]] = None,
    rate_limit_rpm: int = 60,
    requires_auth: bool = False,
    required_credentials: Optional[List[str]] = None,
    description: str = "",
):
    """
    Class decorator to register a site adapter with the global registry.

    Usage:
        @register_adapter("my_site", verticals=["vc"], rate_limit_rpm=30)
        class MySiteAdapter(BaseSiteAdapter):
            def parse_card(self, card):
                ...
    """

    def decorator(cls):
        cls.ADAPTER_NAME = name
        cls.VERTICALS = verticals or []
        cls.RATE_LIMIT_RPM = rate_limit_rpm
        cls.REQUIRES_AUTH = requires_auth
        cls.REQUIRED_CREDENTIALS = required_credentials or []
        cls.DESCRIPTION = description or cls.__doc__ or ""
        # Register with the global registry instance
        _global_registry.register(
            name=name,
            adapter_class=cls,
            verticals=verticals,
            rate_limit_rpm=rate_limit_rpm,
            requires_auth=requires_auth,
            required_credentials=required_credentials,
            description=description,
        )
        return cls

    return decorator


# Global registry singleton
_global_registry = AdapterRegistry()


def get_registry() -> AdapterRegistry:
    """Get the global adapter registry, auto-discovering if empty."""
    if not _global_registry.list_adapters():
        _global_registry.auto_discover()
        _global_registry.discover_entry_points()
    return _global_registry
