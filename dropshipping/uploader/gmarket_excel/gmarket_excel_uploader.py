"""
G마켓/옥션 Excel 업로더
ESM Plus를 통한 Excel 대량 업로드
"""

import os
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

from loguru import logger

from dropshipping.models.product import StandardProduct
from dropshipping.uploader.base import BaseUploader, MarketplaceType, UploadStatus


class GmarketExcelUploader(BaseUploader):
    """G마켓/옥션 Excel 업로더"""
    
    def __init__(self, storage, config: Optional[Dict[str, Any]] = None):
        """
        초기화
        
        Args:
            storage: 저장소 인스턴스
            config: Excel 업로더 설정
                - output_dir: Excel 파일 저장 경로
                - template_path: 템플릿 파일 경로
                - marketplace: gmarket 또는 auction
                - seller_code: 판매자 코드
        """
        marketplace = MarketplaceType.GMARKET if config.get("marketplace") == "gmarket" else MarketplaceType.AUCTION
        super().__init__(marketplace, storage, config)
        
        # 설정
        self.output_dir = Path(self.config.get("output_dir", "./excel_output"))
        self.output_dir.mkdir(exist_ok=True)
        
        self.template_path = self.config.get("template_path")
        self.seller_code = self.config.get("seller_code", "")
        
        # 카테고리 매핑
        self.category_mapping = {
            "전자기기/이어폰": "200001541",  # 이어폰/헤드폰
            "의류/여성의류": "200000564",   # 여성의류
            "애완용품": "200002468",       # 반려동물용품
            # 실제로는 더 많은 매핑 필요
        }
        
        # Excel 컬럼 매핑
        self.column_mapping = {
            "상품명": "B",
            "판매가": "C",
            "재고수량": "D",
            "카테고리코드": "E",
            "브랜드": "F",
            "제조사": "G",
            "원산지": "H",
            "상품상태": "I",
            "배송비유형": "J",
            "배송비": "K",
            "반품배송비": "L",
            "교환배송비": "M",
            "출고지주소": "N",
            "반품지주소": "O",
            "상품이미지1": "P",
            "상품이미지2": "Q",
            "상품이미지3": "R",
            "상품상세설명": "S",
            "옵션사용여부": "T",
            "옵션명": "U",
            "옵션값": "V",
            "옵션가격": "W",
            "옵션재고": "X",
            "판매자상품코드": "Y",
            "바코드": "Z"
        }
    
    async def validate_product(self, product: StandardProduct) -> Tuple[bool, Optional[str]]:
        """상품 검증"""
        errors = []
        
        # 필수 필드 검증
        if not product.name:
            errors.append("상품명 누락")
        elif len(product.name) > 100:
            errors.append("상품명이 너무 깁니다 (최대 100자)")
        
        if not product.price or product.price < 300:
            errors.append("판매가격이 너무 낮습니다 (최소 300원)")
        
        # 카테고리 확인
        if product.category_name not in self.category_mapping:
            errors.append(f"지원하지 않는 카테고리: {product.category_name}")
        
        # 이미지 URL 길이 확인
        for img in product.images:
            if len(str(img.url)) > 500:
                errors.append("이미지 URL이 너무 깁니다 (최대 500자)")
        
        if errors:
            return False, "; ".join(errors)
        
        return True, None
    
    async def transform_product(self, product: StandardProduct) -> Dict[str, Any]:
        """상품 데이터 변환 (Excel 행 데이터)"""
        
        # 기본 상품 정보
        excel_data = {
            "상품명": product.name[:100],
            "판매가": int(product.price),
            "재고수량": product.stock,
            "카테고리코드": self.category_mapping.get(product.category_name, ""),
            "브랜드": product.brand or "기타",
            "제조사": product.attributes.get("manufacturer", "제조사"),
            "원산지": "한국",
            "상품상태": "신상품",
            "배송비유형": "조건부무료",
            "배송비": 2500,
            "반품배송비": 2500,
            "교환배송비": 5000,
            "출고지주소": self.config.get("shipping_address", "서울특별시 강남구"),
            "반품지주소": self.config.get("return_address", "서울특별시 강남구"),
            "판매자상품코드": product.id,
            "바코드": product.barcode or ""
        }
        
        # 이미지 URL
        for i, img in enumerate(product.images[:3]):  # 최대 3개
            excel_data[f"상품이미지{i+1}"] = str(img.url)
        
        # 상세 설명 (HTML 태그 포함)
        excel_data["상품상세설명"] = self._create_detail_html(product)
        
        # 옵션 정보
        if product.variants:
            excel_data["옵션사용여부"] = "Y"
            excel_data["옵션명"] = product.variants[0].name if product.variants else ""
            
            # 옵션값은 콤마로 구분
            option_values = []
            option_prices = []
            option_stocks = []
            
            for variant in product.variants:
                option_values.append(variant.option_value)
                option_prices.append("0")  # 추가금 없음
                option_stocks.append(str(variant.stock))
            
            excel_data["옵션값"] = ",".join(option_values)
            excel_data["옵션가격"] = ",".join(option_prices)
            excel_data["옵션재고"] = ",".join(option_stocks)
        else:
            excel_data["옵션사용여부"] = "N"
            excel_data["옵션명"] = ""
            excel_data["옵션값"] = ""
            excel_data["옵션가격"] = ""
            excel_data["옵션재고"] = ""
        
        return excel_data
    
    def _create_detail_html(self, product: StandardProduct) -> str:
        """상세 설명 HTML 생성"""
        marketplace_name = "G마켓" if self.marketplace == MarketplaceType.GMARKET else "옥션"
        
        html = f"""
        <div style="width: 860px; margin: 0 auto; font-family: 'Malgun Gothic', sans-serif;">
            <div style="text-align: center; padding: 30px 0;">
                <h1 style="font-size: 28px; color: #333;">{product.name}</h1>
            </div>
            
            <div style="background: #f8f8f8; padding: 20px; margin: 20px 0;">
                <h2 style="font-size: 20px; color: #e53935; margin-bottom: 15px;">
                    {marketplace_name} 공식 판매점
                </h2>
                <p style="line-height: 1.8;">
                    {product.description or '고품질의 상품을 합리적인 가격에 제공합니다.'}
                </p>
            </div>
            
            <div style="margin: 30px 0;">
                <h3 style="font-size: 18px; border-bottom: 2px solid #333; padding-bottom: 10px;">
                    상품 정보
                </h3>
                <table style="width: 100%; margin-top: 15px; border-collapse: collapse;">
                    <tr>
                        <td style="width: 150px; padding: 10px; background: #f5f5f5; border: 1px solid #ddd;">
                            브랜드
                        </td>
                        <td style="padding: 10px; border: 1px solid #ddd;">
                            {product.brand or '기타'}
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; background: #f5f5f5; border: 1px solid #ddd;">
                            제조사
                        </td>
                        <td style="padding: 10px; border: 1px solid #ddd;">
                            {product.attributes.get('manufacturer', '제조사')}
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; background: #f5f5f5; border: 1px solid #ddd;">
                            원산지
                        </td>
                        <td style="padding: 10px; border: 1px solid #ddd;">
                            한국
                        </td>
                    </tr>
                </table>
            </div>
            
            <div style="margin: 30px 0;">
                <h3 style="font-size: 18px; border-bottom: 2px solid #333; padding-bottom: 10px;">
                    배송 정보
                </h3>
                <ul style="line-height: 2; margin-top: 15px;">
                    <li>배송비: 2,500원 (3만원 이상 구매 시 무료)</li>
                    <li>배송기간: 평균 2-3일 (주말/공휴일 제외)</li>
                    <li>배송업체: CJ대한통운</li>
                </ul>
            </div>
            
            <div style="background: #fff3cd; padding: 20px; margin: 30px 0; border: 1px solid #ffeaa7;">
                <h3 style="font-size: 18px; color: #856404; margin-bottom: 10px;">
                    교환/반품 안내
                </h3>
                <ul style="line-height: 1.8; color: #856404;">
                    <li>수령 후 7일 이내 교환/반품 가능</li>
                    <li>단순변심 시 왕복배송비 구매자 부담</li>
                    <li>상품하자 시 판매자 부담</li>
                </ul>
            </div>
        </div>
        """
        return html
    
    async def upload_single(self, product_data: Dict[str, Any]) -> Dict[str, Any]:
        """단일 상품은 지원하지 않음"""
        return {
            "success": False,
            "error": "Excel 업로더는 배치 업로드만 지원합니다"
        }
    
    async def update_single(
        self,
        marketplace_product_id: str,
        product_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """단일 상품 수정은 지원하지 않음"""
        return {
            "success": False,
            "error": "Excel 업로더는 배치 업로드만 지원합니다"
        }
    
    async def check_product_status(self, marketplace_product_id: str) -> Dict[str, Any]:
        """상품 상태 확인은 지원하지 않음"""
        return {
            "success": False,
            "error": "Excel 업로더는 상태 확인을 지원하지 않습니다"
        }
    
    async def upload_batch(
        self,
        products: List[StandardProduct],
        update_existing: bool = True,
        max_concurrent: int = 5
    ) -> List[Dict[str, Any]]:
        """배치 업로드 (Excel 파일 생성)"""
        
        logger.info(f"{len(products)}개 상품 Excel 파일 생성 시작")
        
        results = []
        excel_rows = []
        
        # 각 상품 검증 및 변환
        for product in products:
            result = {
                "product_id": product.id,
                "status": UploadStatus.PENDING,
                "marketplace": self.marketplace.value,
                "errors": []
            }
            
            try:
                # 검증
                is_valid, error_msg = await self.validate_product(product)
                if not is_valid:
                    result["status"] = UploadStatus.FAILED
                    result["errors"].append(error_msg)
                    self.stats["failed"] += 1
                else:
                    # 변환
                    excel_data = await self.transform_product(product)
                    excel_rows.append(excel_data)
                    result["status"] = UploadStatus.SUCCESS
                    self.stats["uploaded"] += 1
                
            except Exception as e:
                logger.error(f"상품 처리 오류: {product.id} - {str(e)}")
                result["status"] = UploadStatus.FAILED
                result["errors"].append(str(e))
                self.stats["failed"] += 1
            
            results.append(result)
        
        # Excel 파일 생성
        if excel_rows:
            try:
                filename = await self._create_excel_file(excel_rows)
                logger.info(f"Excel 파일 생성 완료: {filename}")
                
                # 모든 성공 결과에 파일명 추가
                for result in results:
                    if result["status"] == UploadStatus.SUCCESS:
                        result["excel_file"] = filename
                        
            except Exception as e:
                logger.error(f"Excel 파일 생성 오류: {str(e)}")
                # 모든 결과를 실패로 변경
                for result in results:
                    if result["status"] == UploadStatus.SUCCESS:
                        result["status"] = UploadStatus.FAILED
                        result["errors"].append(f"Excel 파일 생성 실패: {str(e)}")
        
        return results
    
    async def _create_excel_file(self, rows: List[Dict[str, Any]]) -> str:
        """Excel 파일 생성"""
        
        # DataFrame 생성
        df = pd.DataFrame(rows)
        
        # 파일명 생성
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        marketplace_name = "gmarket" if self.marketplace == MarketplaceType.GMARKET else "auction"
        filename = f"{marketplace_name}_upload_{timestamp}.xlsx"
        filepath = self.output_dir / filename
        
        # Excel Writer 생성
        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            # 데이터 쓰기
            df.to_excel(writer, sheet_name='상품등록', index=False)
            
            # 워크시트 가져오기
            worksheet = writer.sheets['상품등록']
            
            # 스타일 적용
            await self._apply_excel_styles(worksheet, len(rows))
        
        return filename
    
    async def _apply_excel_styles(self, worksheet, row_count: int):
        """Excel 스타일 적용"""
        
        # 헤더 스타일
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        header_alignment = Alignment(horizontal="center", vertical="center")
        
        # 헤더 행 스타일 적용
        for cell in worksheet[1]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment
        
        # 컬럼 너비 조정
        column_widths = {
            'A': 10,   # 번호
            'B': 50,   # 상품명
            'C': 15,   # 판매가
            'D': 10,   # 재고수량
            'E': 15,   # 카테고리코드
            'F': 20,   # 브랜드
            'G': 20,   # 제조사
            'H': 10,   # 원산지
            'I': 10,   # 상품상태
            'J': 15,   # 배송비유형
            'K': 10,   # 배송비
            'L': 10,   # 반품배송비
            'M': 10,   # 교환배송비
            'N': 30,   # 출고지주소
            'O': 30,   # 반품지주소
            'P': 50,   # 상품이미지1
            'Q': 50,   # 상품이미지2
            'R': 50,   # 상품이미지3
            'S': 100,  # 상품상세설명
            'T': 15,   # 옵션사용여부
            'U': 20,   # 옵션명
            'V': 50,   # 옵션값
            'W': 30,   # 옵션가격
            'X': 30,   # 옵션재고
            'Y': 20,   # 판매자상품코드
            'Z': 20    # 바코드
        }
        
        for col, width in column_widths.items():
            worksheet.column_dimensions[col].width = width
        
        # 행 높이 조정
        worksheet.row_dimensions[1].height = 30
        
        # 데이터 행 스타일
        for row in range(2, row_count + 2):
            worksheet.row_dimensions[row].height = 20
            
            # 가격 컬럼 숫자 서식
            worksheet[f'C{row}'].number_format = '#,##0'
            worksheet[f'K{row}'].number_format = '#,##0'
            worksheet[f'L{row}'].number_format = '#,##0'
            worksheet[f'M{row}'].number_format = '#,##0'