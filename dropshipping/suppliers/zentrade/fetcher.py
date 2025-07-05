"""
Zentrade fetcher
"""

from typing import Any, Dict, Optional

from dropshipping.suppliers.base import BaseFetcher


class ZentradeFetcher(BaseFetcher):
    """Zentrade supplier fetcher"""

    def __init__(self):
        super().__init__()
        self.base_url = "https://api.zentrade.com"

    async def fetch_products(
        self, category: Optional[str] = None, page: int = 1, limit: int = 100
    ) -> Dict[str, Any]:
        """Fetch products from Zentrade API"""
        # TODO: Implement actual API call
        return {"products": [], "total": 0, "page": page, "limit": limit}

    async def fetch_product_detail(self, product_id: str) -> Dict[str, Any]:
        """Fetch single product details"""
        # TODO: Implement actual API call
        return {}
