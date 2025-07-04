# 📦 도매꾹/도매매 API 명세서 (Domeggook / Domeme)

---

## 📎 참고 URL (최신 버전 기준)

- 상품 리스트: [https://openapi.domeggook.com/main/reference/detail?api\_no=73&version\_no=419&scope\_code=SCP\_OPEN](https://openapi.domeggook.com/main/reference/detail?api_no=73\&version_no=419\&scope_code=SCP_OPEN)
- 상품 상세: [https://openapi.domeggook.com/main/reference/detail?api\_no=319&version\_no=399&scope\_code=SCP\_OPEN](https://openapi.domeggook.com/main/reference/detail?api_no=319\&version_no=399\&scope_code=SCP_OPEN)
- 재고/가격: [https://openapi.domeggook.com/main/reference/detail?api\_no=19&version\_no=213&scope\_code=SCP\_OPEN](https://openapi.domeggook.com/main/reference/detail?api_no=19\&version_no=213\&scope_code=SCP_OPEN)
- 카테고리: [https://openapi.domeggook.com/main/reference/detail?api\_no=68&version\_no=384&scope\_code=SCP\_OPEN](https://openapi.domeggook.com/main/reference/detail?api_no=68\&version_no=384\&scope_code=SCP_OPEN)
- 오류/가이드: [https://openapi.domeggook.com/main/guide/stderr](https://openapi.domeggook.com/main/guide/stderr)



---

## 🔗 기본 정보

- **API 명**: 도매꾹/도매매 상품/카테고리 API
- **공급사명**: 도매꾹 (Domeggook) / 도매매 (Domeme)
- **API 버전**: 상품 리스트 v4.1 / 상품 상세 v4.5 / 카테고리 목록 v1.0 / 카테고리 정보 v2.0
- **API 방식**: REST (HTTP GET)
- **요청/응답 형식**: XML
- **인증 방식**: API Key (Query String)
- **주의사항**: `market` 파라미터를 `supply`로 지정해야 도매매 전용으로 작동함

---

## 🧾 공통 요청 파라미터

| 번호  | 필드       | 타입     | 필수  | 설명                             |
| --- | -------- | ------ | --- | ------------------------------ |
| 1   | `ver`    | string | Y   | API 버전 (예: `4.5`, 카테고리는 `2.0`) |
| 4   | `market` | string | Y   | 서비스 코드: `supply` (도매매용)        |
| ... | ...      | ...    | ... | ... 기타 항목은 각 API 문서 참고         |

> **주의:** 모든 API는 도매꾹 도메인을 사용하지만, `market=supply` 로 설정 시 도매매 전용 필터링 적용됨

---

## 📂 카테고리 검색 API (API No. 68)

### ✅ 엔드포인트

- `https://openapi.domeggook.com/api/rest/category/searchCategoryList`

### 🔍 주요 파라미터

| 필드         | 필수 | 설명                                |
| ---------- | -- | --------------------------------- |
| `ver`      | Y  | API 버전 (※ 이 API는 `1.0`)           |
| `aid`      | Y  | API 인증 키                          |
| `market`   | Y  | `supply` 사용                       |
| `category` | N  | 시작 카테고리 번호 (ex: `01_11_00_00_00`) |
| `depth`    | N  | 조회할 카테고리 단계 (1\~5, 기본값 5)         |

### 📄 응답

- XML 형식
- 카테고리는 5단계 구조이며, 코드값은 `01_11_00_00_00` 형태로 전달됨

> `01_00_00_00_00` → ❌ 불가 (대분류만) `01_11_00_00_00` → ✅ 가능 (중분류 포함)

---

## 🔍 상품 검색 API (API No. 73)

### ✅ 엔드포인트

- `https://openapi.domeggook.com/api/rest/product/searchProductList`

### 🔍 요청 파라미터

| 필드          | 필수 | 타입     | 설명                                            |
| ----------- | -- | ------ | --------------------------------------------- |
| `ver`       | Y  | string | API 버전 (`4.1`)                                |
| `aid`       | Y  | string | 발급받은 API Key                                  |
| `market`    | Y  | string | 서비스 구분 (도매매는 `supply`)                        |
| `ca`        | N  | string | 카테고리 코드 (예: `01_11_00_00_00`)                 |
| `start`     | N  | int    | 페이지 시작 위치 (기본: 1)                             |
| `limit`     | N  | int    | 요청 수량 (기본: 10, 최대: 100)                       |
| `soldout`   | N  | string | 품절 제외 여부 (`Y` 또는 `N`)                         |
| `state`     | N  | string | 판매 상태 (`Y`: 판매중, `N`: 중지, 기본: `Y`)            |
| `img_yn`    | N  | string | 이미지 없는 상품 제외 여부 (`Y`/`N`)                     |
| `search`    | N  | string | 상품명 검색 키워드                                    |
| `min_price` | N  | int    | 최소 가격                                         |
| `max_price` | N  | int    | 최대 가격                                         |
| `order`     | N  | string | 정렬: `new`, `row`, `price_asc`, `price_desc` 등 |
| `om`        | N  | string | 응답 형식 (기본: XML, `json` 가능)                    |

> ⚠️ 최소 한 개 이상의 필터 파라미터(`ca`, `search` 등)가 필수이며, 전체 상품 수집에는 `ca`(카테고리) 권장

### 📄 응답

- XML 형식 기본, `om=json` 지정 시 JSON 반환
- 응답 구조 예시:

```xml
<response>
  <itemList>
    <item>
      <pid>123456</pid>
      <itemNm>상품명</itemNm>
      <price>10000</price>
      <stockFlag>Y</stockFlag>
      <itemUrl>https://...상품링크</itemUrl>
      <imageUrl>https://...대표이미지</imageUrl>
      <state>Y</state>
      <soldout>N</soldout>
      <deliveryType>택배</deliveryType>
      <itemGrade>일반</itemGrade>
    </item>
  </itemList>
  <pageInfo>
    <totalCount>152</totalCount>
    <pageNum>1</pageNum>
    <pageSize>100</pageSize>
  </pageInfo>
</response>
```

| 필드명            | 설명               |
| -------------- | ---------------- |
| `pid`          | 상품 고유번호          |
| `itemNm`       | 상품명              |
| `price`        | 가격               |
| `stockFlag`    | 재고 여부 (`Y`, `N`) |
| `itemUrl`      | 상품 페이지 링크        |
| `imageUrl`     | 대표 이미지 URL       |
| `state`        | 판매 상태 (`Y`, `N`) |
| `soldout`      | 품절 여부 (`Y`, `N`) |
| `deliveryType` | 배송 방식            |
| `itemGrade`    | 상품 등급 (예: 일반)    |

- XML 형식
- 상품 목록, 가격, 이미지, 상태 등이 포함됨

---

## 🧾 상품 상세 API (API No. 319)

### ✅ 엔드포인트

- `https://openapi.domeggook.com/api/rest/product/searchProductInfo`

### 🔍 요청 파라미터

| 필드       | 필수 | 타입     | 설명                            |
| -------- | -- | ------ | ----------------------------- |
| `ver`    | Y  | string | API 버전 (`4.5`)                |
| `aid`    | Y  | string | API 인증 키                      |
| `market` | Y  | string | 서비스 코드 (`supply`)             |
| `pid`    | Y  | string | 상품 고유번호                       |
| `om`     | N  | string | 응답 포맷 (기본: XML, `json` 지정 가능) |

### 📄 응답

- XML 형식 또는 `om=json` 지정 시 JSON 반환 가능
- 상세정보, 이미지, 옵션, 배송, 설명 포함

```xml
<response>
  <pid>123456</pid>
  <itemNm>상품명</itemNm>
  <description><![CDATA[<p>상품 설명</p>]]></description>
  <brand>브랜드명</brand>
  <maker>제조사</maker>
  <origin>원산지</origin>
  <model>모델명</model>
  <price>10000</price>
  <imageList>
    <image>https://...1.jpg</image>
    <image>https://...2.jpg</image>
  </imageList>
  <optionList>
    <option>
      <optNm>색상</optNm>
      <optVal>Red</optVal>
    </option>
    <option>
      <optNm>사이즈</optNm>
      <optVal>L</optVal>
    </option>
  </optionList>
  <deliveryType>택배</deliveryType>
  <deliveryCharge>3000</deliveryCharge>
  <itemState>Y</itemState>
</response>
```

| 필드명              | 설명                      |
| ---------------- | ----------------------- |
| `pid`            | 상품 고유 ID                |
| `itemNm`         | 상품명                     |
| `description`    | 상품 설명 HTML (CDATA로 감싸짐) |
| `brand`          | 브랜드명                    |
| `maker`          | 제조사                     |
| `origin`         | 원산지                     |
| `model`          | 모델명                     |
| `price`          | 소비자 가격                  |
| `imageList`      | 이미지 배열 (URL 목록)         |
| `optionList`     | 상품 옵션 (옵션명/값 구조)        |
| `deliveryType`   | 배송 방식                   |
| `deliveryCharge` | 기본 배송비 (숫자값)            |
| `itemState`      | 판매 상태 (`Y`, `N`)        |

---

## 📦 재고/가격 조회 API (API No. 19)

### ✅ 엔드포인트

- `https://openapi.domeggook.com/api/rest/product/searchProductQtyPrice`

### 🔍 요청 파라미터

| 필드       | 필수 | 타입     | 설명                         |
| -------- | -- | ------ | -------------------------- |
| `ver`    | Y  | string | API 버전 (`4.5`)             |
| `aid`    | Y  | string | API 인증 키                   |
| `market` | Y  | string | `supply` (도매매 전용)          |
| `pid`    | Y  | string | 상품 고유번호                    |
| `om`     | N  | string | 응답 포맷 (기본: XML, `json` 가능) |

### 📄 응답

- XML 형식 또는 `om=json` 지정 시 JSON 반환 가능
- 실시간 재고/가격 상태 포함

```xml
<response>
  <pid>123456</pid>
  <price>9500</price>
  <stockQty>25</stockQty>
  <itemState>Y</itemState>
</response>
```

| 필드명         | 설명                      |
| ----------- | ----------------------- |
| `pid`       | 상품 고유번호                 |
| `price`     | 현재 판매가                  |
| `stockQty`  | 남은 재고 수량                |
| `itemState` | 상태 (`Y`: 판매중, `N`: 중지됨) |

---

## 📌 참고 사항

- XML 파싱 필요: 응답은 JSON이 아닌 XML
- 오류 응답 예시는 [stderr 문서](https://openapi.domeggook.com/main/guide/stderr) 참고
- API 테스트 샘플은 [sample 문서](https://openapi.domeggook.com/main/guide/sample) 참고
- 인증 키는 도매꾹 개발자 센터에서 발급받아 사용

> 이 문서는 도매매 상품 수집 및 카테고리 연동 자동화를 위한 기반 명세입니다. 이후 fetcher/parser 모듈 및 중앙 에이전트 연동에 활용됩니다.

