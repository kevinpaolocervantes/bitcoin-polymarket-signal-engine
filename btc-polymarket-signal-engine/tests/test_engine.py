import copy
import json
import math
import unittest
from pathlib import Path
from unittest.mock import patch

from btc_signal.engine import Config, estimate_sigma, evaluate, fill_cost, probability_up
from btc_signal.paper import replay
from btc_signal.polymarket import capture_market

ROOT = Path(__file__).resolve().parents[1]


def example():
    return json.loads((ROOT / "examples/snapshot.json").read_text())


class EngineTests(unittest.TestCase):
    def test_probability_at_reference_is_half(self):
        self.assertEqual(probability_up(100, 100, 0.001, 100), 0.5)

    def test_probability_moves_with_distance_and_time(self):
        self.assertGreater(probability_up(101, 100, 0.001, 10),
                           probability_up(101, 100, 0.001, 100))
        self.assertLess(probability_up(99, 100, 0.001, 10), 0.5)

    def test_expiry_tie_is_up(self):
        self.assertEqual(probability_up(100, 100, 0.001, 0), 1)
        self.assertEqual(probability_up(99, 100, 0.001, 0), 0)

    def test_reject_bad_model_inputs(self):
        for sigma in [0, -1, float("nan"), float("inf")]:
            with self.assertRaises(ValueError):
                probability_up(100, 100, sigma, 100)

    def test_volatility_units_with_irregular_ticks(self):
        ticks = [(0, 100), (1, 100 * math.exp(0.01)), (4, 100)]
        self.assertAlmostEqual(estimate_sigma(ticks, min_returns=2), math.sqrt(0.0002 / 4))
        with self.assertRaises(ValueError):
            estimate_sigma([(0, 100), (0, 101)], min_returns=1)

    def test_depth_and_fees_calculated_per_level(self):
        book = {"min_order_size": 1, "asks": [{"price": 0.6, "size": 5},
                                                {"price": 0.5, "size": 5}]}
        fill = fill_cost(book, 10, 0.07, 0.005)
        self.assertAlmostEqual(fill["vwap"], 0.55)
        self.assertAlmostEqual(fill["fee"], 5 * 0.07 * (0.25 + 0.24))
        self.assertAlmostEqual(fill["cost"], 5.5 + fill["fee"] + 0.05)

    def test_no_trade_when_depth_missing_or_below_minimum(self):
        book = {"min_order_size": 5, "asks": [{"price": 0.5, "size": 6}]}
        for shares in [1, 10]:
            with self.assertRaises(ValueError):
                fill_cost(book, shares, 0.07, 0.005)

    def test_synthetic_signal_and_no_trade_at_fair_prices(self):
        s = example()
        self.assertEqual(evaluate(s)["decision"], "PAPER_UP")
        s["spot"] = s["reference"]
        for book in s["books"].values():
            book["asks"] = [{"price": 0.51, "size": 100}]
        self.assertEqual(evaluate(s)["decision"], "NO_TRADE")

    def test_stale_future_and_unverified_price_rejected(self):
        for field, value in [("price_timestamp", 1791765600),
                             ("price_timestamp", 1791766010),
                             ("reference_verified", False),
                             ("price_source", "binance"),
                             ("sigma_per_sqrt_second", 0)]:
            s = example()
            s[field] = value
            self.assertEqual(evaluate(s)["decision"], "NO_TRADE")

    def test_market_and_fee_identity_checks(self):
        for field, value in [("market_id", "wrong"), ("fee_verified", False),
                             ("fee_exponent", 2), ("timestamp", 1)]:
            s = example()
            for book in s["books"].values():
                book[field] = value
            self.assertEqual(evaluate(s)["decision"], "NO_TRADE")

    def test_expired_and_wrong_duration_rejected(self):
        s = example()
        s["timestamp"] = s["window_end"]
        self.assertEqual(evaluate(s)["decision"], "NO_TRADE")
        s = example()
        s["window_end"] += 1
        self.assertEqual(evaluate(s)["decision"], "NO_TRADE")

    def test_cost_limit(self):
        self.assertEqual(evaluate(example(), Config(max_cost=1))["decision"], "NO_TRADE")


class PaperTests(unittest.TestCase):
    def outcomes(self, outcome="UP"):
        s = example()
        return {s["market_id"]: {"outcome": outcome, "verified": True,
                                  "resolved_at": s["window_end"] + 60}}

    def test_one_entry_per_market_and_pnl(self):
        s = example()
        report = replay([s, copy.deepcopy(s)], self.outcomes())
        self.assertEqual(report["settled_trades"], 1)
        cost = report["trades"][0]["cost"]
        self.assertAlmostEqual(report["realized_pnl"], 10 - cost)
        self.assertAlmostEqual(report["cash"], 1000 + 10 - cost)

    def test_losing_trade_and_label_independence(self):
        win = replay([example()], self.outcomes("UP"))
        lose = replay([example()], self.outcomes("DOWN"))
        self.assertEqual(win["decisions"], lose["decisions"])
        self.assertAlmostEqual(lose["realized_pnl"], -lose["trades"][0]["cost"])

    def test_unresolved_trade_not_counted_as_loss(self):
        report = replay([example()], {})
        self.assertEqual(report["settled_trades"], 0)
        self.assertEqual(report["unresolved_trades"], 1)
        self.assertIsNone(report["win_rate"])
        self.assertEqual(report["realized_pnl"], 0)
        self.assertGreater(report["unresolved_cost"], 0)

    def test_bad_settlement_and_nonchronological_replay(self):
        outcomes = self.outcomes()
        outcomes[example()["market_id"]]["resolved_at"] = 0
        with self.assertRaises(ValueError):
            replay([example()], outcomes)
        earlier = example()
        earlier["timestamp"] -= 1
        with self.assertRaises(ValueError):
            replay([example(), earlier], {})

    def test_cash_limit(self):
        report = replay([example()], self.outcomes(), starting_cash=1)
        self.assertEqual(report["settled_trades"], 0)
        self.assertEqual(report["cash"], 1)


class CaptureTests(unittest.TestCase):
    @patch("btc_signal.polymarket.get_json")
    def test_tokens_mapped_by_label(self, get):
        get.side_effect = [
            {"outcomes": '["Down", "Up"]', "clobTokenIds": '["2", "1"]', "conditionId": "m"},
            {"asset_id": "2", "market": "m"},
            {"asset_id": "1", "market": "m"},
        ]
        result = capture_market("test")
        self.assertEqual(result["books"]["UP"]["raw"]["asset_id"], "1")
        self.assertEqual(result["books"]["DOWN"]["raw"]["asset_id"], "2")

    @patch("btc_signal.polymarket.get_json")
    def test_book_identity_mismatch_rejected(self, get):
        get.side_effect = [{"outcomes": ["Up", "Down"], "clobTokenIds": ["1", "2"],
                            "conditionId": "m"}, {"asset_id": "1", "market": "wrong"}]
        with self.assertRaises(ValueError):
            capture_market("test")


if __name__ == "__main__":
    unittest.main()
