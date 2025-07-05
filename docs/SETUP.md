# 드랍쉬핑 자동화 시스템 설정 가이드

## 목차
1. [시스템 요구사항](#시스템-요구사항)
2. [설치 방법](#설치-방법)
3. [환경 변수 설정](#환경-변수-설정)
4. [데이터베이스 설정](#데이터베이스-설정)
5. [AI 모델 설정](#ai-모델-설정)
6. [공급사 API 설정](#공급사-api-설정)
7. [마켓플레이스 API 설정](#마켓플레이스-api-설정)
8. [모니터링 설정](#모니터링-설정)
9. [실행 방법](#실행-방법)

## 시스템 요구사항

- Python 3.11 이상
- PostgreSQL (Supabase 사용)
- Ollama (로컬 AI 모델용, 선택사항)
- 최소 8GB RAM
- 10GB 이상의 디스크 공간

## 설치 방법

### 1. 저장소 클론
```bash
git clone https://github.com/your-repo/dropshipping-automation.git
cd dropshipping-automation
```

### 2. 가상환경 생성 및 활성화
```bash
python -m venv venv
source activate.sh  # Linux/Mac
# 또는
.\venv\Scripts\activate  # Windows
```

### 3. 의존성 설치
```bash
pip install -r requirements.txt
```

### 4. 환경 변수 설정
```bash
cp .env.example .env
# .env 파일을 편집하여 필요한 값 설정
```

## 환경 변수 설정

### 기본 설정
```env
ENV=development          # development, staging, production
DEBUG=true              # 디버그 모드
LOG_LEVEL=INFO          # DEBUG, INFO, WARNING, ERROR, CRITICAL
SCHEDULER_ENABLED=true  # 스케줄러 자동 시작
```

### 데이터베이스 (Supabase)

1. [Supabase](https://supabase.com)에서 프로젝트 생성
2. Settings > API에서 URL과 Service Role Key 복사
3. `.env` 파일에 설정:
```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
```

## AI 모델 설정

### Google Gemini (클라우드)
1. [Google AI Studio](https://makersuite.google.com/app/apikey)에서 API 키 생성
2. `.env` 파일에 설정:
```env
GEMINI_API_KEY=your-gemini-api-key
```

### Ollama (로컬)
1. [Ollama](https://ollama.ai) 설치
2. 필요한 모델 다운로드:
```bash
ollama pull gemma:3b
ollama pull deepseek-r1:7b
ollama pull qwen:14b
```
3. `.env` 파일에 설정:
```env
OLLAMA_HOST=http://localhost:11434
```

## 공급사 API 설정

### 도매매/도매꾹
1. [도매꾹](https://www.domeggook.com) 회원가입 및 API 신청
2. `.env` 파일에 설정:
```env
DOMEME_API_KEY=your-domeme-api-key
```

### 오너클랜
1. [오너클랜](https://www.ownerclan.com) 파트너 신청
2. `.env` 파일에 설정:
```env
OWNERCLAN_API_KEY=your-ownerclan-api-key
```

## 마켓플레이스 API 설정

### 쿠팡
1. [쿠팡 WING](https://wing.coupang.com) 셀러 가입
2. API 인증키 발급
3. `.env` 파일에 설정:
```env
COUPANG_ACCESS_KEY=your-access-key
COUPANG_SECRET_KEY=your-secret-key
COUPANG_VENDOR_ID=your-vendor-id
```

### 11번가
1. [11번가 셀러존](https://soffice.11st.co.kr) 가입
2. OpenAPI 신청
3. `.env` 파일에 설정:
```env
ELEVENST_API_KEY=your-api-key
ELEVENST_API_SECRET=your-api-secret
ELEVENST_SELLER_ID=your-seller-id
```

### 네이버 스마트스토어
1. [네이버 커머스 API](https://apicenter.commerce.naver.com) 신청
2. OAuth 2.0 인증 설정
3. `.env` 파일에 설정:
```env
NAVER_CLIENT_ID=your-client-id
NAVER_CLIENT_SECRET=your-client-secret
```

## 모니터링 설정

### Slack 알림 (선택사항)
1. Slack 워크스페이스에서 Incoming Webhook 생성
2. `.env` 파일에 설정:
```env
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

### 대시보드
```env
DASHBOARD_HOST=0.0.0.0
DASHBOARD_PORT=8080
```

## 데이터베이스 초기화

### 1. 스키마 생성
```bash
python dropshipping/db/migrate.py
```

### 2. 시드 데이터 입력 (선택사항)
```bash
python dropshipping/db/seed.py
```

## 실행 방법

### CLI 모드
```bash
python -m dropshipping.main
```

### 스케줄러 실행
```bash
python -m dropshipping.scheduler.main
```

### 모니터링 대시보드
```bash
python -m dropshipping.monitoring.dashboard
# 브라우저에서 http://localhost:8080 접속
```

### 개발 모드 (모든 서비스 동시 실행)
```bash
# 별도 터미널에서 각각 실행
python -m dropshipping.scheduler.main
python -m dropshipping.monitoring.dashboard
```

## 문제 해결

### 1. 의존성 오류
```bash
pip install --upgrade -r requirements.txt
```

### 2. 데이터베이스 연결 오류
- Supabase URL과 키가 올바른지 확인
- 네트워크 연결 확인

### 3. AI 모델 오류
- Ollama가 실행 중인지 확인: `ollama list`
- Gemini API 키가 유효한지 확인

### 4. 로그 확인
```bash
tail -f logs/dropshipping.log
```

## 프로덕션 배포

### 1. 환경 변수 설정
```env
ENV=production
DEBUG=false
DRY_RUN=false
```

### 2. systemd 서비스 등록 (Linux)
```bash
sudo cp deployment/dropshipping.service /etc/systemd/system/
sudo systemctl enable dropshipping
sudo systemctl start dropshipping
```

### 3. Docker 배포 (준비중)
```bash
docker build -t dropshipping .
docker run -d --env-file .env dropshipping
```

## 보안 주의사항

1. **절대 `.env` 파일을 Git에 커밋하지 마세요**
2. 프로덕션 환경에서는 강력한 SECRET_KEY 사용
3. API 키는 주기적으로 재발급
4. 데이터베이스 백업 설정
5. HTTPS 사용 권장