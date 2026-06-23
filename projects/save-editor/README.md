# ECWolf Save Editor

ECWolf `.ecs` 세이브 파일 편집기. Python + React + WebView2 기반.

## 실행

```bash
# 개발 모드
./run.sh

# 또는 수동 실행
uv sync
cd frontend && npm install && npx vite build && cd ..
uv run python main.py
```

브라우저가 열리거나 WebView2 창이 표시됩니다.

## 빌드

```bash
./build.sh
```

`dist/` 디렉토리에 플랫폼별 실행 파일 생성.

## 의존성

- **Python 3.13+**: `uv sync`로 자동 설치
- **Node.js 20+**: `npm install`로 자동 설치
- **Windows**: WebView2 (Windows 10+ 기본 내장)
- **Linux**: WebKit2GTK (`sudo apt install webkit2gtk-4.1`)
- **macOS**: WebKit (기본 내장)
