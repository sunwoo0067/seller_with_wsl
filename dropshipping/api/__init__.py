"""
드랍쉬핑 자동화 시스템 API
FastAPI 기반 RESTful API 서버
"""

from .main import app
from .routers import marketplaces, monitoring, orders, products, sourcing, suppliers

__all__ = ["app", "products", "orders", "suppliers", "marketplaces", "sourcing", "monitoring"]
