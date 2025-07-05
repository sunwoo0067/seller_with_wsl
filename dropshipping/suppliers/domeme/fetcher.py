"""
도매매(Domeme) 상품 수집기
BaseFetcher를 상속받아 도매매 특화 기능 구현
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

from loguru import logger

from dropshipping.suppliers.base.base_fetcher import BaseFetcher, FetchError
from dropshipping.suppliers.domeme.client import DomemeClient, DomemeAPIError
from dropshipping.transformers.domeme import DomemeTransformer


class DomemeFetcher(BaseFetcher):
    """도매매 상품 수집기"""

    def __init__(self, storage=None, api_key: Optional[str] = None):
        """
        Args:
            storage: 저장소 인스턴스
            api_key: 도매매 API 키
        """
        # 변환기 생성
        transformer = DomemeTransformer()

        # 부모 클래스 초기화
        super().__init__(supplier_id="domeme", storage=storage, transformer=transformer)

        # API 클라이언트
        self.client = DomemeClient(api_key=api_key)

        # 카테고리별 수집 설정
        self.target_categories = [
            "001",  # 패션의류
            "002",  # 패션잡화
            "003",  # 화장품/미용
            "004",  # 디지털/가전
            "005",  # 가구/인테리어
            "006",  # 식품
            "007",  # 스포츠/레저
            "008",  # 생활용품
            "009",  # 출산/육아
            "010",  # 반려동물
        ]

    def fetch_list(
        self,
        page: int = 1,
        category: Optional[str] = None,
        since: Optional[datetime] = None,
        **kwargs,
    ) -> Tuple[List[Dict[str, Any]], bool]:
        """
        상품 목록 조회

        Args:
            page: 페이지 번호
            category: 카테고리 코드
            since: 이 시점 이후 등록/수정된 상품만 조회
            **kwargs: 추가 검색 조건

        Returns:
            Tuple[상품 목록, 다음 페이지 존재 여부]
        """
        try:
            # 페이지당 100개씩 조회
            page_size = 100
            start_row = (page - 1) * page_size + 1
            end_row = page * page_size

            # 검색 파라미터 구성
            search_params = {
                "start_row": start_row,
                "end_row": end_row,
                "order_by": "modDate",  # 수정일 기준 정렬
                "sort_type": "desc",
            }

            # 카테고리 필터
            if category:
                search_params["categoryCode"] = category

            # 날짜 필터 (도매매 API가 지원하는 경우)
            if since:
                # 도매매는 직접적인 날짜 필터를 지원하지 않을 수 있음
                # 이 경우 전체를 가져와서 클라이언트에서 필터링
                logger.debug(f"날짜 필터: {since.isoformat()}")

            # 추가 검색 조건
            search_params.update(kwargs)

            # API 호출
            result = self.client.search_products(**search_params)

            # 날짜 필터링 (클라이언트 사이드)
            products = result["products"]
            if since:
                filtered_products = []
                for product in products:
                    # 등록일 또는 수정일 확인
                    mod_date_str = product.get("modDate", product.get("regDate", ""))
                    if mod_date_str:
                        try:
                            # 도매매 날짜 형식: YYYYMMDD or YYYY-MM-DD
                            if len(mod_date_str) == 8:
                                mod_date = datetime.strptime(mod_date_str, "%Y%m%d")
                            else:
                                mod_date = datetime.strptime(mod_date_str[:10], "%Y-%m-%d")

                            if mod_date >= since:
                                filtered_products.append(product)
                        except ValueError:
                            # 날짜 파싱 실패시 포함
                            filtered_products.append(product)
                    else:
                        # 날짜 정보가 없으면 포함
                        filtered_products.append(product)

                products = filtered_products

            has_next = result["has_next"]

            logger.info(f"도매매 상품 목록 조회: 페이지 {page}, {len(products)}개 상품")

            return products, has_next

        except DomemeAPIError as e:
            raise FetchError(f"도매매 API 오류: {str(e)}")
        except Exception as e:
            raise FetchError(f"상품 목록 조회 실패: {str(e)}")

    def fetch_detail(self, product_id: str) -> Dict[str, Any]:
        """
        상품 상세 정보 조회

        Args:
            product_id: 상품 번호

        Returns:
            상품 상세 정보
        """
        try:
            detail = self.client.get_product_detail(product_id)
            logger.debug(f"도매매 상품 상세 조회: {product_id}")
            return detail

        except DomemeAPIError as e:
            raise FetchError(f"도매매 API 오류: {str(e)}")
        except Exception as e:
            raise FetchError(f"상품 상세 조회 실패: {str(e)}")

    def needs_detail_fetch(self, list_item: Dict[str, Any]) -> bool:
        """
        상세 정보 조회 필요 여부

        도매매는 목록 API에서 대부분의 정보를 제공하므로
        특별한 경우가 아니면 상세 조회 불필요
        """
        # 상세 설명이나 추가 이미지가 없는 경우만 상세 조회
        has_description = bool(list_item.get("description"))
        has_add_images = any(list_item.get(f"addImg{i}") for i in range(1, 11))

        return not (has_description and has_add_images)

    def run_full_sync(self, max_pages_per_category: int = 10):
        """
        전체 동기화 실행 (모든 카테고리)

        Args:
            max_pages_per_category: 카테고리별 최대 페이지 수
        """
        logger.info("도매매 전체 동기화 시작")

        total_products = 0
        total_saved = 0

        for category in self.target_categories:
            logger.info(f"카테고리 {category} 수집 시작")

            page = 1
            category_products = 0

            while page <= max_pages_per_category:
                try:
                    # 목록 조회
                    products, has_next = self.fetch_with_retry(
                        self.fetch_list, page=page, category=category
                    )

                    if not products:
                        logger.info(f"카테고리 {category}: 더 이상 상품이 없습니다")
                        break

                    # 각 상품 처리
                    for product in products:
                        try:
                            # 원본 데이터 저장
                            record_id = self.save_raw(product)
                            if record_id:
                                total_saved += 1

                                # 변환 및 처리
                                if self.transformer:
                                    self.process_product(record_id, product)

                            category_products += 1
                            total_products += 1

                        except Exception as e:
                            logger.error(f"상품 처리 실패: {str(e)}")
                            self._stats["errors"] += 1

                    # 다음 페이지
                    if not has_next:
                        break

                    page += 1

                except Exception as e:
                    logger.error(f"카테고리 {category} 페이지 {page} 수집 실패: {str(e)}")
                    break

            logger.info(f"카테고리 {category} 수집 완료: {category_products}개 상품")

        logger.info(f"도매매 전체 동기화 완료: 총 {total_products}개 조회, {total_saved}개 저장")

    def run_daily_sync(self):
        """일일 증분 동기화 (최근 24시간)"""
        since = datetime.now() - timedelta(days=1)
        logger.info(f"도매매 일일 동기화 시작: {since.isoformat()} 이후 상품")

        # 모든 카테고리에 대해 증분 동기화
        for category in self.target_categories:
            logger.info(f"카테고리 {category} 증분 동기화")

            try:
                # 증분 동기화는 수정일 기준으로 최대 20페이지만
                self.run_incremental(since=since, max_pages=20, category=category)
            except Exception as e:
                logger.error(f"카테고리 {category} 동기화 실패: {str(e)}")

        logger.info("도매매 일일 동기화 완료")

    def run_incremental(
        self,
        since: Optional[datetime] = None,
        max_pages: int = 100,
        category: Optional[str] = None,
    ):
        """
        증분 동기화 실행 (카테고리별)

        Args:
            since: 이 시점 이후의 데이터만 수집
            max_pages: 최대 페이지 수
            category: 특정 카테고리만 수집
        """
        # 카테고리가 지정되지 않으면 전체 카테고리 대상
        categories = [category] if category else self.target_categories

        for cat in categories:
            logger.info(f"[{self.supplier_id}] 카테고리 {cat} 증분 동기화 시작")

            page = 1
            total_products = 0

            while page <= max_pages:
                try:
                    # 목록 조회
                    products, has_next = self.fetch_with_retry(
                        self.fetch_list, page=page, category=cat, since=since
                    )

                    if not products:
                        logger.info(f"카테고리 {cat}: 더 이상 상품이 없습니다 (page={page})")
                        break

                    self._stats["fetched"] += len(products)

                    # 각 상품 처리
                    for product in products:
                        try:
                            # 상세 정보가 필요한 경우 조회
                            if self.needs_detail_fetch(product):
                                product_id = self.extract_product_id(product)
                                detail = self.fetch_with_retry(self.fetch_detail, product_id)
                                product = self.merge_detail(product, detail)

                            # 원본 데이터 저장
                            record_id = self.save_raw(product)

                            # 변환 및 후처리
                            if record_id and self.transformer:
                                self.process_product(record_id, product)

                            total_products += 1

                        except Exception as e:
                            logger.error(f"상품 처리 실패: {str(e)}")
                            self._stats["errors"] += 1

                    # 다음 페이지 확인
                    if not has_next:
                        logger.info(f"카테고리 {cat}: 마지막 페이지입니다")
                        break

                    page += 1

                except FetchError as e:
                    logger.error(f"카테고리 {cat} 페이지 {page} 수집 실패: {str(e)}")
                    self._stats["errors"] += 1
                    break
                except Exception as e:
                    logger.error(f"예기치 않은 오류: {str(e)}")
                    self._stats["errors"] += 1
                    break

            logger.info(f"카테고리 {cat} 동기화 완료: {total_products}개 처리")

        # 통계 출력
        logger.info(
            f"[{self.supplier_id}] 동기화 완료: "
            f"수집={self._stats['fetched']}, "
            f"저장={self._stats['saved']}, "
            f"중복={self._stats['duplicates']}, "
            f"오류={self._stats['errors']}"
        )
