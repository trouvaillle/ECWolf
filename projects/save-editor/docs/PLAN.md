# ECWolf Save Editor - 프로젝트 문서

## 1. 개요

ECWolf(`Wolf3D/BlakeStone` 엔진)의 `.ecs` 세이브 파일을 GUI로 편집하는 도구.
세이브 파일은 PNG 포맷에 커스텀 청크(`tEXt`, `raNd`, `snAp`)가 포함된 구조.

## 2. 세이브 파일 구조 분석

`.ecs` 파일 = PNG + 커스텀 청크:

```
PNG Signature (8 bytes)
IHDR (screenshot: 216x162, 8-bit palette, color_type=3)
gAMA
PLTE (256-color palette, 768 bytes)
IDAT (screenshot 픽셀 데이터, zlib 압축)
tEXt (메타데이터 - 키-값 쌍)
  - "Software": "ECWolf"
  - "Engine": "ECWOLF"
  - "ECWolf Save Version": "ECWOLFSAVE{timestamp}ull"
  - "ECWolf Save Product Version": "1049602"
  - "Title": "저장명"
  - "Current Map": "MAP11"
  - "Creation Time": 타임스탬프
  - "Comment": 맵명 + 시간
  - "Game WAD": IWAD 목록 (; 구분)
  - "Map WAD": 맵 WAD 파일명
raNd (RNG 상태) - SFMT 난수 생성기 상태 (rngseed + named RNG 테이블)
snAp (압축된 게임 상태)
  - FLZL (4 bytes magic)
  - compressed_size (4 bytes, Big Endian)
  - uncompressed_size (4 bytes, Big Endian)
  - zlib 압축 데이터
IEND
```

### snAp 청크 역직렬화 순서 (FArchive)

압축 해제 후 바이너리 스트림 구조:
1. `difficulty` (short, 2 bytes) - 난이도 (0=Baby ~ 4=Hard)
2. `playerClass[0]` - ClassDef* (UserWriteClass/UserReadClass)
3. `maxPlayers` (uint32, 버전 >= 1599444347)
4. `playerClass[1..N]` (ClassDef* 배열)
5. `secretcount` (short) - 이 레벨에서 찾은 비밀
6. `treasurecount` (short) - 이 레벨에서 얻은 보물
7. `killcount` (short) - 이 레벨에서 죽인 적
8. `secrettotal` (short) - 전체 비밀 수
9. `treasuretotal` (short) - 전체 보물 수
10. `killtotal` (short) - 전체 적 수
11. `TimeCount` (int32) - 게임 시간 (틱, 1틱=1/70초)
12. `victoryflag` (bool) - 승리 애니메이션 플래그
13. `fullmap` (bool, 버전 >= 1393719642) - 전체 맵 공개 여부
14. `LevelRatios` (killratio, secretsratio, treasureratio, numLevels, time, par)
15. `thinkerList` (모든 액터/생명체 직렬화 - DObject 포인터 테이블)
16. `map` (GameMap 전체 상태 - 모든 타일, 존, 트리거)
17. `players[N]` (플레이어 상태 - health, ammo, weapons 등)

### FCompressedFile 포맷 상세

| 오프셋 | 크기 | 필드 | 설명 |
|--------|------|------|------|
| 0 | 4 | ZSig | 매직 "FLZL" |
| 4 | 4 | compressed_size | 압축된 크기 (Big Endian DWORD) |
| 8 | 4 | uncompressed_size | 압축 해제 후 크기 (Big Endian DWORD) |
| 12 | 변동 | zlib_data | zlib `compress()` 출력 |

- `compressed_size == 0`이면 데이터가 압축되지 않은 것 (raw)
- 읽기: `uncompress()`로 해제

## 3. 구현 현황 (Phase 1)

### 읽기 기능
- [x] PNG 청크 파싱 (IHDR, PLTE, IDAT, tEXt, raNd, snAp) - `save_parser.py`
- [x] tEXt 메타데이터 추출 및 표시 - React UI
- [x] 스크린샷 이미지 디코딩 및 미리보기 (216x162, 팔레트 → RGBA)
- [x] snAp 청크 압축 해제 (zlib)
- [ ] snAp 헤더 필드 파싱 (difficulty, stats, TimeCount)

### 편집 기능
- [x] tEXt 메타데이터 편집 (Title 등)
- [ ] snAp 기본 필드 편집 (난이도, stats 등)
- [x] PNG 재구성 및 저장 (tEXt 수정 + CRC 재계산)

### UI
- [x] 스크린샷 미리보기 (좌측 사이드바)
- [x] 메타데이터 표시/편집 폼 (탭: Game Info / Metadata)
- [x] 파일 열기 대화상자 (HTML file input)
- [x] 저장 버튼
- [x] 다크 테마

## 4. 기술 스택

| 계층 | 기술 | 버전 |
|------|------|------|
| 언어 | Python / TypeScript | 3.13+ / 5.7+ |
| 백엔드 | aiohttp | 3.14 |
| 프론트엔드 | React + Vite | 19 / 6 |
| 윈도우 | pywebview (WebView2) | 6.2 |
| 이미지 | Pillow | 12.2 |
| 압축 | zlib | (내장) |
| 프로젝트 | uv | 0.11 |

## 5. 프로젝트 구조

```
projects/save-editor/
├── docs/
│   └── PLAN.md                    # 분석 및 설계 문서
├── savegam0.ecs                    # 샘플 세이브 파일
├── pyproject.toml                  # uv Python 프로젝트 설정
├── main.py                         # 진입점 (서버 + WebView2 실행)
├── save_parser.py                  # .ecs 파일 파서
├── api_server.py                   # aiohttp REST API 서버
├── run.sh                          # 개발 실행 스크립트
├── build.sh                        # 패키징 스크립트 (PyInstaller)
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── index.html
│   └── src/
│       ├── main.tsx                # React 진입점
│       └── App.tsx                 # 메인 UI 컴포넌트
├── .python-version                 # Python 버전 고정
├── uv.lock                         # 의존성 잠금 파일
└── README.md
```

## 6. API 명세

### `POST /api/open`
세이브 파일 열기.

```json
// Request
{ "path": "/path/to/savegam0.ecs" }

// Response
{
  "path": "...",
  "metadata": { "Title": "...", "Current Map": "...", ... },
  "saveVersion": 1757820379,
  "saveProdVersion": 1049602,
  "snapSize": 5864,
  "snapDecompressedSize": 303318,
  "hasScreenshot": true
}
```

### `GET /api/info`
현재 로드된 세이브 정보 반환.

### `POST /api/save`
메타데이터 수정 후 저장.

```json
// Request
{ "path": "...", "metadata": { "Title": "New Title" } }

// Response: 업데이트된 SaveInfo
```

### `GET /api/screenshot`
스크린샷을 base64 Data URI로 반환.

```json
// Response
{ "image": "data:image/png;base64,..." }
```

### `GET /api/files?dir=PATH`
디렉토리 내 .ecs 파일 목록 조회.

## 7. 통신 흐름

```
[WebView2 / Browser]
       │
       │ HTTP (localhost:8765)
       ▼
[Python aiohttp Server]
       │
       ├── /api/* → REST API 핸들러
       │                │
       │                └── save_parser.py ←→ .ecs file
       │
       └── /* → Static File Server (frontend/dist/)
```

개발 모드에서는 Vite dev server (`localhost:5173`)가 API를 `localhost:8765`로 프록시.

## 8. 빌드 및 배포

```bash
# 실행
./run.sh

# 패키징
./build.sh   # → dist/ecwolf-save-editor*
```

| 플랫폼 | WebView 백엔드 | PyInstaller 출력 |
|--------|---------------|-----------------|
| Windows | WebView2 (내장) | `ecwolf-save-editor.exe` |
| Linux   | WebKit2GTK (`apt install webkit2gtk-4.1`) | 실행 파일 |
| macOS   | WebKit (내장) | `.app` 번들 |

## 9. 향후 개선 사항

- [ ] snAp 헤더 필드 파싱 (difficulty, killcount, secretcount, TimeCount)
- [ ] snAp 필드 편집 (체력, 탄약, 무기 등)
- [ ] 플레이어 인벤토리 파싱 및 편집
- [ ] Raw hex 뷰어/에디터
- [ ] 드래그 & 드롭 파일 열기
- [ ] .ecs 파일 브라우저 (파일 탐색기)
- [ ] 다국어 지원 (i18n)
