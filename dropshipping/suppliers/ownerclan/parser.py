"""
Ownerclan parser
"""

from typing import Dict, List, Any
from dropshipping.suppliers.base import BaseParser


class OwnerclanParser(BaseParser):
    """Ownerclan response parser"""
    
    def parse_products(self, response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse products response"""
        # TODO: Implement actual parsing logic
        return response.get("products", [])
    
    def parse_product_detail(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Parse product detail response"""
        # TODO: Implement actual parsing logic
        return response