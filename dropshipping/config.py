"""
설정 관리 모듈
환경 변수를 읽어 Pydantic 모델로 변환하여 타입 안전성 보장
"""

from functools import lru_cache
from pathlib import Path
from decimal import Decimal
from typing import Dict, Literal, Optional

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# .env 파일 로드 (명시적 경로 및 오버라이드)
load_dotenv(dotenv_path=".env", override=True)


class SupabaseConfig(BaseSettings):
    """Supabase 설정"""

    url: str = Field(...)
    service_role_key: str = Field(...)

    model_config = SettingsConfigDict(env_prefix="SUPABASE_")


class DomemeConfig(BaseSettings):
    """도매매 API 설정"""

    api_key: str = Field(...)
    api_url: str = Field(default="https://openapi.domeggook.com")

    model_config = SettingsConfigDict(env_prefix="DOMEME_")


class OwnerclanConfig(BaseSettings):
    """오너클랜 API 설정"""

    username: str = Field(...)
    password: str = Field(...)
    api_url: str = Field(default="https://api.ownerclan.com/v1/graphql")

    model_config = SettingsConfigDict(env_prefix="OWNERCLAN_")


class SmartstoreConfig(BaseSettings):
    """스마트스토어 설정"""

    client_id: str = Field(...)
    client_secret: str = Field(...)
    access_token: str = Field(...)
    channel_id: str = Field(...)
    outbound_location_id: str = Field(...)
    return_address: str = Field(...)
    return_detail_address: str = Field(...)
    return_zip_code: str = Field(...)
    return_tel: str = Field(...)
    base_url: str = "https://api.commerce.naver.com/external"
    category_mapping: Dict[str, str] = {
        "전자기기/이어폰": "50000190",
        "의류/여성의류": "50000167",
        "애완용품": "50000197",
    }

    model_config = SettingsConfigDict(env_prefix="SMARTSTORE_")


class GmarketUploaderConfig(BaseSettings):
    """G마켓/옥션 엑셀 업로더 설정"""

    output_dir: str = Field("./excel_output")
    template_path: Optional[str] = Field(None)
    seller_code: str = Field("")
    shipping_address: str = Field("")
    return_address: str = Field("")

    category_mapping: Dict[str, str] = {
        "전자기기/이어폰": "200001541",
        "의류/여성의류": "200000564",
        "애완용품": "200002468",
    }

    column_mapping: Dict[str, str] = {
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
        "바코드": "Z",
    }

    model_config = SettingsConfigDict(env_prefix="GMARKET_")


class ElevenstConfig(BaseSettings):
    """11번가 업로더 설정"""

    api_key: str = Field(...)
    seller_id: str = Field(...)
    test_mode: bool = Field(False)
    base_url: str = "https://api.11st.co.kr/rest"
    delivery_company_code: str = "00034"  # CJ대한통운
    delivery_cost: int = 2500
    free_shipping_threshold: int = 30000
    exchange_delivery_cost: int = 2500
    return_delivery_cost: int = 2500
    category_mapping: Dict[str, str] = {
        "전자기기/이어폰": "159966",
        "의류/여성의류": "103755",
        "애완용품": "201775",
    }

    model_config = SettingsConfigDict(env_prefix="ELEVENST_")


class CoupangConfig(BaseSettings):
    """쿠팡 API 설정"""

    access_key: str = Field(...)
    secret_key: str = Field(...)
    vendor_id: str = Field(...)
    test_mode: bool = Field(default=False)

    # Category Mapping (from JSON string in env var)
    category_mapping: Dict[str, str] = Field(
        default_factory=lambda: {
            "전자기기/이어폰": "1001",
            "의류/여성의류": "1002",
            "애완용품": "1003",
        },
    )

    # Default product values
    default_brand: str = Field(default="기타")
    sale_ended_at: str = Field(default="2099-12-31 23:59:59")
    default_shipping_fee: int = Field(default=2500)

    # Delivery settings
    delivery_company_code: str = Field(default="KGB")  # 로젠택배
    free_ship_over_amount: int = Field(default=30000)
    outbound_shipping_place_code: str = Field(default="74010")

    # Return settings
    return_center_code: str = Field(default="1000274592")
    return_charge_name: str = Field(default="대표이름")
    contact_number: str = Field(default="02-1234-5678")
    return_zip_code: str = Field(default="12345")
    return_address: str = Field(default="서울특별시 강남구")
    return_address_detail: str = Field(default="역삼동 123-45")

    # After-service settings
    after_service_information: str = Field(default="A/S 안내 1577-1234")
    after_service_contact_number: str = Field(default="1577-1234")

    # Item settings
    sale_price_discount_rate: Decimal = Field(default=Decimal("0.9"))  # 10% 할인
    maximum_buy_count: int = Field(default=10)
    maximum_buy_for_person: int = Field(default=5)
    outbound_shipping_time_day: int = Field(default=2)  # 출고 소요일

    model_config = SettingsConfigDict(env_prefix="COUPANG_")


class AIConfig(BaseSettings):
    """AI 모델 설정"""

    gemini_api_key: Optional[str] = Field(None)
    ollama_host: str = Field(default="http://localhost:11434")

    model_config = SettingsConfigDict(env_prefix="")


class MonitoringConfig(BaseSettings):
    """모니터링 설정"""

    slack_webhook_url: Optional[str] = Field(None)

    model_config = SettingsConfigDict(env_prefix="")


class Settings(BaseSettings):
    """전체 애플리케이션 설정"""

    # 환경
    env: Literal["development", "staging", "production", "test"] = Field(
        default="development", env="ENV"
    )
    debug: bool = Field(default=False, env="DEBUG")
    dry_run: bool = Field(default=False, env="DRY_RUN")

    # 로깅
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_file: Optional[Path] = Field(default=None, env="LOG_FILE")

    # 스케줄러
    scheduler_enabled: bool = Field(default=False, env="SCHEDULER_ENABLED")
    scheduler_timezone: str = Field(default="Asia/Seoul", env="SCHEDULER_TIMEZONE")

    # 캐시
    cache_enabled: bool = Field(default=True, env="CACHE_ENABLED")
    cache_ttl: int = Field(default=3600, env="CACHE_TTL")

    # 파일 경로
    local_data_path: Path = Field(default=Path("./data"), env="LOCAL_DATA_PATH")
    local_upload_path: Path = Field(default=Path("./uploads"), env="LOCAL_UPLOAD_PATH")

    # 하위 설정 (선택적)
    _supabase: Optional[SupabaseConfig] = None
    _domeme: Optional[DomemeConfig] = None
    _ownerclan: Optional[OwnerclanConfig] = None
    _coupang: Optional[CoupangConfig] = None
    _elevenst: Optional[ElevenstConfig] = None
    _smartstore: Optional[SmartstoreConfig] = None
    _gmarket: Optional[GmarketUploaderConfig] = None
    _ai: Optional[AIConfig] = None
    _monitoring: Optional[MonitoringConfig] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("log_file", mode="before")
    @classmethod
    def create_log_path(cls, v):
        if v:
            path = Path(v)
            path.parent.mkdir(parents=True, exist_ok=True)
            return path
        return v

    @field_validator("local_data_path", "local_upload_path", mode="before")
    @classmethod
    def create_paths(cls, v):
        path = Path(v)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def supabase(self) -> Optional[SupabaseConfig]:
        """Supabase 설정 (lazy loading)"""
        if self._supabase is None:
            try:
                self._supabase = SupabaseConfig()
            except:
                pass
        return self._supabase

    @property
    def domeme(self) -> Optional[DomemeConfig]:
        """도매매 설정 (lazy loading)"""
        if self._domeme is None:
            try:
                self._domeme = DomemeConfig()
            except:
                pass
        return self._domeme

    @property
    def ownerclan(self) -> Optional[OwnerclanConfig]:
        """오너클랜 설정 (lazy loading)"""
        if self._ownerclan is None:
            try:
                self._ownerclan = OwnerclanConfig()
            except:
                pass
        return self._ownerclan

    @property
    def coupang(self) -> Optional[CoupangConfig]:
        """쿠팡 설정 (lazy loading)"""
        if self._coupang is None:
            try:
                self._coupang = CoupangConfig()
            except:
                pass
        return self._coupang

    @property
    def elevenst(self) -> Optional[ElevenstConfig]:
        """11번가 설정 (lazy loading)"""
        if self._elevenst is None:
            try:
                self._elevenst = ElevenstConfig()
            except:
                pass
        return self._elevenst

    @property
    def smartstore(self) -> Optional[SmartstoreConfig]:
        """스마트스토어 설정 (lazy loading)"""
        if self._smartstore is None:
            try:
                self._smartstore = SmartstoreConfig()
            except:
                pass
        return self._smartstore

    @property
    def gmarket(self) -> Optional[GmarketUploaderConfig]:
        """G마켓/옥션 엑셀 업로더 설정 (lazy loading)"""
        if self._gmarket is None:
            try:
                self._gmarket = GmarketUploaderConfig()
            except:
                pass
        return self._gmarket

    @property
    def ai(self) -> AIConfig:
        """AI 설정"""
        if self._ai is None:
            self._ai = AIConfig()
        return self._ai

    @property
    def monitoring(self) -> MonitoringConfig:
        """모니터링 설정"""
        if self._monitoring is None:
            self._monitoring = MonitoringConfig()
        return self._monitoring

    def is_production(self) -> bool:
        """프로덕션 환경 여부"""
        return self.env == "production"

    def is_development(self) -> bool:
        """개발 환경 여부"""
        return self.env == "development"


@lru_cache()
def get_settings() -> Settings:
    """설정 싱글톤 인스턴스 반환"""
    return Settings()


# 전역 설정 인스턴스
settings = get_settings()
