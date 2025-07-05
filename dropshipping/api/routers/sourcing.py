"""
소싱 인텔리전스 관련 API 엔드포인트
"""

from datetime import date, datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from dropshipping.api.dependencies import (
    Pagination,
    get_current_user,
    get_storage,
    rate_limiter,
)
from dropshipping.monitoring import get_logger
from dropshipping.sourcing.competitor_monitor import CompetitorMonitor
from dropshipping.sourcing.keyword_researcher import KeywordResearcher
from dropshipping.sourcing.sales_analyzer import SalesAnalyzer
from dropshipping.storage.base import BaseStorage

logger = get_logger(__name__)

router = APIRouter()


@router.get("/trending")
async def get_trending_products(
    category: Optional[str] = Query(None, description="카테고리 필터"),
    period: int = Query(7, description="분석 기간(일)"),
    limit: int = Query(20, ge=1, le=100),
    storage: BaseStorage = Depends(get_storage),
    _: None = Depends(rate_limiter),
):
    """인기 상품 분석"""
    try:
        # SalesAnalyzer 인스턴스 생성
        analyzer = SalesAnalyzer(storage)

        # 트렌드 분석
        trending = await analyzer.get_trending_products(days=period, category=category, limit=limit)

        return {"period_days": period, "category": category, "products": trending}

    except Exception as e:
        logger.error(f"인기 상품 분석 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="인기 상품을 분석할 수 없습니다",
        )


@router.get("/keywords/research")
async def research_keywords(
    seed_keyword: str = Query(..., description="시드 키워드"),
    include_related: bool = Query(True, description="연관 키워드 포함"),
    include_trends: bool = Query(True, description="트렌드 정보 포함"),
    storage: BaseStorage = Depends(get_storage),
    _: None = Depends(rate_limiter),
):
    """키워드 리서치"""
    try:
        # KeywordResearcher 인스턴스 생성
        researcher = KeywordResearcher()

        # 키워드 분석
        results = await researcher.analyze_keyword(
            seed_keyword, include_related=include_related, include_trends=include_trends
        )

        return {"seed_keyword": seed_keyword, "analysis": results}

    except Exception as e:
        logger.error(f"키워드 리서치 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="키워드를 분석할 수 없습니다"
        )


@router.get("/keywords/trending")
async def get_trending_keywords(
    category: Optional[str] = Query(None, description="카테고리 필터"),
    limit: int = Query(20, ge=1, le=100),
    storage: BaseStorage = Depends(get_storage),
    _: None = Depends(rate_limiter),
):
    """트렌드 키워드 조회"""
    try:
        # DB에서 트렌드 키워드 조회
        filters = {"is_trending": True}
        if category:
            filters["category"] = category

        keywords = await storage.list(
            "keywords", filters=filters, limit=limit, order_by=["-search_volume", "-trend_score"]
        )

        return {"category": category, "keywords": keywords}

    except Exception as e:
        logger.error(f"트렌드 키워드 조회 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="트렌드 키워드를 조회할 수 없습니다",
        )


@router.get("/competitors")
async def list_competitors(
    marketplace: Optional[str] = Query(None, description="마켓플레이스 필터"),
    category: Optional[str] = Query(None, description="카테고리 필터"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    storage: BaseStorage = Depends(get_storage),
    _: None = Depends(rate_limiter),
):
    """경쟁사 목록 조회"""
    try:
        # 페이지네이션 설정
        pagination = Pagination(page=page, page_size=page_size)

        # 필터 조건
        filters = {"is_active": True}
        if marketplace:
            filters["marketplace"] = marketplace
        if category:
            filters["category"] = category

        # 경쟁사 조회
        competitors = await storage.list(
            "competitors",
            filters=filters,
            limit=pagination.limit,
            offset=pagination.offset,
            order_by=["-sales_rank"],
        )

        # 전체 개수
        total = await storage.count("competitors", filters=filters)

        return pagination.paginate(total, competitors)

    except Exception as e:
        logger.error(f"경쟁사 목록 조회 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="경쟁사 목록을 조회할 수 없습니다",
        )


@router.get("/competitors/{competitor_id}/analysis")
async def analyze_competitor(
    competitor_id: str,
    period_days: int = Query(30, description="분석 기간(일)"),
    storage: BaseStorage = Depends(get_storage),
    _: None = Depends(rate_limiter),
):
    """경쟁사 상세 분석"""
    try:
        # 경쟁사 정보 조회
        competitor = await storage.get("competitors", competitor_id)
        if not competitor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="경쟁사를 찾을 수 없습니다"
            )

        # CompetitorMonitor 인스턴스 생성
        monitor = CompetitorMonitor(storage)

        # 경쟁사 분석
        analysis = await monitor.analyze_competitor(competitor_id, period_days=period_days)

        return {"competitor": competitor, "period_days": period_days, "analysis": analysis}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"경쟁사 분석 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="경쟁사를 분석할 수 없습니다"
        )


@router.post("/competitors")
async def add_competitor(
    competitor_data: Dict[str, Any],
    storage: BaseStorage = Depends(get_storage),
    user: dict = Depends(get_current_user),
):
    """경쟁사 추가"""
    try:
        # 경쟁사 데이터
        competitor = {
            "name": competitor_data.get("name"),
            "marketplace": competitor_data.get("marketplace"),
            "seller_id": competitor_data.get("seller_id"),
            "category": competitor_data.get("category"),
            "is_active": True,
            "created_by": user["id"],
            "created_at": datetime.utcnow().isoformat(),
        }

        # DB 저장
        created = await storage.create("competitors", competitor)

        logger.info(f"경쟁사 추가: {competitor['name']}")
        return created

    except Exception as e:
        logger.error(f"경쟁사 추가 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="경쟁사를 추가할 수 없습니다"
        )


@router.get("/opportunities")
async def find_opportunities(
    min_profit_margin: float = Query(30.0, description="최소 수익률(%)"),
    min_search_volume: int = Query(1000, description="최소 검색량"),
    max_competition: float = Query(0.7, description="최대 경쟁도(0-1)"),
    category: Optional[str] = Query(None, description="카테고리 필터"),
    limit: int = Query(20, ge=1, le=100),
    storage: BaseStorage = Depends(get_storage),
    _: None = Depends(rate_limiter),
):
    """수익 기회 발굴"""
    try:
        # 기회 분석 쿼리
        query = f"""
        SELECT p.*, k.search_volume, k.competition_score
        FROM products p
        JOIN keywords k ON p.main_keyword = k.keyword
        WHERE p.profit_margin >= {min_profit_margin}
        AND k.search_volume >= {min_search_volume}
        AND k.competition_score <= {max_competition}
        """

        if category:
            query += f" AND p.category = '{category}'"

        query += f" ORDER BY (p.profit_margin * k.search_volume) DESC LIMIT {limit}"

        # 쿼리 실행
        opportunities = await storage.query(query)

        return {
            "filters": {
                "min_profit_margin": min_profit_margin,
                "min_search_volume": min_search_volume,
                "max_competition": max_competition,
                "category": category,
            },
            "opportunities": opportunities,
        }

    except Exception as e:
        logger.error(f"기회 발굴 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="수익 기회를 분석할 수 없습니다",
        )


@router.get("/analytics/dashboard")
async def get_analytics_dashboard(
    date_from: Optional[date] = Query(None, description="시작일"),
    date_to: Optional[date] = Query(None, description="종료일"),
    storage: BaseStorage = Depends(get_storage),
    _: None = Depends(rate_limiter),
):
    """분석 대시보드 데이터"""
    try:
        # 기본 날짜 설정
        if not date_to:
            date_to = date.today()
        if not date_from:
            date_from = date_to.replace(day=1)  # 이번 달 1일

        # 대시보드 데이터 수집
        dashboard_data = {
            "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
            "summary": {
                "total_products": await storage.count("products"),
                "active_competitors": await storage.count(
                    "competitors", filters={"is_active": True}
                ),
                "trending_keywords": await storage.count("keywords", filters={"is_trending": True}),
            },
            "top_performers": [],  # TODO: 실제 구현
            "market_trends": [],  # TODO: 실제 구현
            "opportunity_score": 0,  # TODO: 실제 구현
        }

        return dashboard_data

    except Exception as e:
        logger.error(f"대시보드 데이터 조회 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="대시보드 데이터를 조회할 수 없습니다",
        )
