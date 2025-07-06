# API 키 및 설정 상태

## ✅ 설정 완료 및 검증됨

### 1. Supabase (데이터베이스)
- **SUPABASE_URL**: https://opahgyfnirufeiaxcpdl.supabase.co
- **SUPABASE_SERVICE_ROLE_KEY**: 설정됨
- **상태**: ✅ 정상 작동 중
- **테스트 결과**: 연결 성공, 테이블 접근 가능

### 2. Google Gemini (AI 모델)
- **GEMINI_API_KEY**: AIzaSyD18ntyKoXp7QQhgd_xe4dDqfC_yVTtnrY
- **상태**: ✅ API 키 설정 및 작동 확인
- **테스트 결과**: gemini-1.5-flash 모델 사용 가능

### 3. 오너클랜 (공급사)
- **OWNERCLAN_USERNAME**: b00679540
- **OWNERCLAN_PASSWORD**: 설정됨
- **상태**: ✅ JWT 인증 성공
- **테스트 결과**: 인증 토큰 발급 성공

### 4. 쿠팡 (마켓플레이스)
- **COUPANG_ACCESS_KEY**: a825d408-a53d-4234-bdaa-be67acd67e5d
- **COUPANG_SECRET_KEY**: 856d45fae108cbf8029eaa0544bcbeed2a21f9d4
- **COUPANG_VENDOR_ID**: A01282691
- **상태**: ✅ API 키 설정 완료
- **테스트 결과**: 키 설정 확인 (실제 API 호출은 추가 검증 필요)

## ⚠️ 설정됨 but 연결 실패

### 1. 도매매/도매꾹 (공급사)
- **DOMEME_API_KEY**: 96ef1110327e9ce5be389e5eaa612f4a
- **상태**: ⚠️ API 키는 설정되었으나 연결 실패
- **문제**: 404 에러 - API URL 또는 키 확인 필요
- **해결방안**: 도매매 측에 API 키 유효성 확인 요청

## ❌ 미설정 또는 부분 설정

### 1. 젠트레이드 (공급사)
- **ZENTRADE_ID**: b00679540 (설정됨)
- **ZENTRADE_M_SKEY**: 5284c44b0fcf0f877e6791c5884d6ea9 (설정됨)
- **ZENTRADE_FTP_PASS**: your-ftp-password (미설정)
- **상태**: ⚠️ FTP 비밀번호 필요
- **참고**: FTP 접속 정보 추가 필요

### 2. 11번가 (마켓플레이스)
- **ELEVENST_API_KEY**: 87d6fb7e7e5535729fa9fd42ffbad7ed (설정됨)
- **ELEVENST_API_SECRET**: your-11st-secret (미설정)
- **ELEVENST_SELLER_ID**: your-seller-id (미설정)
- **상태**: ⚠️ API Secret과 Seller ID 필요
- **필수 여부**: ❗ 11번가 사용 시 필수

### 3. 네이버 스마트스토어 (마켓플레이스)
- **NAVER_CLIENT_ID**: 6VLJ92Z3etSr7l0NW50W2u (설정됨)
- **NAVER_CLIENT_SECRET**: $2a$04$c2PIErmauo6fBliTyxAmLe (설정됨)
- **NAVER_ACCESS_TOKEN**: your-access-token (미설정)
- **NAVER_REFRESH_TOKEN**: your-refresh-token (미설정)
- **상태**: ⚠️ OAuth 토큰 발급 필요
- **필수 여부**: ❗ 스마트스토어 사용 시 필수

### 4. G마켓/옥션 (마켓플레이스)
- **GMARKET_SELLER_ID**: your-gmarket-seller-id (미설정)
- **GMARKET_API_KEY**: your-gmarket-api-key (미설정)
- **상태**: ❌ 완전 미설정
- **필수 여부**: ❗ G마켓/옥션 사용 시 필수

## 📊 현재 작동 가능한 기능

### ✅ 완전 작동 가능
- **Supabase 데이터베이스**: 모든 데이터 저장/조회
- **Google Gemini AI**: 상품 설명 최적화, 키워드 생성
- **오너클랜 상품 수집**: GraphQL API 통한 상품 데이터 수집
- **쿠팡 업로드 준비**: API 키 설정 완료 (실제 업로드는 vendor 검증 필요)

### ⚠️ 부분적 작동
- **도매매/도매꾹**: API 키는 있으나 연결 실패 (URL 또는 키 확인 필요)
- **젠트레이드**: ID/M_SKEY는 있으나 FTP 비밀번호 필요
- **11번가**: API 키만 있고 Secret/Seller ID 필요
- **네이버 스마트스토어**: Client ID/Secret은 있으나 OAuth 토큰 필요

### ❌ 작동 불가
- **G마켓/옥션**: 모든 인증 정보 미설정

## 📋 권장 사항

### 즉시 해결 가능한 항목
1. **도매매 API 문제 해결**
   - API 키 유효성 확인
   - 정확한 API URL 확인 필요

2. **젠트레이드 FTP 비밀번호**
   - 젠트레이드 관리자 페이지에서 FTP 비밀번호 확인

### 추가 설정이 필요한 항목
1. **11번가**: API Secret과 판매자 ID 필요
2. **네이버 스마트스토어**: OAuth 인증 플로우 실행 필요
3. **G마켓/옥션**: 판매자 등록 및 API 키 발급 필요

## 🔐 보안 주의사항
- `.env` 파일은 절대 Git에 커밋하지 마세요
- 프로덕션 환경에서는 환경 변수로 관리하세요
- API 키는 정기적으로 갱신하세요