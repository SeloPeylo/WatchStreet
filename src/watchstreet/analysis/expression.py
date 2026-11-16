"""A small series algebra: ``$objekt / gold``, ``yoy(CPIAUCSL)``, ``ma(copper / gold, 12)``.

Pure: the caller supplies ``resolve(name) -> Operand``. Two series are combined only on days both
have a value of their own; sums and differences need equal units. Nothing is filled or
interpolated, and the number of days lost by the alignment is reported.
"""

import math
import re
from bisect import bisect_right
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta

from watchstreet.constants import (
    DAYS_PER_YEAR,
    EXPRESSION_MAX_CHARS,
    EXPRESSION_MAX_NODES,
    PERCENT,
    SERIES_MAX_GAP_DAYS,
)
from watchstreet.errors import WatchStreetError

Points = list[tuple[date, float]]
RATIO_UNIT = "Verhältnis (ohne Einheit)"
PERCENT_UNIT = "%"
TOKEN = re.compile(r"\s*(?:(\d+(?:\.\d+)?)|(\$?[A-Za-z_][A-Za-z0-9_.:]*)|(.))")
SIMPLE_UNIT = re.compile(r"[A-Za-z%]+")
FUNCTIONS = {"ma": 2, "lag": 2, "chg": 2, "yoy": 1, "log": 1}


class ExpressionError(WatchStreetError):
    """The formula cannot be read or would combine things that do not fit."""


@dataclass(frozen=True)
class Operand:
    points: Points
    unit: str


@dataclass
class Result:
    points: Points
    unit: str
    terms: list[str] = field(default_factory=list)  # series names used, in order of appearance
    dropped: int = 0  # days of the longest input that have no value in the result


@dataclass(frozen=True)
class Num:
    value: float


@dataclass(frozen=True)
class Name:
    name: str


@dataclass(frozen=True)
class Call:
    name: str
    arg: "Node"
    count: int


@dataclass(frozen=True)
class Bin:
    op: str
    left: "Node"
    right: "Node"


Node = Num | Name | Call | Bin


def _tokens(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for number, name, other in TOKEN.findall(text):
        if number:
            out.append(("num", number))
        elif name:
            out.append(("name", name))
        elif other.strip():
            out.append(("op", other))
    return out


class _Parser:
    def __init__(self, text: str) -> None:
        if len(text) > EXPRESSION_MAX_CHARS:
            raise ExpressionError(f"Formel zu lang (höchstens {EXPRESSION_MAX_CHARS} Zeichen)")
        self.tokens = _tokens(text)
        self.pos = 0
        self.nodes = 0

    def _peek(self) -> tuple[str, str]:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else ("end", "")

    def _take(self) -> tuple[str, str]:
        token = self._peek()
        self.pos += 1
        self.nodes += 1
        if self.nodes > EXPRESSION_MAX_NODES:
            raise ExpressionError("Formel zu verschachtelt")
        return token

    def _expect(self, symbol: str) -> None:
        if self._take() != ("op", symbol):
            raise ExpressionError(f"„{symbol}“ erwartet")

    def parse(self) -> Node:
        if not self.tokens:
            raise ExpressionError("Leere Formel")
        node = self._sum()
        if self._peek()[0] != "end":
            raise ExpressionError(f"Unerwartetes Zeichen „{self._peek()[1]}“")
        return node

    def _sum(self) -> Node:
        node = self._product()
        while self._peek() in (("op", "+"), ("op", "-")):
            node = Bin(self._take()[1], node, self._product())
        return node

    def _product(self) -> Node:
        node = self._atom()
        while self._peek() in (("op", "*"), ("op", "/")):
            node = Bin(self._take()[1], node, self._atom())
        return node

    def _atom(self) -> Node:
        kind, text = self._take()
        if kind == "num":
            return Num(float(text))
        if (kind, text) == ("op", "("):
            node = self._sum()
            self._expect(")")
            return node
        if (kind, text) == ("op", "-"):
            return Bin("*", Num(-1.0), self._atom())
        if kind != "name":
            raise ExpressionError(
                f"Unerwartetes Zeichen „{text}“" if text else "Formel unvollständig"
            )
        if self._peek() != ("op", "("):
            return Name(text)
        if text not in FUNCTIONS:
            raise ExpressionError(f"Unbekannte Funktion „{text}“ (bekannt: {', '.join(FUNCTIONS)})")
        self._take()
        args = [self._sum()]
        while self._peek() == ("op", ","):
            self._take()
            args.append(self._sum())
        self._expect(")")
        if len(args) != FUNCTIONS[text]:
            raise ExpressionError(f"{text}() braucht {FUNCTIONS[text]} Angabe(n)")
        return Call(text, args[0], _count(args[1]) if len(args) > 1 else 0)


def _align(first: Points, second: Points, op: str) -> Points:
    other = dict(second)
    out: Points = []
    for day, value in first:
        if day not in other:
            continue
        b = other[day]
        if op == "+":
            out.append((day, value + b))
        elif op == "-":
            out.append((day, value - b))
        elif op == "*":
            out.append((day, value * b))
        elif b != 0:
            out.append((day, value / b))
    return out


def _unit(op: str, first: str, second: str) -> str:
    if op in "+-":
        if first != second:
            raise ExpressionError(
                f"Einheiten passen nicht zusammen: „{first}“ und „{second}“ lassen sich nicht "
                "addieren oder abziehen"
            )
        return first
    if op == "/":
        return _quotient(first, second)
    return f"{first} × {second}"


def _fraction(unit: str) -> tuple[str, str] | None:
    """'USD/oz' -> ('USD', 'oz'); 'USD' -> ('USD', ''); anything with spaces is not simple."""
    top, _, bottom = unit.partition("/")
    simple = SIMPLE_UNIT.fullmatch(top) and (not bottom or SIMPLE_UNIT.fullmatch(bottom))
    return (top, bottom) if simple else None


def _quotient(first: str, second: str) -> str:
    """Unit of a ratio; equal parts cancel, so USD ÷ USD/lb is 'lb' and USD/oz ÷ USD/oz a ratio."""
    if first == second:
        return RATIO_UNIT
    a, b = _fraction(first), _fraction(second)
    if a is None or b is None:
        return f"{first} je {second}"
    top, bottom = [a[0], b[1]], [a[1], b[0]]
    for part in list(top):
        if part in bottom:
            top.remove(part)
            bottom.remove(part)
    numerator = " · ".join(p for p in top if p)
    denominator = " · ".join(p for p in bottom if p)
    if not denominator:
        return numerator or RATIO_UNIT
    return f"{numerator or '1'} je {denominator}"


def _scalar(op: str, value: float, number: float, *, number_first: bool) -> float | None:
    a, b = (number, value) if number_first else (value, number)
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    return a / b if b != 0 else None


def _count(node: Node) -> int:
    if not isinstance(node, Num) or node.value < 1 or node.value != int(node.value):
        raise ExpressionError("Die zweite Angabe muss eine ganze Zahl von Beobachtungen sein")
    return int(node.value)


def _year_over_year(points: Points) -> Points:
    days = [d for d, _ in points]
    out: Points = []
    for day, value in points:
        target = day - timedelta(days=round(DAYS_PER_YEAR))
        index = bisect_right(days, target) - 1
        if index < 0 or (target - days[index]).days > SERIES_MAX_GAP_DAYS:
            continue
        before = points[index][1]
        if before:
            out.append((day, (value / before - 1) * PERCENT))
    return out


def _call(name: str, points: Points, unit: str, count: int) -> Operand:
    if name == "yoy":
        return Operand(_year_over_year(points), PERCENT_UNIT)
    if name == "log":
        return Operand([(d, math.log(v)) for d, v in points if v > 0], f"ln({unit})")
    if name == "ma":
        values = [v for _, v in points]
        out = [
            (points[i][0], sum(values[i - count + 1 : i + 1]) / count)
            for i in range(count - 1, len(points))
        ]
        return Operand(out, unit)
    if name == "lag":
        return Operand(
            [(points[i][0], points[i - count][1]) for i in range(count, len(points))], unit
        )
    out = [
        (points[i][0], (points[i][1] / points[i - count][1] - 1) * PERCENT)
        for i in range(count, len(points))
        if points[i - count][1]
    ]
    return Operand(out, PERCENT_UNIT)


def _with_number(op: str, series: Operand, number: float, *, number_first: bool) -> Operand:
    if op in "+-" and series.unit not in (PERCENT_UNIT, RATIO_UNIT):
        raise ExpressionError(
            f"Eine Zahl ohne Einheit lässt sich nicht zu „{series.unit}“ addieren"
        )
    points = [
        (d, out)
        for d, v in series.points
        if (out := _scalar(op, v, number, number_first=number_first)) is not None
    ]
    unit = f"1 je {series.unit}" if op == "/" and number_first else series.unit
    return Operand(points, unit)


def _binary(op: str, left: Operand | float, right: Operand | float) -> Operand | float:
    if isinstance(left, Operand) and isinstance(right, Operand):
        return Operand(_align(left.points, right.points, op), _unit(op, left.unit, right.unit))
    if isinstance(left, Operand):
        return _with_number(op, left, float(right), number_first=False)  # type: ignore[arg-type]
    if isinstance(right, Operand):
        return _with_number(op, right, left, number_first=True)
    value = _scalar(op, left, right, number_first=False)
    if value is None:
        raise ExpressionError("Division durch null")
    return value


def evaluate(text: str, resolve: Callable[[str], Operand]) -> Result:
    """Evaluate a formula. ``resolve`` raises ``ExpressionError`` for an unknown name."""
    terms: list[str] = []
    longest = 0

    def walk(node: Node) -> Operand | float:
        nonlocal longest
        if isinstance(node, Num):
            return node.value
        if isinstance(node, Name):
            operand = resolve(node.name)
            if node.name not in terms:
                terms.append(node.name)
            longest = max(longest, len(operand.points))
            return operand
        if isinstance(node, Call):
            inner = walk(node.arg)
            if not isinstance(inner, Operand):
                raise ExpressionError(f"{node.name}() braucht eine Reihe, keine Zahl")
            return _call(node.name, inner.points, inner.unit, node.count)
        return _binary(node.op, walk(node.left), walk(node.right))

    result = walk(_Parser(text).parse())
    if not isinstance(result, Operand):
        raise ExpressionError("Die Formel enthält keine Reihe")
    return Result(result.points, result.unit, terms, max(longest - len(result.points), 0))
