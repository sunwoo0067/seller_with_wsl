"""
Base parser class
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseParser(ABC):
    """Base parser for supplier responses"""

    @abstractmethod
    def parse_products(self, response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse products response"""
        pass

    @abstractmethod
    def parse_product_detail(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Parse product detail response"""
        pass
