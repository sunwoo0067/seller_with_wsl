"""
젠트레이드 공급사 Fetcher
FTP를 통한 XML 파일 다운로드 및 파싱
"""

import os
import xml.etree.ElementTree as ET
from datetime import datetime
from ftplib import FTP
from typing import Any, Dict, List, Optional
import tempfile
import gzip
from io import BytesIO

from dropshipping.suppliers.base.base_fetcher import BaseFetcher
from dropshipping.monitoring.logger import get_logger

logger = get_logger(__name__)


class ZentradeFetcher(BaseFetcher):
    """젠트레이드 FTP/XML 기반 상품 수집기"""

    def __init__(
        self, storage, supplier_name, ftp_host, ftp_user, ftp_pass, ftp_path="/", **kwargs
    ):
        super().__init__(storage, supplier_name)
        self.ftp_host = ftp_host
        self.ftp_user = ftp_user
        self.ftp_pass = ftp_pass
        self.ftp_path = ftp_path
        self.timeout = kwargs.get("timeout", 30)
        self.encoding = kwargs.get("encoding", "utf-8")

    def _connect_ftp(self) -> FTP:
        """FTP 서버 연결"""
        try:
            ftp = FTP()
            ftp.connect(self.ftp_host, timeout=self.timeout)
            ftp.login(self.ftp_user, self.ftp_pass)
            ftp.encoding = self.encoding

            # 작업 디렉토리 변경
            if self.ftp_path and self.ftp_path != "/":
                ftp.cwd(self.ftp_path)

            logger.info(f"FTP 연결 성공: {self.ftp_host}")
            return ftp

        except Exception as e:
            logger.error(f"FTP 연결 실패: {str(e)}")
            raise

    def _download_file(self, ftp: FTP, filename: str) -> bytes:
        """FTP에서 파일 다운로드"""
        try:
            buffer = BytesIO()
            ftp.retrbinary(f"RETR {filename}", buffer.write)
            buffer.seek(0)

            # gzip 압축 파일인 경우 압축 해제
            if filename.endswith(".gz"):
                with gzip.open(buffer, "rb") as gz:
                    return gz.read()
            else:
                return buffer.read()

        except Exception as e:
            logger.error(f"파일 다운로드 실패 [{filename}]: {str(e)}")
            raise

    def _parse_xml(self, xml_data: bytes) -> List[Dict[str, Any]]:
        """XML 데이터 파싱"""
        try:
            # XML 파싱
            root = ET.fromstring(xml_data.decode(self.encoding))
            products = []

            # 젠트레이드 XML 구조에 맞게 파싱
            # 일반적인 구조: <products><product>...</product></products>
            for product_elem in root.findall(".//product"):
                product = self._parse_product_element(product_elem)
                if product:
                    products.append(product)

            return products

        except Exception as e:
            logger.error(f"XML 파싱 실패: {str(e)}")
            raise

    def _parse_product_element(self, elem: ET.Element) -> Dict[str, Any]:
        """단일 상품 요소 파싱"""
        try:
            # 기본 정보 추출
            product = {
                "id": self._get_text(elem, "product_id"),
                "name": self._get_text(elem, "product_name"),
                "category": self._get_text(elem, "category"),
                "brand": self._get_text(elem, "brand"),
                "model": self._get_text(elem, "model"),
                "price": self._get_float(elem, "price"),
                "stock": self._get_int(elem, "stock"),
                "description": self._get_text(elem, "description"),
                "status": self._get_text(elem, "status", "active"),
                "created_at": self._get_text(elem, "created_at"),
                "updated_at": self._get_text(elem, "updated_at"),
            }

            # 이미지 정보
            images = []
            for img_elem in elem.findall(".//image"):
                url = img_elem.text or img_elem.get("url", "")
                if url:
                    images.append(url)
            product["images"] = images

            # 옵션 정보
            options = []
            for opt_elem in elem.findall(".//option"):
                option = {
                    "name": opt_elem.get("name", ""),
                    "value": opt_elem.get("value", ""),
                    "price": self._get_float(opt_elem, "price", 0),
                    "stock": self._get_int(opt_elem, "stock", 0),
                }
                if option["name"]:
                    options.append(option)
            product["options"] = options

            # 배송 정보
            shipping_elem = elem.find(".//shipping")
            if shipping_elem is not None:
                product["shipping"] = {
                    "method": self._get_text(shipping_elem, "method"),
                    "fee": self._get_float(shipping_elem, "fee", 0),
                    "free_condition": self._get_float(shipping_elem, "free_condition", 0),
                }

            return product

        except Exception as e:
            logger.error(f"상품 파싱 실패: {str(e)}")
            return None

    def _get_text(self, parent: ET.Element, tag: str, default: str = "") -> str:
        """XML 요소에서 텍스트 추출"""
        elem = parent.find(tag)
        if elem is not None and elem.text:
            return elem.text.strip()
        return default

    def _get_int(self, parent: ET.Element, tag: str, default: int = 0) -> int:
        """XML 요소에서 정수 추출"""
        text = self._get_text(parent, tag)
        try:
            return int(text) if text else default
        except ValueError:
            return default

    def _get_float(self, parent: ET.Element, tag: str, default: float = 0.0) -> float:
        """XML 요소에서 실수 추출"""
        text = self._get_text(parent, tag)
        try:
            return float(text) if text else default
        except ValueError:
            return default

    def fetch_list(self, page: int = 1) -> List[Dict[str, Any]]:
        """상품 목록 조회

        젠트레이드는 전체 상품을 XML 파일로 제공하므로
        페이지 개념이 없고 전체 파일을 다운로드하여 처리
        """
        ftp = None
        try:
            # FTP 연결
            ftp = self._connect_ftp()

            # XML 파일 목록 조회
            files = []
            ftp.retrlines("LIST", lambda x: files.append(x))

            # 상품 XML 파일 찾기 (예: products.xml, products_20240101.xml 등)
            xml_files = [f for f in files if "product" in f.lower() and (".xml" in f or ".gz" in f)]

            if not xml_files:
                logger.warning("상품 XML 파일을 찾을 수 없습니다")
                return []

            # 가장 최신 파일 선택 (보통 날짜가 포함된 경우)
            latest_file = sorted(xml_files)[-1]
            filename = latest_file.split()[-1]  # 파일명만 추출

            logger.info(f"XML 파일 다운로드 중: {filename}")

            # 파일 다운로드
            xml_data = self._download_file(ftp, filename)

            # XML 파싱
            products = self._parse_xml(xml_data)

            logger.info(f"총 {len(products)}개 상품 조회 완료")
            return products

        except Exception as e:
            logger.error(f"상품 목록 조회 실패: {str(e)}")
            return []

        finally:
            if ftp:
                try:
                    ftp.quit()
                except:
                    pass

    def fetch_detail(self, item_id: str) -> Dict[str, Any]:
        """상품 상세 조회

        젠트레이드는 전체 데이터를 한 번에 제공하므로
        별도의 상세 API가 없음. 전체 데이터에서 필터링
        """
        # 전체 목록에서 해당 상품 찾기
        products = self.fetch_list()

        for product in products:
            if product.get("id") == item_id:
                return product

        logger.warning(f"상품을 찾을 수 없습니다: {item_id}")
        return {}

    def fetch_categories(self) -> List[Dict[str, Any]]:
        """카테고리 목록 조회"""
        ftp = None
        try:
            ftp = self._connect_ftp()

            # 카테고리 XML 파일 찾기
            files = []
            ftp.retrlines("LIST", lambda x: files.append(x))

            category_files = [f for f in files if "category" in f.lower() and ".xml" in f]

            if not category_files:
                logger.warning("카테고리 XML 파일을 찾을 수 없습니다")
                return []

            filename = category_files[0].split()[-1]

            # 파일 다운로드 및 파싱
            xml_data = self._download_file(ftp, filename)
            root = ET.fromstring(xml_data.decode(self.encoding))

            categories = []
            for cat_elem in root.findall(".//category"):
                category = {
                    "id": cat_elem.get("id", ""),
                    "name": cat_elem.get("name", ""),
                    "parent_id": cat_elem.get("parent_id", ""),
                    "level": int(cat_elem.get("level", "1")),
                }
                categories.append(category)

            return categories

        except Exception as e:
            logger.error(f"카테고리 조회 실패: {str(e)}")
            return []

        finally:
            if ftp:
                try:
                    ftp.quit()
                except:
                    pass
