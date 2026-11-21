# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A program that takes **two 세무조정계산서 PDFs for the same company (전기 · 당기)** and produces a **법인세 분석 보고서 PDF** (the only graded output) plus a 조정료청구서 (not graded). Work proceeds in rounds 1차–4차; each round brings new input files (other companies, reordered forms, missing pages, possibly scanned PDFs) and the **same program is extended**, not rewritten.

Current state: round 1 materials read and specified (SPEC v0.2). `src/` and `config/` are still empty. Inputs are text PDFs (no OCR needed in round 1). Parsing approach is decided in `docs/DECISIONS.md` D-016: **kordoc** (`.claude/skills/kordoc/`, run `npx -y kordoc@4.25.2 …`) for Excel, form discovery and evidence (its JSON blocks carry `pageNumber`), plus a layout-text line parser (`pdftotext -layout` / pdfplumber) for the 결산 재무상태표·손익계산서 numbers, because kordoc merges those statements' labels and amounts into single `<br>` cells. Converted Markdown is in `input/_parsed/` (whole file + per-page `_pages/pNNN.md`). Stack (D-028): Python 3.11 + uv. Code is in `src/ff_report/` (`extract.py` → `analysis.py` → `render_pdf.py` / `render_xlsx.py` / `charts.py` / `invoice.py`). Rules are in `config/rules.yaml`.

```bash
uv sync
uv run ff-report --prev input/round1/샘플컴퍼니_2024_세무조정계산서.pdf --curr input/round1/샘플컴퍼니_2025_세무조정계산서.pdf
# → output/: 보고서 PDF (graded), Excel, 조정료청구서 초안, 근거.json, charts/
```
The run prints check results and the «확인 필요» count. Do not submit while that count is above 0.

## Non-negotiable rules (from README / SPEC)

1. **Every number is traceable.** Each extracted value carries `{항목, 연도, 값, 단위, 파일, 서식명, 페이지, 원문 라벨, 상태(확정/확인 필요), 비고}` (FR-2.2). The report and the 근거 표 are built from these records.
2. **Don't guess ambiguous criteria.** Mark the value «확인 필요» and add or point to a question in `docs/QUESTIONS.md`. Never present an estimate as a confirmed value (NFR-5).
3. **«확인 필요» counts as wrong when graded.** A submission must contain zero of them. They are resolved by getting answers and re-running, not by filling in plausible numbers.
4. **No hardcoded criteria.** Formulas, units, rounding, item mappings, the 판관비 selection rule, the fee schedule, and so on live in `config/`. A client answer should change only config, then re-run (FR-5.3).
5. **Locate forms by 서식명 and 원문 라벨, never by page number.** Page positions differ between rounds and companies (NFR-2). `FORM_MAP.md` page numbers are for evidence and checking only.
6. **Read company identity from the PDF body, not the filename** (법인명, 사업자등록번호, 사업연도). Stop if the two files belong to different companies. Warn if the years are equal or not consecutive (FR-1).

## Processing pipeline (SPEC §4)

`01 접수` (identify and pair files as 전기/당기) → `02 읽기` (find forms, extract values with provenance) → `03 작성` (comparison tables, charts, comment draft following the 출력 예시 Excel) → `04 검토` (검산 results plus the «확인 필요» list).

Checks to run before building the report (FR-6). A mismatch flips the value to «확인 필요» and is logged:
- 자산총계 = 부채총계 + 자본총계
- 매출총이익 = 매출액 − 매출원가
- 영업이익 = 매출총이익 − 판관비
- Σ 판관비 세부 = 판관비 합계

Prior-year values come from the 전기 PDF and are cross-checked against the 당기 PDF's prior-year column (D-004); in round 1 every item matches. Further checks are listed in SPEC FR-4, including 결손금 발생액 vs 세무상 결손금, which already mismatches by 129,800원 in round 1 (FORM_MAP F-01, Q-05).

## Report sections

Confirmed by the client (Q-01, D-019): **I. 기본정보 → II. 표준재무제표 (재무상태표, 손익계산서) → III. 법인세 신고상황 → IV. 이월결손금 → V. 소득금액조정 → VI. 공제·감면세액 → VII. 요약 코멘트 → VIII. 재무제표 주요 특이사항**, preceded by a 요약 카드 of the four key figures. Statement amounts come from the 표준재무제표 with their codes (D-020). 요약 카드 amounts use «1.93억원» at 1억 or more and «4,900만원» below, rounded to 0.01억 (D-021). A loss turning into a profit is shown as «흑자전환» (D-022). The 출력 예시 Excel is a layout reference only.

Ask the client only questions that change graded numbers or sections. The client UI flags other questions as «해당 문제에 필요 없는 질문입니다». Decide formatting yourself and log it in DECISIONS (D-023).

Format requirements that grading depends on (SPEC §6):
- Company name, 사업연도, and item names are visible.
- Column headers carry the year (`2024년`, `2025년`, `증감`, `증감률`).
- The unit is shown whenever amounts are abbreviated (억원 or 백만원).
- Item names, order, and notation follow the 출력 예시 Excel as closely as possible.
- Sans-serif (고딕) font with Korean text rendering correctly.

## Docs: what each one is for

- `docs/SPEC.md`: requirements with IDs (FR-x, NFR-x, R-x). Fill in `TBD`s as inputs are read, and link each one to a question ID.
- `docs/FORM_MAP.md`: which value lives in which form, page, and label for each file, including whether the 2025 PDF's prior-year column matches the 2024 PDF.
- `docs/QUESTIONS.md`: client question log. **Never delete or rewrite an original question**; append below it. Classify each answer as `답변 있음` / `불명확·충돌` / `답변 없음`. When an answer arrives, update `config/` and SPEC and log it in «답변 반영 이력».
- `docs/DECISIONS.md`: decision log D-001… with status 확정(자료/요구사항/고객) · 설계 · 잠정. Never delete a decision; supersede it with a new ID.
- `docs/ROUNDS.md`: per-round checklist, submission log, and grader feedback. Resubmission is allowed only 2 minutes after the previous submission.

## Layout notes

- `input/roundN/` holds each round's materials: the requirements Excel, the 출력 예시 Excel, and the company PDFs. `.gitignore` excludes `input/**/*.pdf` and `*.xlsx`, so inputs are never committed.
- Generated reports, invoices, and 근거 표 go to `output/`. Run logs and 검산 results go to `logs/`.
- Docs and client communication are in Korean. Write questions to the client in business terms and send them in one batch.
