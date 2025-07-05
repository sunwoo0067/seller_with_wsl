"""
경쟁사 모니터링 시스템
경쟁사 상품, 가격, 판매 전략 모니터링
"""

import asyncio
import re
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Tuple

from loguru import logger

from dropshipping.models.sourcing import CompetitorInfo
from dropshipping.storage.base import BaseStorage


class CompetitorMonitor:
    """경쟁사 모니터"""

    def __init__(self, storage: BaseStorage, config: Optional[Dict[str, Any]] = None):
        """
        초기화

        Args:
            storage: 저장소 인스턴스
            config: 모니터링 설정
        """
        self.storage = storage
        self.config = config or {}

        # 모니터링 설정
        self.price_change_threshold = self.config.get("price_change_threshold", 0.05)  # 5%
        self.update_interval = self.config.get("update_interval", 86400)  # 24시간
        self.competitor_limit = self.config.get("competitor_limit", 20)  # 경쟁사 수 제한

        # 마켓플레이스별 스크래퍼 (실제로는 각 마켓플레이스 API/스크래핑)
        self.scrapers = {}

        # 캐시
        self._competitor_cache = {}
        self._last_update = {}

    async def identify_competitors(
        self, product_id: str, marketplace: Optional[str] = None
    ) -> List[CompetitorInfo]:
        """
        경쟁사 식별

        Args:
            product_id: 우리 상품 ID
            marketplace: 마켓플레이스 (None이면 전체)

        Returns:
            경쟁사 정보 목록
        """
        try:
            our_product = await self._get_product_info_for_competitor_identification(product_id)
            if not our_product:
                return []

            cache_key = f"{product_id}_{marketplace or 'all'}"
            cached_competitors = self._check_competitor_cache(cache_key)
            if cached_competitors:
                return cached_competitors

            category = our_product.get("category_name", "")
            keywords = self._extract_keywords(our_product.get("name", ""))
            price_range = self._get_price_range(our_product.get("price", 0))

            competitors = await self._search_competitors_across_marketplaces(
                marketplace, category, keywords, price_range
            )

            final_competitors = self._sort_and_limit_competitors(competitors)
            self._competitor_cache[cache_key] = {
                "competitors": final_competitors,
                "timestamp": datetime.now(),
            }

            return final_competitors

        except Exception as e:
            logger.error(f"경쟁사 식별 오류: {str(e)}")
            return []

    async def _get_product_info_for_competitor_identification(
        self, product_id: str
    ) -> Optional[Dict[str, Any]]:
        """경쟁사 식별을 위한 상품 정보를 가져옵니다."""
        our_product = await self.storage.get("products", product_id)
        if not our_product:
            logger.error(f"상품을 찾을 수 없습니다: {product_id}")
        return our_product

    def _check_competitor_cache(self, cache_key: str) -> Optional[List[CompetitorInfo]]:
        """경쟁사 캐시를 확인합니다."""
        if cache_key in self._competitor_cache:
            cached = self._competitor_cache[cache_key]
            if cached["timestamp"] > datetime.now() - timedelta(seconds=self.update_interval):
                return cached["competitors"]
        return None

    async def _search_competitors_across_marketplaces(
        self,
        marketplace: Optional[str],
        category: str,
        keywords: List[str],
        price_range: Tuple[Decimal, Decimal],
    ) -> List[CompetitorInfo]:
        """지정된 마켓플레이스 또는 모든 마켓플레이스에서 경쟁사를 검색합니다."""
        competitors = []
        if marketplace:
            competitors = await self._find_competitors_by_marketplace(
                marketplace, category, keywords, price_range
            )
        else:
            tasks = []
            for mp in ["coupang", "11st", "gmarket", "smartstore"]:
                tasks.append(
                    self._find_competitors_by_marketplace(mp, category, keywords, price_range)
                )
            results = await asyncio.gather(*tasks)
            for res in results:
                competitors.extend(res)
        return competitors

    def _sort_and_limit_competitors(
        self, competitors: List[CompetitorInfo]
    ) -> List[CompetitorInfo]:
        """경쟁사를 정렬하고 제한합니다."""
        return sorted(competitors, key=lambda x: x.review_count or 0, reverse=True)[
            : self.competitor_limit
        ]

    async def monitor_competitor_prices(
        self, product_id: str, competitors: Optional[List[CompetitorInfo]] = None
    ) -> Dict[str, Any]:
        """
        경쟁사 가격 모니터링

        Args:
            product_id: 우리 상품 ID
            competitors: 경쟁사 목록 (None이면 자동 식별)

        Returns:
            가격 분석 결과
        """
        try:
            if not competitors:
                competitors = await self.identify_competitors(product_id)

            if not competitors:
                return {"error": "경쟁사를 찾을 수 없습니다"}

            our_price = await self._get_our_product_price(product_id)
            if our_price is None:
                return {"error": f"우리 상품 가격을 찾을 수 없습니다: {product_id}"}

            competitor_prices = [c.average_price for c in competitors]
            price_statistics = self._calculate_price_statistics(competitor_prices)

            position_info = self._calculate_our_product_position(our_price, competitor_prices)

            price_changes = await asyncio.gather(
                *[self._detect_price_change(c) for c in competitors]
            )
            price_changes = [change for change in price_changes if change]

            recommended_price = self._calculate_recommended_price(
                our_price,
                competitor_prices,
                await self.storage.get("products", product_id),  # 우리 상품 정보 다시 가져오기
            )

            return {
                "product_id": product_id,
                "our_price": our_price,
                "competitor_count": len(competitors),
                "price_statistics": price_statistics,
                "position": position_info,
                "price_changes": price_changes,
                "recommended_price": recommended_price,
                "competitors": [
                    {
                        "id": c.competitor_id,
                        "name": c.name,
                        "price": c.average_price,
                        "marketplace": c.marketplace,
                    }
                    for c in sorted(competitors, key=lambda x: x.average_price)[:10]
                ],
                "analyzed_at": datetime.now(),
            }

        except Exception as e:
            logger.error(f"가격 모니터링 오류: {str(e)}")
            return {"error": str(e)}

    async def _get_our_product_price(self, product_id: str) -> Optional[Decimal]:
        """우리 상품의 가격을 가져옵니다."""
        our_product = await self.storage.get("products", product_id)
        if not our_product or "price" not in our_product:
            return None
        return Decimal(str(our_product["price"]))

    def _calculate_price_statistics(self, prices: List[Decimal]) -> Dict[str, Decimal]:
        """경쟁사 가격 통계를 계산합니다."""
        if not prices:
            return {
                "min": Decimal("0"),
                "max": Decimal("0"),
                "avg": Decimal("0"),
                "median": Decimal("0"),
            }

        min_price = min(prices)
        max_price = max(prices)
        avg_price = sum(prices) / len(prices)
        median_price = sorted(prices)[len(prices) // 2]
        return {"min": min_price, "max": max_price, "avg": avg_price, "median": median_price}

    def _calculate_our_product_position(
        self, our_price: Decimal, competitor_prices: List[Decimal]
    ) -> Dict[str, Any]:
        """우리 상품의 시장 포지션을 계산합니다."""
        if not competitor_prices:
            return {"rank": 1, "percentile": 100.0, "competitiveness": "unknown"}

        cheaper_count = sum(1 for p in competitor_prices if p < our_price)
        position = cheaper_count + 1
        percentile = (cheaper_count / len(competitor_prices)) * 100

        price_competitiveness = "competitive"
        avg_price = sum(competitor_prices) / len(competitor_prices)
        if our_price < avg_price * Decimal("0.9"):
            price_competitiveness = "very_competitive"
        elif our_price > avg_price * Decimal("1.1"):
            price_competitiveness = "expensive"

        return {
            "rank": position,
            "percentile": percentile,
            "competitiveness": price_competitiveness,
        }

    async def analyze_competitor_strategy(self, competitor_id: str) -> Dict[str, Any]:
        """
        경쟁사 전략 분석

        Args:
            competitor_id: 경쟁사 ID

        Returns:
            전략 분석 결과
        """
        try:
            competitor = await self._get_competitor_details(competitor_id)
            if not competitor:
                return {"error": "경쟁사 정보를 찾을 수 없습니다"}

            portfolio = await self._analyze_product_portfolio(competitor_id)
            pricing_strategy = self._analyze_pricing_strategy(portfolio)
            promotion_strategy = await self._analyze_promotion_strategy(competitor_id)
            shipping_strategy = self._build_shipping_strategy(competitor, portfolio)
            customer_satisfaction = self._build_customer_satisfaction(competitor)
            swot = self._analyze_swot(
                competitor, portfolio, pricing_strategy, customer_satisfaction
            )

            return {
                "competitor_id": competitor_id,
                "name": competitor.name,
                "marketplace": competitor.marketplace,
                "portfolio": portfolio,
                "pricing_strategy": pricing_strategy,
                "promotion_strategy": promotion_strategy,
                "shipping_strategy": shipping_strategy,
                "customer_satisfaction": customer_satisfaction,
                "swot_analysis": swot,
                "analyzed_at": datetime.now(),
            }

        except Exception as e:
            logger.error(f"전략 분석 오류: {str(e)}")
            return {"error": str(e)}

    async def _get_competitor_details(self, competitor_id: str) -> Optional[CompetitorInfo]:
        """경쟁사 상세 정보를 가져옵니다."""
        return await self._get_competitor_info(competitor_id)

    def _build_shipping_strategy(
        self, competitor: CompetitorInfo, portfolio: Dict[str, Any]
    ) -> Dict[str, Any]:
        """배송 전략을 구성합니다."""
        return {
            "method": competitor.shipping_method,
            "average_days": competitor.average_delivery_days,
            "free_shipping_threshold": self._estimate_free_shipping_threshold(portfolio),
        }

    def _build_customer_satisfaction(self, competitor: CompetitorInfo) -> Dict[str, Any]:
        """고객 만족도 정보를 구성합니다."""
        return {
            "average_rating": competitor.average_rating,
            "review_count": competitor.review_count,
            "sentiment": self._analyze_review_sentiment(competitor.average_rating),
        }

    async def track_new_competitors(
        self, category: str, marketplace: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        신규 경쟁사 추적

        Args:
            category: 카테고리
            marketplace: 마켓플레이스

        Returns:
            신규 경쟁사 목록
        """
        try:
            existing_ids = await self._get_existing_competitor_ids(category, marketplace)
            current_competitors = await self._search_current_competitors(category, marketplace)
            new_competitors_analysis = await self._identify_and_analyze_new_competitors(
                existing_ids, current_competitors
            )

            for new_comp in new_competitors_analysis:
                await self._save_competitor(new_comp["competitor"])

            return new_competitors_analysis

        except Exception as e:
            logger.error(f"신규 경쟁사 추적 오류: {str(e)}")
            return []

    async def _get_existing_competitor_ids(
        self, category: str, marketplace: Optional[str]
    ) -> Set[str]:
        """기존 경쟁사 ID 목록을 가져옵니다."""
        filters = {"category": category}
        if marketplace:
            filters["marketplace"] = marketplace
        existing_competitors = await self.storage.list("competitors", filters=filters)
        return {c["competitor_id"] for c in existing_competitors}

    async def _identify_and_analyze_new_competitors(
        self, existing_ids: Set[str], current_competitors: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """신규 경쟁사를 식별하고 분석합니다."""
        new_competitors_analysis = []
        for competitor in current_competitors:
            if competitor["competitor_id"] not in existing_ids:
                analysis = await self._analyze_new_competitor(competitor)
                new_competitors_analysis.append(
                    {
                        "competitor": competitor,
                        "analysis": analysis,
                        "discovered_at": datetime.now(),
                    }
                )
        return new_competitors_analysis

    def _extract_keywords(self, product_name: str) -> List[str]:
        """상품명에서 키워드 추출"""
        # 불용어 제거
        stopwords = {"및", "또는", "의", "을", "를", "이", "가", "은", "는"}

        # 특수문자 제거 및 분리
        words = re.findall(r"\w+", product_name.lower())

        # 키워드 필터링
        keywords = []
        for word in words:
            if len(word) > 1 and word not in stopwords:
                keywords.append(word)

        return keywords[:5]  # 상위 5개

    def _get_price_range(self, base_price: float) -> Tuple[Decimal, Decimal]:
        """가격 범위 계산"""
        price = Decimal(str(base_price))
        margin = price * Decimal("0.3")  # 30% 범위

        return (price - margin, price + margin)

    async def _find_competitors_by_marketplace(
        self,
        marketplace: str,
        category: str,
        keywords: List[str],
        price_range: Tuple[Decimal, Decimal],
    ) -> List[CompetitorInfo]:
        """마켓플레이스별 경쟁사 검색"""
        # 실제로는 각 마켓플레이스 API/스크래핑 사용
        # 여기서는 시뮬레이션

        competitors = []

        # DB에서 유사 상품 검색 (실제로는 마켓플레이스 검색)
        similar_products = await self.storage.list(
            "competitor_products",
            filters={
                "marketplace": marketplace,
                "category": category,
                "price": {"$gte": float(price_range[0]), "$lte": float(price_range[1])},
            },
            limit=50,
        )

        # 키워드 매칭
        for product in similar_products:
            product_name = product.get("name", "").lower()
            match_count = sum(1 for kw in keywords if kw in product_name)

            if match_count >= len(keywords) * 0.4:  # 40% 이상 매칭
                competitor = CompetitorInfo(
                    competitor_id=f"{marketplace}_{product['seller_id']}",
                    name=product.get("seller_name", "Unknown"),
                    marketplace=marketplace,
                    product_count=product.get("product_count", 1),
                    average_rating=product.get("rating", 0.0),
                    review_count=product.get("review_count", 0),
                    min_price=Decimal(str(product.get("min_price", 0))),
                    max_price=Decimal(str(product.get("max_price", 0))),
                    average_price=Decimal(str(product.get("price", 0))),
                    shipping_method=product.get("shipping_method"),
                    average_delivery_days=product.get("delivery_days"),
                    last_updated=datetime.now(),
                )
                competitors.append(competitor)

        return competitors

    async def _detect_price_change(self, competitor: CompetitorInfo) -> Optional[Dict[str, Any]]:
        """가격 변동 감지"""
        # 이전 가격 조회
        history = await self.storage.list(
            "competitor_price_history", filters={"competitor_id": competitor.competitor_id}, limit=1
        )

        if not history:
            # 첫 기록
            await self.storage.save(
                "competitor_price_history",
                {
                    "competitor_id": competitor.competitor_id,
                    "price": float(competitor.average_price),
                    "recorded_at": datetime.now(),
                },
            )
            return None

        prev_price = Decimal(str(history[0]["price"]))
        current_price = competitor.average_price

        if prev_price == 0:
            return None

        change_rate = (current_price - prev_price) / prev_price

        if abs(change_rate) >= self.price_change_threshold:
            # 가격 변동 기록
            await self.storage.save(
                "competitor_price_history",
                {
                    "competitor_id": competitor.competitor_id,
                    "price": float(current_price),
                    "recorded_at": datetime.now(),
                },
            )

            return {
                "competitor_id": competitor.competitor_id,
                "name": competitor.name,
                "previous_price": prev_price,
                "current_price": current_price,
                "change_rate": float(change_rate) * 100,
                "direction": "up" if change_rate > 0 else "down",
            }

        return None

    def _calculate_recommended_price(
        self, our_price: Decimal, competitor_prices: List[Decimal], product: Dict[str, Any]
    ) -> Decimal:
        """추천 가격 계산"""
        # 기본 전략: 중간값 근처
        sorted_prices = sorted(competitor_prices)
        median_price = sorted_prices[len(sorted_prices) // 2]

        # 마진 고려
        min_margin = Decimal("0.2")  # 최소 20% 마진
        cost = Decimal(str(product.get("cost", 0)))
        min_price = cost * (1 + min_margin)

        # 경쟁력 있는 가격 (중간값의 95%)
        competitive_price = median_price * Decimal("0.95")

        # 최소 가격 보장
        recommended = max(min_price, competitive_price)

        # 현재 가격과 큰 차이가 나면 단계적 조정
        max_change = Decimal("0.1")  # 최대 10% 변경
        if abs(recommended - our_price) / our_price > max_change:
            if recommended > our_price:
                recommended = our_price * (1 + max_change)
            else:
                recommended = our_price * (1 - max_change)

        return recommended.quantize(Decimal("100"))  # 100원 단위

    async def _get_competitor_info(self, competitor_id: str) -> Optional[CompetitorInfo]:
        """경쟁사 정보 조회"""
        # 캐시 확인
        if competitor_id in self._competitor_cache:
            return self._competitor_cache[competitor_id]

        # DB 조회
        data = await self.storage.get("competitors", competitor_id)
        if not data:
            return None

        competitor = CompetitorInfo(**data)
        self._competitor_cache[competitor_id] = competitor

        return competitor

    async def _analyze_product_portfolio(self, competitor_id: str) -> Dict[str, Any]:
        """상품 포트폴리오 분석"""
        # 경쟁사 상품 조회
        products = await self.storage.list(
            "competitor_products", filters={"seller_id": competitor_id}
        )

        # 카테고리별 분포
        category_dist = {}
        price_ranges = {}

        for product in products:
            category = product.get("category", "기타")
            price = Decimal(str(product.get("price", 0)))

            if category not in category_dist:
                category_dist[category] = 0
                price_ranges[category] = []

            category_dist[category] += 1
            price_ranges[category].append(price)

        # 주력 카테고리
        main_categories = sorted(category_dist.items(), key=lambda x: x[1], reverse=True)[:3]

        # 가격대별 분포
        price_distribution = {
            "low": 0,  # 10만원 미만
            "medium": 0,  # 10-50만원
            "high": 0,  # 50만원 이상
        }

        for product in products:
            price = Decimal(str(product.get("price", 0)))
            if price < 100000:
                price_distribution["low"] += 1
            elif price < 500000:
                price_distribution["medium"] += 1
            else:
                price_distribution["high"] += 1

        return {
            "total_products": len(products),
            "category_distribution": category_dist,
            "main_categories": main_categories,
            "price_distribution": price_distribution,
            "average_price_by_category": {
                cat: sum(prices) / len(prices) if prices else Decimal("0")
                for cat, prices in price_ranges.items()
            },
        }

    def _analyze_pricing_strategy(self, portfolio: Dict[str, Any]) -> Dict[str, Any]:
        """가격 전략 분석"""
        price_dist = portfolio["price_distribution"]
        total = portfolio["total_products"]

        if total == 0:
            return {"strategy": "unknown"}

        # 가격대 비중
        low_ratio = price_dist["low"] / total
        medium_ratio = price_dist["medium"] / total
        high_ratio = price_dist["high"] / total

        # 전략 판단
        strategy = "balanced"
        if low_ratio > 0.6:
            strategy = "low_price"
        elif high_ratio > 0.4:
            strategy = "premium"
        elif medium_ratio > 0.7:
            strategy = "mid_range"

        return {
            "strategy": strategy,
            "price_distribution_ratio": {
                "low": low_ratio,
                "medium": medium_ratio,
                "high": high_ratio,
            },
            "focus": "volume" if strategy == "low_price" else "margin",
        }

    async def _analyze_promotion_strategy(self, competitor_id: str) -> Dict[str, Any]:
        """프로모션 전략 분석"""
        # 최근 프로모션 이력
        promotions = await self.storage.list(
            "competitor_promotions",
            filters={
                "competitor_id": competitor_id,
                "created_at": {"$gte": datetime.now() - timedelta(days=30)},
            },
        )

        # 프로모션 타입 분석
        promo_types = {}
        total_discount = Decimal("0")

        for promo in promotions:
            promo_type = promo.get("type", "기타")
            discount = Decimal(str(promo.get("discount_rate", 0)))

            if promo_type not in promo_types:
                promo_types[promo_type] = 0
            promo_types[promo_type] += 1
            total_discount += discount

        avg_discount = total_discount / len(promotions) if promotions else Decimal("0")

        return {
            "promotion_frequency": len(promotions),
            "promotion_types": promo_types,
            "average_discount": float(avg_discount),
            "strategy": "aggressive" if len(promotions) > 10 else "moderate",
        }

    def _estimate_free_shipping_threshold(self, portfolio: Dict[str, Any]) -> Optional[int]:
        """무료배송 기준 추정"""
        avg_prices = portfolio.get("average_price_by_category", {})
        if not avg_prices:
            return None

        # 평균 가격의 1.5배를 무료배송 기준으로 추정
        overall_avg = sum(avg_prices.values()) / len(avg_prices)
        threshold = int(overall_avg * Decimal("1.5") / 10000) * 10000

        return max(30000, threshold)  # 최소 3만원

    def _analyze_review_sentiment(self, average_rating: Optional[float]) -> str:
        """리뷰 감성 분석"""
        if not average_rating:
            return "unknown"

        if average_rating >= 4.5:
            return "very_positive"
        elif average_rating >= 4.0:
            return "positive"
        elif average_rating >= 3.5:
            return "neutral"
        elif average_rating >= 3.0:
            return "negative"
        else:
            return "very_negative"

    def _analyze_swot(
        self,
        competitor: CompetitorInfo,
        portfolio: Dict[str, Any],
        pricing_strategy: Dict[str, Any],
        customer_satisfaction: Dict[str, Any],
    ) -> Dict[str, List[str]]:
        """SWOT 분석"""
        swot = {"strengths": [], "weaknesses": [], "opportunities": [], "threats": []}

        # 강점
        if (
            customer_satisfaction["average_rating"]
            and customer_satisfaction["average_rating"] >= 4.5
        ):
            swot["strengths"].append("높은 고객 만족도")
        if portfolio["total_products"] > 100:
            swot["strengths"].append("다양한 상품 포트폴리오")
        if pricing_strategy["strategy"] == "low_price":
            swot["strengths"].append("가격 경쟁력")

        # 약점
        if customer_satisfaction["review_count"] and customer_satisfaction["review_count"] < 10:
            swot["weaknesses"].append("낮은 리뷰 수")
        if (
            pricing_strategy["strategy"] == "premium"
            and customer_satisfaction["average_rating"]
            and customer_satisfaction["average_rating"] < 4.0
        ):
            swot["weaknesses"].append("가격 대비 만족도 부족")

        # 기회
        if len(portfolio["main_categories"]) < 3:
            swot["opportunities"].append("카테고리 확장 가능")

        # 위협
        if pricing_strategy["strategy"] == "low_price":
            swot["threats"].append("가격 경쟁 심화")

        return swot

    async def _get_existing_competitors(
        self, category: str, marketplace: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """기존 경쟁사 목록 조회"""
        filters = {"category": category}
        if marketplace:
            filters["marketplace"] = marketplace

        return await self.storage.list("competitors", filters=filters)

    async def _search_current_competitors(
        self, category: str, marketplace: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """현재 활동중인 경쟁사 검색"""
        # 실제로는 마켓플레이스 API/스크래핑
        # 여기서는 시뮬레이션
        return []

    async def _analyze_new_competitor(self, competitor: Dict[str, Any]) -> Dict[str, Any]:
        """신규 경쟁사 분석"""
        return {
            "threat_level": "medium",  # 위협 수준
            "estimated_market_share": 0.01,  # 예상 시장 점유율
            "growth_potential": "high",  # 성장 가능성
        }

    async def _save_competitor(self, competitor: Dict[str, Any]):
        """경쟁사 정보 저장"""
        await self.storage.save("competitors", competitor)
