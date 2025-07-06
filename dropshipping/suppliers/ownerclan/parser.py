"""
오너클랜 응답 파서
GraphQL 응답을 파싱하여 표준 형식으로 변환
"""

from typing import Any, Dict, List, Optional
from dropshipping.suppliers.base import BaseParser


class OwnerclanParser(BaseParser):
    """오너클랜 GraphQL 응답 파서"""

    def parse_products(self, response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """상품 목록 응답 파싱
        
        Args:
            response: GraphQL API 응답
            
        Returns:
            파싱된 상품 목록
        """
        # GraphQL 응답에서 상품 목록 추출
        data = response.get("data", {})
        all_items = data.get("allItems", {})
        edges = all_items.get("edges", [])
        
        products = []
        for edge in edges:
            node = edge.get("node", {})
            if node:
                # 기본 정보만 있는 경우 상세 정보는 별도 조회 필요
                products.append(self._parse_node(node))
                
        return products

    def parse_product_detail(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """상품 상세 응답 파싱
        
        Args:
            response: GraphQL API 응답
            
        Returns:
            파싱된 상품 상세 정보
        """
        data = response.get("data", {})
        item = data.get("item", {})
        
        if not item:
            return {}
            
        return self._parse_node(item)
    
    def _parse_node(self, node: Dict[str, Any]) -> Dict[str, Any]:
        """GraphQL 노드를 표준 형식으로 파싱
        
        Args:
            node: GraphQL 노드
            
        Returns:
            파싱된 상품 정보
        """
        # 카테고리 정보 추출
        category = node.get("category", {})
        category_name = category.get("name", "") if isinstance(category, dict) else ""
        
        # 옵션 정보 파싱
        options = self._parse_options(node.get("options", []))
        
        # 이미지 URL 목록 생성
        images = node.get("images", [])
        if isinstance(images, str):
            images = [images] if images else []
        
        # 재고 수량 계산
        if options:
            total_stock = sum(opt.get("quantity", 0) for opt in options)
        else:
            total_stock = int(node.get("stock") or 0)
        
        return {
            "id": node.get("key", ""),
            "name": node.get("name", ""),
            "model": node.get("model", ""),
            "brand": node.get("production", ""),  # 제조사를 브랜드로 사용
            "origin": node.get("origin", ""),
            "price": float(node.get("price") or 0),
            "fixed_price": float(node.get("fixedPrice") or 0),
            "category": category_name,
            "shipping_fee": float(node.get("shippingFee") or 0),
            "shipping_type": node.get("shippingType", ""),
            "status": node.get("status", ""),
            "options": options,
            "tax_free": node.get("taxFree", False),
            "adult_only": node.get("adultOnly", False),
            "returnable": node.get("returnable", True),
            "images": images,
            "stock": total_stock,
            "created_at": node.get("createdAt", ""),
            "updated_at": node.get("updatedAt", ""),
        }
    
    def _parse_options(self, options: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """상품 옵션 파싱
        
        Args:
            options: 원본 옵션 목록
            
        Returns:
            파싱된 옵션 목록
        """
        parsed_options = []
        
        for option in options:
            # 옵션 속성들을 문자열로 조합
            attributes = option.get("optionAttributes", [])
            option_names = []
            option_values = []
            
            for attr in attributes:
                name = attr.get("name", "")
                value = attr.get("value", "")
                if name and value:
                    option_names.append(name)
                    option_values.append(value)
            
            # 옵션명 생성 (예: "색상: 블랙, 사이즈: L")
            option_name = ", ".join(f"{n}: {v}" for n, v in zip(option_names, option_values))
            
            parsed_options.append({
                "name": option_name,
                "price": float(option.get("price") or 0),
                "quantity": int(option.get("quantity") or 0),
                "attributes": {n: v for n, v in zip(option_names, option_values)}
            })
            
        return parsed_options
    
    def parse_error(self, response: Dict[str, Any]) -> Optional[str]:
        """GraphQL 에러 응답 파싱
        
        Args:
            response: API 응답
            
        Returns:
            에러 메시지 또는 None
        """
        errors = response.get("errors", [])
        if errors:
            # 첫 번째 에러 메시지 반환
            first_error = errors[0]
            return first_error.get("message", "Unknown GraphQL error")
        return None