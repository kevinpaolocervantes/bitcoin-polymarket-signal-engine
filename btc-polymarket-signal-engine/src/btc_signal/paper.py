"""Replay snapshots chronologically; keep settlement labels outside the model."""

from math import log

from .engine import Config, evaluate, number


def replay(snapshots: list[dict], outcomes: dict, config: Config = Config(),
           starting_cash: float = 1000) -> dict:
    cash = number(starting_cash, "starting_cash", 1e-12)
    initial_cash, trades, decisions, seen = cash, [], [], set()
    previous = -1.0
    for snapshot in snapshots:
        timestamp = number(snapshot["timestamp"], "timestamp")
        if timestamp < previous:
            raise ValueError("snapshots must be chronological")
        previous = timestamp
        decision = evaluate(snapshot, config)
        decisions.append(decision)
        market_id = snapshot.get("market_id")
        if "entry" not in decision:
            continue
        if market_id in seen:
            decision.update(decision="NO_TRADE", reason="already entered this market")
            decision.pop("entry")
            continue
        entry = decision["entry"]
        if entry["cost"] > cash:
            decision.update(decision="NO_TRADE", reason="insufficient paper cash")
            decision.pop("entry")
            continue
        seen.add(market_id)
        cash -= entry["cost"]
        trades.append({"market_id": market_id, "timestamp": timestamp,
                       "window_end": snapshot["window_end"],
                       "probability_up": decision["probability_up"], **entry})
    # This conservative replay reserves cash for ALL entries until the end.
    # Outcomes never influence entry decisions or sizing.
    closed, unresolved_cost, pnl = [], 0.0, 0.0
    for trade in trades:
        settlement = outcomes.get(trade["market_id"])
        if settlement is None:
            unresolved_cost += trade["cost"]
            continue
        if (settlement.get("verified") is not True
                or settlement.get("outcome") not in {"UP", "DOWN"}
                or number(settlement.get("resolved_at"), "resolved_at") < trade["window_end"]):
            raise ValueError("invalid or unverified settlement")
        payout = trade["shares"] if trade["side"] == settlement["outcome"] else 0
        trade.update(outcome=settlement["outcome"], payout=payout,
                     pnl=payout - trade["cost"])
        cash += payout
        pnl += trade["pnl"]
        closed.append(trade)
    n = len(closed)
    brier = sum((t["probability_up"] - (t["outcome"] == "UP")) ** 2 for t in closed)
    loss = 0.0
    for trade in closed:
        p = min(1 - 1e-12, max(1e-12, trade["probability_up"]))
        loss -= log(p if trade["outcome"] == "UP" else 1 - p)
    cost = sum(t["cost"] for t in closed)
    return {"mode": "PAPER_REPLAY", "starting_cash": initial_cash,
            "cash": cash, "unresolved_cost": unresolved_cost, "realized_pnl": pnl,
            "roi_on_settled_cost": pnl / cost if cost else None,
            "settled_trades": n, "unresolved_trades": len(trades) - n,
            "win_rate": sum(t["payout"] > 0 for t in closed) / n if n else None,
            "brier_on_traded_markets": brier / n if n else None,
            "log_loss_on_traded_markets": loss / n if n else None,
            "trades": trades, "decisions": decisions}
