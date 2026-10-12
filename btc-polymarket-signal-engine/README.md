# BTC Polymarket Signal Engine

**A Python research engine for probability pricing in Bitcoin 15-minute Up/Down markets.**

The research question: can a transparent probability model identify mispriced
contracts after executable entry costs? The goal is measured expected value,
calibration, and realized net returns. A high win rate alone is insufficient.

**Status: v0.1 research prototype.** Offline signals and paper replay work. A
GET-only adapter captures public market metadata and order books. Continuous
BTC streaming, automatic reference verification, and order execution are not
implemented. No profitability or forecasting edge has been demonstrated.

## What works

- UP/DOWN probabilities using a Gaussian log-return baseline.
- Same-source realized-volatility estimator for timestamped past ticks.
- Entry costs calculated by sweeping ask depth, with fees at each consumed
  price level and an additional slippage allowance.
- `PAPER_UP`, `PAPER_DOWN`, or `NO_TRADE` decisions with reasons.
- Rejection of stale data, mismatched market identities, unverified references
  or fees, unsupported fee schedules, insufficient depth, and near-expiry entries.
- Chronological paper replay: one entry per market, cash limits, separate
  settlement labels, net P&L, ROI, Brier score, and log loss.
- Public Gamma/CLOB capture, unit tests, and GitHub Actions configuration.

There are no private keys, wallet connections, authenticated trading requests,
or order-submission functions in this version.

## Quick start

Python 3.11 or later. The research engine uses only the standard library.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
btc-signal signal examples/snapshot.json
btc-signal replay examples/snapshots.jsonl examples/outcomes.json
python -m unittest discover -s tests -v
```

If installation is unavailable, run directly from source:

```bash
PYTHONPATH=src python3 -m btc_signal signal examples/snapshot.json
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

**All files under `examples/` are synthetic fixtures.** Their prices, fees,
verification flags, and outcomes demonstrate behavior, not observed results.
The duplicate snapshot demonstrates the one-entry-per-market guard.

Override research parameters:

```bash
btc-signal signal examples/snapshot.json --config examples/config.json
```

## Public market capture

Provide the exact slug from the market you want to inspect:

```bash
btc-signal capture --slug ACTUAL_MARKET_SLUG --output data/books.jsonl --count 12 --interval 5
```

The command appends raw market metadata and both outcome books. It matches
tokens by outcome label and verifies returned book identities. A capture stays
on the supplied slug; automatic rollover is not implemented. Treat partial
output after an error as incomplete. Keep the active market and rules under review.

Raw captures are **not** normalized signal snapshots. This adapter does not
capture Chainlink BTC ticks or determine the official opening reference. A
separate feed adapter must assemble synchronized inputs before live signals
can be evaluated. Public requests have bounded timeouts, but retry/backoff,
connection recovery, and persistent stream supervision remain future work.
Network integration has been checked against official documentation and
fixture tests; successful live endpoint access was not verified in the build environment.

## Model and input contract

Under the baseline assumption that future log returns have zero mean and
standard deviation `sigma * sqrt(seconds_remaining)`:

```text
P(UP) = NormalCDF(log(current_price / opening_reference)
                 / (sigma * sqrt(seconds_remaining)))
```

This assumes Gaussian increments and constant short-horizon volatility. It
does not model jumps, regime changes, feed basis differences, oracle timing,
or latency. The output is an uncalibrated baseline probability. At expiry,
the helper uses the supported contract's tie rule: equal prices count as Up.
The signal screen does not enter at expiry.

Normalized snapshots use Unix timestamps **in seconds** and decimal prices
between zero and one. See `examples/snapshot.json` for the full schema.

| Field | Required meaning |
| --- | --- |
| `market_id` | Same market identity used by both books |
| `window_start`, `window_end` | Verified contract boundaries, exactly 900 seconds apart |
| `timestamp` | Collector decision time; replay evaluates using this clock |
| `spot`, `price_timestamp` | Last available supported settlement-source BTC tick |
| `reference` | Official opening reference for this exact market |
| `reference_verified` | True only after a feed adapter actually verifies it |
| `price_source` | `chainlink_btc_usd` for the supported market type |
| `sigma_per_sqrt_second` | Past-only log-return volatility per square-root second |
| `books.UP`, `books.DOWN` | Ask levels, source timestamp, minimum size, verified fee parameters |

Each book requires `market_id`, `timestamp`, `min_order_size`, `asks`,
`fee_rate`, `fee_exponent`, and `fee_verified`. Ask levels contain numeric
`price` and `size` fields. The prototype supports only fee exponent one:
`shares * fee_rate * price * (1-price)`.

Verification flags are an **input trust contract**, not an independent audit.
Never turn them on simply to obtain a signal. The future adapter must verify
market rules, reference provenance, fee parameters, and source timestamps.
Raw API strings and millisecond timestamps must be normalized explicitly.
For a verified fee-free market, use `fee_rate: 0`, exponent one, and the
verified flag. Unknown fees must remain unverified. No live fee is hardcoded.

The volatility estimator computes the square root of summed squared log
returns divided by elapsed seconds, requiring at least 30 returns by default.
Use a trailing window ending at or before decision time, and only ticks from
the supported price source. Sampling policy and lookback need validation.

## Decision and accounting

```text
net_edge = model_probability - all_in_cost_per_share
entry eligible when net_edge >= min_edge + uncertainty_margin
```

Defaults: ten shares, three-second maximum data age, no entries in the final
15 seconds, three percentage points of minimum net edge, a further two-point
uncertainty margin, half a cent per share of extra slippage allowance, and a
$10 maximum entry cost. These are research defaults, not recommended live
position sizes or evidence of an edge.

Paper fills sweep the captured asks, require the full requested depth, and
assume execution without queue competition or latency. Fees are modeled in
dollar terms without per-fill protocol rounding or share-denominated accounting.
Rebates are excluded. Simulated fills can therefore be optimistic even after
the extra slippage allowance. Uncertainty margins affect eligibility, not
realized P&L. Unrealized positions are listed separately and are not treated
as losses or valued at $1.

Replay reserves cash for every entry until the end of the run. It does not
recycle settlements during the input sequence, making capital accounting
conservative. It rejects nonchronological snapshots instead of silently sorting
them. Separate verified outcomes are applied only after entries are chosen;
each outcome needs `outcome`, `verified`, and `resolved_at >= window_end`.
This prevents settlement labels from entering the model, but the caller is
responsible for keeping volatility estimates and references free of future data.

Brier score and log loss in the replay report cover **traded markets only**.
They are not full-universe calibration metrics. Win rate also covers settled
trades only. Report sample count and time period with any performance metric.

## Research roadmap

1. Collect BTC settlement-source ticks and order books with source and receipt clocks.
2. Verify contract windows, reference prices, fee schedules, and market rollover.
3. Store every forecast, including `NO_TRADE`, and official settlement labels.
4. Evaluate complete-market calibration, time-to-expiry buckets, and market-price baselines.
5. Use chronological train/validation/test windows grouped by contract and day;
   freeze thresholds before testing, and simulate execution delay and adverse fills.
6. Consider automation only after repeatable out-of-sample net results and execution testing.

## GitHub publishing

You can publish from a laptop using GitHub's website without installing an
integration. Create the empty repository, then use **Add file > Upload files**
to upload the extracted project contents and commit them. Include `src/`,
`tests/`, `examples/`, `README.md`, and `pyproject.toml`. The `.github/` folder
contains CI and may be hidden by your file browser; use the terminal route
below to include all project files reliably.

Create an empty repository called `btc-polymarket-signal-engine` in your
GitHub account. Do not initialize a second README. From this folder:

```bash
git init -b main
git add .
git commit -m "Initial probability engine and paper-trading research prototype"
git remote add origin https://github.com/YOUR_USERNAME/btc-polymarket-signal-engine.git
git push -u origin main
```

Or, with an authenticated GitHub CLI and no existing remote:

```bash
gh repo create btc-polymarket-signal-engine --private --source=. --remote=origin --push
```

Choose repository visibility deliberately. An open-source license is not
included; select one before inviting reuse under an open-source license.

Suggested description: **Probability pricing, cost-aware signals, and paper-trading
research for Bitcoin 15-minute prediction markets.**

## Official references

Reviewed October 11, 2026. APIs, fee schedules, and feeds can change.

- [Polymarket API overview](https://docs.polymarket.com/api-reference/predictions/overview)
- [Market lookup by slug](https://docs.polymarket.com/api-reference/markets/get-market-by-slug)
- [Order book endpoint](https://docs.polymarket.com/api-reference/market-data/get-order-book)
- [Market details and fee parameters](https://docs.polymarket.com/market-data/market-details)
- [Fee formula](https://docs.polymarket.com/trading/fees)
- [Real-time feeds](https://docs.polymarket.com/market-data/realtime-data)
- [Example BTC 15-minute market rules](https://polymarket.com/event/btc-updown-15m-1791333000)

Read the exact market's current rules before constructing inputs. This project
is independent research and is not affiliated with Polymarket or Chainlink.
