"""
Zentrade transformer
"""

from typing import Dict, Any
from dropshipping.transformers.base import BaseTransformer
from dropshipping.models.product import StandardProduct


class ZentradeTransformer(BaseTransformer):
    """Zentrade product transformer"""
    
    def transform(self, raw_product: Dict[str, Any]) -> StandardProduct:
        """Transform raw product to standard format"""
        # TODO: Implement actual transformation logic
        return StandardProduct(
            supplier_id=raw_product.get("id", ""),
            supplier="zentrade",
            name=raw_product.get("name", ""),
            brand=raw_product.get("brand", ""),
            category=raw_product.get("category", ""),
            original_price=float(raw_product.get("price", 0)),
            selling_price=float(raw_product.get("price", 0)) * 1.3,
            currency="KRW",
            description=raw_product.get("description", ""),
            images=[],
            options=[],
            stock_quantity=raw_product.get("stock", 0),
            is_active=True
        )