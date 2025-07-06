"""
Supplier registry
"""

from typing import Dict, List, Type

from dropshipping.config import settings
from dropshipping.suppliers.base import BaseFetcher


class SupplierRegistry:
    """Supplier registry"""

    def __init__(self):
        self._suppliers: Dict[str, Type[BaseFetcher]] = {}
        self._register_defaults()

    def _register_defaults(self):
        """Register default suppliers"""
        # TODO: Auto-discover and register suppliers
        try:
            from dropshipping.suppliers.domeme.fetcher import DomemeFetcher

            self._suppliers["domeme"] = DomemeFetcher
        except ImportError:
            pass

        try:
            from dropshipping.suppliers.ownerclan.fetcher import OwnerclanFetcher

            self._suppliers["ownerclan"] = OwnerclanFetcher
        except ImportError:
            pass

        try:
            from dropshipping.suppliers.zentrade.fetcher import ZentradeFetcher

            self._suppliers["zentrade"] = ZentradeFetcher
        except ImportError:
            pass

    def register(self, name: str, fetcher_class: Type[BaseFetcher]):
        """Register a supplier"""
        self._suppliers[name] = fetcher_class

    def get_supplier(self, name: str, storage: "BaseStorage") -> BaseFetcher:
        """Get supplier instance"""
        if name not in self._suppliers:
            raise ValueError(f"Unknown supplier: {name}")
        fetcher_class = self._suppliers[name]
        supplier_settings = getattr(settings, name)
        if name == "ownerclan":
            return fetcher_class(
                storage=storage,
                supplier_name=name,
                username=supplier_settings.username,
                password=supplier_settings.password,
                api_url=supplier_settings.api_url,
            )
        return fetcher_class(
            storage=storage,
            supplier_name=name,
            api_key=supplier_settings.api_key,
            api_url=supplier_settings.api_url,
        )

    def list_suppliers(self) -> List[str]:
        """List registered suppliers"""
        return list(self._suppliers.keys())
