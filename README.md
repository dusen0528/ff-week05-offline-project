# ff-week05-offline-project — 법인세 분석 보고서 자동화

같은 회사의 **세무조정계산서 PDF 2개(전기·당기)**를 넣으면 **법인세 분석 보고서 PDF·Excel**과 **조정료청구서**를 만드는 프로그램입니다.
1차~4차에 걸쳐 같은 프로그램을 계속 고쳐 나갑니다.

## 핵심 원칙
1. 보고서의 숫자마다 **출처(파일 · 서식 · 페이지)**를 댈 수 있어야 합니다.
2. 모호한 기준은 **추측하지 않고 질문**합니다. 확정 전에는 «확인 필요»로 둡니다 (채점에서는 오답).
3. 기준값은 `config/`에 둡니다. 답을 받으면 설정만 바꿔 다시 실행합니다.
4. 결정은 모두 [docs/DECISIONS.md](docs/DECISIONS.md)에 남깁니다.

## 문서
| 문서 | 내용 |
|---|---|
| [docs/SPEC.md](docs/SPEC.md) | 요구사항 명세 v0.2. 섹션별 규칙, 1차 기대 값 |
| [docs/DECISIONS.md](docs/DECISIONS.md) | **의사결정 로그** D-001~D-018 |
| [docs/QUESTIONS.md](docs/QUESTIONS.md) | 고객 질문 Q-01~Q-12와 답변 기록 |
| [docs/FORM_MAP.md](docs/FORM_MAP.md) | 서식·페이지 맵, 추출 값, 발견 사항 F-01~F-10 |
| [docs/ROUNDS.md](docs/ROUNDS.md) | 차수별 진행·제출 기록 |

## 폴더
```
├── .claude/skills/kordoc/   # kordoc 스킬 (한국 문서 → Markdown, D-016)
├── docs/
├── input/
│   ├── round1/              # 받은 원본 4개
│   └── _parsed/             # kordoc 변환 결과 (전체본 + 페이지별)
├── config/  src/  output/  logs/
```

## 문서 변환 (kordoc)
```bash
# Node 20 이상. 리눅스에서 sharp 오류가 나면 ONNXRUNTIME_NODE_INSTALL=skip
npx -y kordoc@4.25.2 input/round1/요구사항.xlsx -o input/_parsed/요구사항.md
npx -y kordoc@4.25.2 input/round1/샘플컴퍼니_2025_세무조정계산서.pdf -p 54-55 -o /tmp/fs.md   # 페이지 범위
npx -y kordoc@4.25.2 input/round1/샘플컴퍼니_2025_세무조정계산서.pdf --format json -o /tmp/doc.json  # blocks[].pageNumber
```
Claude Code 플러그인으로 쓰려면 `/plugin marketplace add chrisryugj/kordoc` → `/plugin install kordoc@kordoc`.

## 진행 상태
- [x] 1차 자료 읽기 · 서식 맵 · 명세 v0.2 · 질문 정리
- [ ] 1차 고객 질문 발송 → 답변 반영
- [ ] 1차 구현 → 보고서 PDF 제출
- [ ] 2차 / 3차 / 4차
