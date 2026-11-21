"""값 + 근거(provenance) 모델."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

CONFIRMED = "확정"
NEEDS_CHECK = "확인 필요"


@dataclass
class Value:
    item: str  # 항목 (예: 매출액)
    year: int
    value: int | float | str | None
    file: str = ""
    form: str = ""
    page: int | None = None
    label: str = ""  # 원문 라벨 또는 코드
    status: str = CONFIRMED
    note: str = ""
    unit: str = "원"

    @property
    def ok(self) -> bool:
        return self.status == CONFIRMED and self.value is not None

    def src(self) -> str:
        if not self.file:
            return "계산값"
        return f"{self.file} · {self.form} · p{self.page}"

    def dict(self) -> dict:
        d = asdict(self)
        d["source"] = self.src()
        return d


def missing(item: str, year: int, why: str) -> Value:
    return Value(item, year, None, status=NEEDS_CHECK, note=why)


@dataclass
class Evidence:
    """보고서 전체에서 쓴 값과 검산 결과를 모은다."""

    values: list[Value] = field(default_factory=list)
    checks: list[dict] = field(default_factory=list)
    flags: list[dict] = field(default_factory=list)  # 차이 표시 등 주석

    def add(self, v: Value) -> Value:
        self.values.append(v)
        return v

    def check(self, name: str, ok: bool, detail: str):
        self.checks.append({"검산": name, "결과": "통과" if ok else "불일치", "내용": detail})
        return ok

    @property
    def needs_check(self) -> list[Value]:
        return [v for v in self.values if v.status == NEEDS_CHECK]
