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
    warnings: list[dict] = field(default_factory=list)

    def add(self, v: Value) -> Value:
        self.values.append(v)
        return v

    def check(self, name: str, ok, detail: str, *operands):
        """ok가 None이거나 피연산자에 확인 필요 값이 있으면 '보류'."""
        if ok is None or any(o is NA or o is None for o in operands):
            self.checks.append({"검산": name, "결과": "보류", "내용": detail + " (확인 필요 값 포함)"})
            return None
        self.checks.append({"검산": name, "결과": "통과" if ok else "불일치", "내용": detail})
        return ok

    def warn(self, kind: str, v: "Value | None" = None, detail: str = "", **kw):
        """2차 규칙 2: 파일·연도·서식·페이지·항목·표시값을 남긴다."""
        rec = {"구분": kind, "파일": v.file if v else kw.get("file", ""), "연도": v.year if v else kw.get("year", ""),
               "서식": v.form if v else kw.get("form", ""), "페이지": v.page if v else kw.get("page", ""),
               "항목": v.label or v.item if v else kw.get("item", ""),
               "표시값": ("(회색 칸)" if v and v.value is None else v.value) if v else kw.get("shown", ""),
               "내용": detail}
        if rec not in self.warnings:
            self.warnings.append(rec)

    @property
    def needs_check(self) -> list[Value]:
        return [v for v in self.values if v.status == NEEDS_CHECK]


class _NA:
    """확인할 수 없는 값. 계산에 섞이면 결과도 NA가 되고(보류), 표시할 때는 «확인 필요»."""

    _inst = None

    def __new__(cls):
        if cls._inst is None:
            cls._inst = super().__new__(cls)
        return cls._inst

    def _op(self, *a):
        return self

    __add__ = __radd__ = __sub__ = __rsub__ = __mul__ = __rmul__ = _op
    __truediv__ = __rtruediv__ = __floordiv__ = __rfloordiv__ = __neg__ = __abs__ = __pos__ = _op

    def __lt__(self, o): return False
    __le__ = __gt__ = __ge__ = __lt__

    def __eq__(self, o): return o is self
    def __hash__(self): return 0
    def __bool__(self): return False
    def __format__(self, spec): return NEEDS_CHECK
    def __str__(self): return NEEDS_CHECK
    __repr__ = __str__


NA = _NA()


def is_na(*xs) -> bool:
    return any(x is NA or x is None for x in xs)


def div(a, b):
    """안전한 나눗셈: NA면 NA, 0으로 나누면 None(표시는 '-')."""
    if is_na(a, b):
        return NA
    return a / b if b else None
