"""Deterministic PER arithmetic; values and evidence are supplied by the caller.

This module neither reads case documents nor decides whether a valuation is fair.
Financial amounts use million KRW, share counts use individual shares, and prices
use KRW per share. A missing or invalid peer is never silently dropped.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from typing import Any, Callable

PRECISION = 40
MILLION = Decimal("1000000")
_NUMBER = re.compile(r"^[+-]?(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]+)?$")


class InputProblem(ValueError):
    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status


def _number(value: Any, name: str, *, zero_allowed: bool = False,
            integer: bool = False) -> Decimal:
    if value is None:
        raise InputProblem("UNAVAILABLE", f"{name}: 입력값이 없습니다.")
    if not isinstance(value, str):
        raise InputProblem("INVALID", f"{name}: 숫자는 문자열로 전달해야 합니다.")
    value = value.strip()
    if not value:
        raise InputProblem("UNAVAILABLE", f"{name}: 입력값이 비어 있습니다.")
    if len(value) > 80 or not _NUMBER.fullmatch(value):
        raise InputProblem("INVALID", f"{name}: 유한한 십진수 형식이 아닙니다.")
    try:
        result = Decimal(value.replace(",", ""))
    except InvalidOperation as exc:
        raise InputProblem("INVALID", f"{name}: 숫자로 읽을 수 없습니다.") from exc
    if not result.is_finite():
        raise InputProblem("INVALID", f"{name}: 유한한 수가 아닙니다.")
    if result < 0 or (result == 0 and not zero_allowed):
        condition = "0 이상" if zero_allowed else "0보다 큰 값"
        raise InputProblem("INVALID", f"{name}: {condition}이어야 합니다.")
    if integer and result != result.to_integral_value():
        raise InputProblem("INVALID", f"{name}: 주식수는 정수여야 합니다.")
    return result


def _text(value: Decimal) -> str:
    # Decimal.normalize() uses the ambient context. Avoid it so caller context
    # cannot change a saved calculation after the local context has closed.
    value_text = format(value, "f")
    return value_text.rstrip("0").rstrip(".") if "." in value_text else value_text


def _get(inputs: dict[str, Any], key: str) -> Decimal:
    return _number(inputs.get(key), key,
                   zero_allowed=key in {"existing_shares", "new_shares", "dilutive_shares", "secondary_sale_shares"},
                   integer=key.endswith("shares") or key == "share_count")


def _peers(inputs: dict[str, Any]) -> list[dict[str, Any]]:
    peers = inputs.get("peers")
    if peers is None or peers == []:
        raise InputProblem("UNAVAILABLE", "비교기업 목록이 없습니다.")
    if not isinstance(peers, list) or any(not isinstance(peer, dict) for peer in peers):
        raise InputProblem("INVALID", "비교기업 목록은 객체의 배열이어야 합니다.")
    names = [peer.get("name") for peer in peers]
    if any(not isinstance(name, str) or not name.strip() for name in names):
        raise InputProblem("INVALID", "모든 비교기업에 이름이 있어야 합니다.")
    if len({name.strip().casefold() for name in names}) != len(names):
        raise InputProblem("INVALID", "비교기업 이름이 중복되어 있습니다.")
    return peers


def _peer_values(inputs: dict[str, Any], *, recomputed: bool = False) -> list[Decimal]:
    values = []
    problems = []
    for peer in _peers(inputs):
        try:
            if recomputed:
                numerator = _number(peer.get("market_cap_million_krw"), f"{peer['name']}.market_cap_million_krw")
                denominator = _number(peer.get("earnings_million_krw"), f"{peer['name']}.earnings_million_krw")
                values.append(numerator / denominator)
            else:
                values.append(_number(peer.get("per"), f"{peer['name']}.per"))
        except InputProblem as exc:
            problems.append(exc)
    if problems:
        status = "INVALID" if any(p.status == "INVALID" for p in problems) else "UNAVAILABLE"
        raise InputProblem(status, "일부 기업을 임의로 제외하지 않았습니다. " + " / ".join(map(str, problems)))
    return values


def _mean(values: list[Decimal]) -> Decimal:
    return sum(values, Decimal(0)) / Decimal(len(values))


def _median(values: list[Decimal]) -> Decimal:
    ordered = sorted(values)
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / Decimal(2)


def _item(identifier: str, label: str, formula: str, used_inputs: dict[str, Any],
          unit: str, operation: Callable[[], Decimal]) -> dict[str, Any]:
    item = {
        "id": identifier, "label": label, "formula": formula,
        "inputs": used_inputs, "result": None, "unit": unit,
        "status": "OK", "reason": None,
        "precision": {"decimal_digits": PRECISION, "rounding": "ROUND_HALF_EVEN",
                      "rounded_to_currency_unit": False},
    }
    try:
        with localcontext() as context:
            context.prec = PRECISION
            context.rounding = ROUND_HALF_EVEN
            item["result"] = _text(operation())
    except InputProblem as exc:
        item.update(status=exc.status, reason=str(exc))
    return item


def _used(inputs: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {key: inputs.get(key) for key in keys}


def calculate(inputs: dict[str, Any]) -> dict[str, Any]:
    """Return reproducible calculations without correcting or filling inputs."""
    if not isinstance(inputs, dict):
        raise TypeError("inputs must be a dictionary")
    rows: list[dict[str, Any]] = []

    def add(identifier: str, label: str, formula: str, keys: tuple[str, ...],
            unit: str, operation: Callable[[], Decimal]) -> None:
        rows.append(_item(identifier, label, formula, _used(inputs, *keys), unit, operation))

    components = ("existing_shares", "new_shares", "dilutive_shares")
    def share_sum() -> Decimal:
        # A known secondary sale must be a valid share count, even though it is
        # excluded from the sum. Its absence does not prevent this calculation.
        if inputs.get("secondary_sale_shares") is not None:
            _get(inputs, "secondary_sale_shares")
        return sum((_get(inputs, key) for key in components), Decimal(0))
    reported_price = lambda: _get(inputs, "reported_equity_million_krw") * MILLION / _get(inputs, "share_count")
    displayed_price = lambda: _get(inputs, "earnings_million_krw") * MILLION * _get(inputs, "applied_per") / _get(inputs, "share_count")
    add("share_sum", "평가에 사용하는 주식수의 합계", "existing_shares + new_shares + dilutive_shares; secondary_sale_shares is excluded",
        components + ("secondary_sale_shares",), "shares", share_sum)
    add("share_count_difference", "주식수 합계와 공시 주식수의 차이", "share_sum - share_count", components + ("secondary_sale_shares", "share_count"), "shares",
        lambda: share_sum() - _get(inputs, "share_count"))
    add("price_from_reported_equity", "공시된 주식가치를 주식수로 나눈 가격", "reported_equity_million_krw * 1000000 / share_count",
        ("reported_equity_million_krw", "share_count"), "KRW/share", reported_price)
    add("price_from_displayed_per", "이익과 표시 배수로 다시 계산한 가격", "earnings_million_krw * 1000000 * applied_per / share_count",
        ("earnings_million_krw", "applied_per", "share_count"), "KRW/share", displayed_price)
    add("reported_price_difference", "공시 가치에서 계산한 가격과 공시 가격의 차이", "price_from_reported_equity - reported_price_krw",
        ("reported_equity_million_krw", "share_count", "reported_price_krw"), "KRW/share",
        lambda: reported_price() - _get(inputs, "reported_price_krw"))
    add("displayed_price_difference", "표시 배수에서 계산한 가격과 공시 가격의 차이", "price_from_displayed_per - reported_price_krw",
        ("earnings_million_krw", "applied_per", "share_count", "reported_price_krw"), "KRW/share",
        lambda: displayed_price() - _get(inputs, "reported_price_krw"))
    add("implied_per", "공시된 주식가치에서 거꾸로 계산한 배수", "reported_equity_million_krw / earnings_million_krw",
        ("reported_equity_million_krw", "earnings_million_krw"), "multiple",
        lambda: _get(inputs, "reported_equity_million_krw") / _get(inputs, "earnings_million_krw"))
    add("peer_displayed_mean", "비교기업의 표시 배수 평균", "sum(peer.per) / count(peers)", ("peers",), "multiple",
        lambda: _mean(_peer_values(inputs)))
    add("peer_displayed_median", "비교기업의 표시 배수 중앙값", "median(peer.per)", ("peers",), "multiple",
        lambda: _median(_peer_values(inputs)))

    raw_peers = inputs.get("peers")
    if isinstance(raw_peers, list):
        for index, peer in enumerate(raw_peers):
            if not isinstance(peer, dict):
                continue  # The aggregate calculation reports this malformed list.
            name = peer.get("name", f"peer_{index + 1}")
            rows.append(_item(
                f"peer_recomputed_per_{index + 1}", f"{name}: 시가총액과 이익으로 다시 계산한 배수",
                "market_cap_million_krw / earnings_million_krw", dict(peer), "multiple",
                lambda peer=peer: _number(peer.get("market_cap_million_krw"), "market_cap_million_krw") / _number(peer.get("earnings_million_krw"), "earnings_million_krw"),
            ))
    add("peer_recomputed_mean", "개별 기업에서 다시 계산한 배수의 평균", "mean(peer.market_cap_million_krw / peer.earnings_million_krw)", ("peers",), "multiple",
        lambda: _mean(_peer_values(inputs, recomputed=True)))
    add("price_from_recomputed_peer_mean", "다시 계산한 비교기업 평균 배수를 적용한 가격", "earnings_million_krw * 1000000 * peer_recomputed_mean / share_count",
        ("earnings_million_krw", "share_count", "peers"), "KRW/share",
        lambda: _get(inputs, "earnings_million_krw") * MILLION * _mean(_peer_values(inputs, recomputed=True)) / _get(inputs, "share_count"))
    return {
        "calculations": rows,
        "notes": [
            "이 계산은 전달받은 숫자를 사용합니다. 숫자의 출처와 적용 여부는 별도로 확인해야 합니다.",
            "구주매출은 기존 주식의 소유자가 바뀌는 거래이므로 주식수 합계에 더하지 않습니다.",
            "표시된 배수나 금액의 반올림 때문에 차이가 날 수 있습니다. 차이만으로 공시 오류라고 판정하지 않습니다.",
            "비교기업 값이 빠지거나 잘못되면 그 기업을 빼고 평균을 내지 않습니다.",
        ],
    }


def sensitivity(inputs: dict[str, Any]) -> dict[str, Any]:
    """Apply explicit arithmetic alternatives, not investment recommendations."""
    if not isinstance(inputs, dict):
        raise TypeError("inputs must be a dictionary")
    keys = ("earnings_million_krw", "applied_per", "share_count")
    baseline = _item("baseline", "공시에 표시된 적용 배수로 계산한 기준 가격",
                     "earnings_million_krw * 1000000 * applied_per / share_count",
                     _used(inputs, *keys), "KRW/share",
                     lambda: _get(inputs, "earnings_million_krw") * MILLION * _get(inputs, "applied_per") / _get(inputs, "share_count"))
    scenarios: list[dict[str, Any]] = []

    def scenario(identifier: str, label: str, formula: str,
                 multiple: Callable[[], Decimal], excluded_peer: str | None = None) -> None:
        item = _item(identifier, label, formula, _used(inputs, *keys, "peers"), "KRW/share",
                     lambda: _get(inputs, "earnings_million_krw") * MILLION * multiple() / _get(inputs, "share_count"))
        item.update(assumption="계산상 대안이며 실제로 이 배수를 적용해야 한다는 뜻은 아닙니다.",
                    excluded_peer=excluded_peer, applied_per=None,
                    difference_krw=None, difference_percent=None,
                    comparison_status="UNAVAILABLE", comparison_reason=None)
        if item["status"] == "OK":
            with localcontext() as context:
                context.prec = PRECISION
                context.rounding = ROUND_HALF_EVEN
                item["applied_per"] = _text(multiple())
                if baseline["status"] == "OK":
                    difference = Decimal(item["result"]) - Decimal(baseline["result"])
                    item["difference_krw"] = _text(difference)
                    item["difference_percent"] = _text(difference / Decimal(baseline["result"]) * Decimal(100))
                    item["comparison_status"] = "OK"
        if item["comparison_status"] != "OK":
            item["comparison_reason"] = "기준 가격이나 대안 가격을 계산할 수 없어 차이를 계산하지 않았습니다."
        scenarios.append(item)

    scenario("displayed_mean", "비교기업의 표시 배수 평균을 적용", "earnings_million_krw * 1000000 * mean(peer.per) / share_count",
             lambda: _mean(_peer_values(inputs)))
    scenario("displayed_median", "비교기업의 표시 배수 중앙값을 적용", "earnings_million_krw * 1000000 * median(peer.per) / share_count",
             lambda: _median(_peer_values(inputs)))
    try:
        peers = _peers(inputs)
    except InputProblem:
        peers = []  # Mean and median already retain the problem explicitly.
    for index, peer in enumerate(peers):
        def excluded_mean(index: int = index) -> Decimal:
            values = _peer_values(inputs)  # Validate all peers, including the omitted one.
            remaining = values[:index] + values[index + 1:]
            if not remaining:
                raise InputProblem("UNAVAILABLE", "한 기업을 제외하면 비교기업이 남지 않습니다.")
            return _mean(remaining)
        scenario(f"exclude_peer_{index + 1}", f"{peer['name']} 한 곳을 제외한 표시 배수 평균을 적용",
                 "earnings_million_krw * 1000000 * mean(remaining peer.per) / share_count",
                 excluded_mean, excluded_peer=peer["name"])
    return {
        "baseline": baseline, "scenarios": scenarios,
        "notes": [
            "차이는 공시에 표시된 적용 배수로 재계산한 기준 가격에 대한 값입니다. 공시 가격 자체와 비교한 값이 아닙니다.",
            "평균, 중앙값, 기업 한 곳을 제외한 평균은 계산 결과가 얼마나 달라지는지 보기 위한 가정입니다.",
            "어느 기업을 제외하거나 어느 배수를 선택할지는 사업 특성과 근거를 검토한 뒤 판단해야 합니다.",
        ],
    }
