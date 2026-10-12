"""Transparent Gaussian log-return baseline and conservative entry screening."""

from dataclasses import asdict, dataclass
from math import erf, isfinite, log, sqrt


def number(value: object, label: str, low: float = 0, high: float = float("inf")) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number")
    result = float(value)
    if not isfinite(result) or not low <= result <= high:
        raise ValueError(f"{label} must be finite and in [{low}, {high}]")
    return result


def probability_up(spot: float, reference: float, sigma: float, seconds: float) -> float:
    """P(log(S_T/reference) >= 0), assuming zero expected log return.

    sigma is log-return volatility per sqrt(second), NOT annualized volatility.
    A tie at expiry resolves Up. This is a baseline, not a calibrated forecast.
    """
    spot = number(spot, "spot", 1e-12)
    reference = number(reference, "reference", 1e-12)
    sigma = number(sigma, "sigma", 1e-12)
    seconds = number(seconds, "seconds")
    if seconds == 0:
        return float(spot >= reference)
    z = log(spot / reference) / (sigma * sqrt(seconds))
    return (1 + erf(z / sqrt(2))) / 2


def estimate_sigma(ticks: list[tuple[float, float]], min_returns: int = 30) -> float:
    """Realized RMS log returns over elapsed seconds; use ONLY past same-source ticks."""
    if len(ticks) < min_returns + 1:
        raise ValueError("insufficient volatility history")
    squared_returns = 0.0
    elapsed = 0.0
    for (t0, p0), (t1, p1) in zip(ticks, ticks[1:]):
        t0, t1 = number(t0, "timestamp"), number(t1, "timestamp")
        p0, p1 = number(p0, "price", 1e-12), number(p1, "price", 1e-12)
        if t1 <= t0:
            raise ValueError("ticks must have strictly increasing timestamps")
        squared_returns += log(p1 / p0) ** 2
        elapsed += t1 - t0
    sigma = sqrt(squared_returns / elapsed)
    if sigma == 0:
        raise ValueError("zero volatility history")
    return sigma


@dataclass(frozen=True)
class Config:
    shares: float = 10
    max_age_seconds: float = 3
    min_seconds_remaining: float = 15
    min_edge: float = 0.03
    uncertainty_margin: float = 0.02
    slippage_per_share: float = 0.005
    max_cost: float = 10

    def __post_init__(self):
        for name, value in asdict(self).items():
            number(value, name, 1e-12 if name in {"shares", "max_cost"} else 0)


def fill_cost(book: dict, shares: float, rate: float, slippage: float) -> dict:
    """Sweep asks in price order; calculate fees at each consumed price level.

    Only the currently documented exponent-one fee schedule is supported.
    Slippage is an additional dollar-per-share research allowance.
    """
    shares = number(shares, "shares", 1e-12)
    rate = number(rate, "fee_rate", 0, 1)
    slippage = number(slippage, "slippage")
    minimum = number(book["min_order_size"], "min_order_size", 1e-12)
    if shares < minimum:
        raise ValueError("below minimum order size")
    levels = []
    for level in book["asks"]:
        p = number(level["price"], "ask price", 1e-12, 1 - 1e-12)
        size = number(level["size"], "ask size")
        levels.append((p, size))
    remaining, notional, fee = shares, 0.0, 0.0
    for price, size in sorted(levels):
        take = min(remaining, size)
        notional += take * price
        fee += take * rate * price * (1 - price)
        remaining -= take
        if remaining <= 1e-9:
            break
    if remaining > 1e-9:
        raise ValueError("insufficient ask depth")
    total = notional + fee + shares * slippage
    if total >= shares:
        raise ValueError("all-in share cost reaches payout")
    return {"vwap": notional / shares, "fee": fee, "cost": total,
            "cost_per_share": total / shares}


def evaluate(snapshot: dict, config: Config = Config()) -> dict:
    """Evaluate at snapshot.timestamp. Malformed or incomplete data fails closed."""
    result = {"market_id": snapshot.get("market_id"),
              "timestamp": snapshot.get("timestamp"), "decision": "NO_TRADE"}
    try:
        if not isinstance(snapshot.get("market_id"), str) or not snapshot["market_id"]:
            raise ValueError("missing market identity")
        now = number(snapshot["timestamp"], "timestamp")
        start = number(snapshot["window_start"], "window_start")
        end = number(snapshot["window_end"], "window_end")
        if end - start != 900:
            raise ValueError("window must be exactly 15 minutes")
        if not start <= now < end:
            raise ValueError("outside market window")
        if end - now < config.min_seconds_remaining:
            raise ValueError("too close to expiry")
        if snapshot.get("reference_verified") is not True:
            raise ValueError("opening reference not verified")
        if snapshot.get("price_source") != "chainlink_btc_usd":
            raise ValueError("price source does not match supported settlement source")
        age = now - number(snapshot["price_timestamp"], "price_timestamp")
        if not 0 <= age <= config.max_age_seconds:
            raise ValueError("stale or future BTC tick")
        p_up = probability_up(snapshot["spot"], snapshot["reference"],
                              snapshot["sigma_per_sqrt_second"], end - now)
        result["probability_up"] = p_up
        candidates, rejected = [], []
        for side, probability in (("UP", p_up), ("DOWN", 1 - p_up)):
            try:
                book = snapshot["books"][side]
                if book["market_id"] != snapshot["market_id"]:
                    raise ValueError("order book market mismatch")
                age = now - number(book["timestamp"], "book timestamp")
                if not 0 <= age <= config.max_age_seconds:
                    raise ValueError("stale or future book")
                if book.get("fee_verified") is not True:
                    raise ValueError("fee schedule not verified")
                if book.get("fee_exponent") != 1:
                    raise ValueError("unsupported fee exponent")
                fill = fill_cost(book, config.shares, book["fee_rate"], config.slippage_per_share)
                if fill["cost"] > config.max_cost:
                    raise ValueError("paper position cost limit exceeded")
                edge = probability - fill["cost_per_share"]
                candidates.append({"side": side, "probability": probability,
                                   "net_edge": edge, "shares": config.shares, **fill})
            except (KeyError, ValueError, TypeError) as exc:
                rejected.append(f"{side}: {exc}")
        result["candidates"] = candidates
        result["rejected"] = rejected
        best = max(candidates, key=lambda c: c["net_edge"], default=None)
        if best and best["net_edge"] >= config.min_edge + config.uncertainty_margin:
            result.update(decision=f"PAPER_{best['side']}", entry=best,
                          reason="estimated edge clears costs and uncertainty buffer")
        else:
            result["reason"] = "no eligible entry clears edge threshold"
    except (KeyError, ValueError, TypeError, OverflowError) as exc:
        result["reason"] = str(exc)
    return result
