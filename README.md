# BTC Polymarket Signal Engine

A Python research project for tracking and evaluating Bitcoin 15-minute Up/Down markets on Polymarket.

The engine compares its estimated probability of Bitcoin finishing **Up** or **Down** against the current market price, transaction fees, available liquidity, and estimated slippage.

Its purpose is not to force a prediction every 15 minutes. Its purpose is to identify potential pricing discrepancies and return **NO TRADE** when the estimated advantage is insufficient.

> Status: Research prototype with paper trading only. This version does not execute real-money trades.

## Core Idea

Every 15-minute market asks whether Bitcoin will finish above or below its opening reference price.

The engine evaluates:

- Current Bitcoin price
- Opening reference price
- Time remaining
- Short-term realized volatility
- Polymarket UP and DOWN prices
- Available order-book liquidity
- Trading fees
- Estimated slippage
- Model uncertainty

It then returns one of three decisions:

- `PAPER_UP`
- `PAPER_DOWN`
- `NO_TRADE`

## Why This Project Exists

Predicting Bitcoin’s direction is not enough.

A model can be directionally correct and still lose money if it consistently overpays for contracts. For example, winning 80% of trades does not create an edge if each contract costs $0.90.

The primary research question is:

> Can the model estimate probabilities more accurately than the market after fees, slippage, and uncertainty?

The most important metrics are therefore:

- Net expected value
- Realized profit and loss
- Return on capital
- Probability calibration
- Brier score
- Log loss
- Performance against market-implied probabilities

## Current Features

- Estimates the probability of Bitcoin finishing Up or Down
- Uses a transparent Gaussian log-return baseline
- Calculates short-term realized volatility from historical price ticks
- Reads available ask-side order-book depth
- Calculates estimated transaction fees
- Includes a configurable slippage allowance
- Rejects stale or incomplete data
- Rejects mismatched market and order-book identities
- Rejects unverified reference prices and fee schedules
- Avoids entries too close to market expiration
- Requires a minimum estimated edge before entering
- Prevents duplicate entries in the same market
- Supports chronological paper-trading replay
- Tracks simulated cash, profit, ROI, win rate, Brier score, and log loss
- Includes automated tests and GitHub Actions configuration
- Contains no wallet connection or real-money order execution

## Decision Logic

The baseline probability model estimates:

```text
P(UP) = NormalCDF(
    log(current_price / opening_reference)
    / (volatility × sqrt(seconds_remaining))
)
```

The engine then calculates:

```text
net_edge = model_probability - all_in_cost_per_share
```

A paper entry is eligible only when:

```text
net_edge >= minimum_edge + uncertainty_margin
```

Otherwise, the engine returns:

```text
NO_TRADE
```

## Default Risk Controls

The current research defaults include:

- 10 simulated shares per entry
- Maximum data age of 3 seconds
- No entries during the final 15 seconds
- Minimum net edge of 3 percentage points
- Additional uncertainty margin of 2 percentage points
- Slippage allowance of $0.005 per share
- Maximum simulated entry cost of $10
- One entry per market

These are experimental defaults, not recommended real-money position sizes.

## Project Structure

```text
btc-polymarket-signal-engine/
├── .github/
│   └── workflows/
│       └── tests.yml
├── examples/
│   ├── config.json
│   ├── outcomes.json
│   ├── snapshot.json
│   └── snapshots.jsonl
├── src/
│   └── btc_signal/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── engine.py
│       ├── paper.py
│       └── polymarket.py
├── tests/
│   └── test_engine.py
├── .gitignore
├── pyproject.toml
└── README.md
```

## Installation

Python 3.11 or newer is recommended.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

On Windows:

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e .
```

## Run a Sample Signal

```bash
btc-signal signal examples/snapshot.json
```

The included example is synthetic and exists only to demonstrate the engine’s behavior.

Example decision:

```json
{
  "decision": "PAPER_UP",
  "probability_up": 0.7989,
  "reason": "estimated edge clears costs and uncertainty buffer"
}
```

This is not a historical result or evidence of profitability.

## Run a Paper-Trading Replay

```bash
btc-signal replay examples/snapshots.jsonl examples/outcomes.json
```

The replay report includes:

- Starting and ending simulated cash
- Realized profit and loss
- ROI on settled trade costs
- Settled and unresolved trades
- Win rate
- Brier score
- Log loss
- Individual entry decisions

Settlement results are stored separately from signal inputs to help prevent future information from leaking into the model.

## Capture Public Polymarket Data

Provide the exact slug of the market you want to inspect:

```bash
btc-signal capture \
  --slug ACTUAL_MARKET_SLUG \
  --output data/books.jsonl \
  --count 12 \
  --interval 5
```

The capture command retrieves public market metadata and UP/DOWN order books.

It does not:

- Place orders
- Access a wallet
- Use private keys
- Determine the official opening reference automatically
- Capture a continuous Chainlink Bitcoin feed
- Automatically move to the next 15-minute market

Raw captures must be normalized and synchronized before they can be used as verified signal inputs.

## Run the Tests

```bash
python -m unittest discover -s tests -v
```

The current version includes 19 tests covering:

- Probability calculations
- Expiration behavior
- Volatility estimation
- Stale and future data rejection
- Market identity verification
- Fee verification
- Order-book depth
- Minimum order size
- Position cost limits
- Paper-trade accounting
- Duplicate market protection
- Settlement verification
- Chronological replay
- Outcome-label separation

## Research Limitations

The current model is intentionally simple.

It assumes:

- Normally distributed short-term log returns
- Constant volatility during the remaining market window
- Zero expected short-term drift
- Immediate fills at captured ask prices
- No adverse selection
- No meaningful network or execution latency

Real markets can include:

- Sudden jumps
- Volatility regime changes
- Feed discrepancies
- Oracle timing differences
- Rapid order-book changes
- Partial fills
- Queue competition
- Execution delays

A simulated edge should not be treated as a tradable edge until it survives realistic out-of-sample testing.

## Development Roadmap

### Phase 1: Data Collection

- Stream Bitcoin prices from the correct settlement source
- Capture Polymarket order-book changes
- Record source and receipt timestamps
- Verify each market’s opening reference
- Detect new 15-minute markets automatically
- Store every forecast, including NO TRADE decisions

### Phase 2: Research and Validation

- Build a historical synchronized dataset
- Compare predictions against market-implied probabilities
- Measure performance by time remaining
- Analyze volatility and liquidity regimes
- Test momentum, order flow, and market microstructure features
- Use chronological walk-forward validation
- Model latency, partial fills, and adverse price movement

### Phase 3: Live Paper Trading

- Run the engine continuously
- Record simulated entries in real time
- Track unresolved and settled contracts
- Monitor calibration and drawdowns
- Add daily risk and exposure limits
- Create a live monitoring dashboard

### Phase 4: Controlled Automation

Automated execution should only be considered after the strategy demonstrates repeatable, out-of-sample profitability after all estimated costs.

## Success Criteria

The project will not be judged primarily by win rate.

A successful strategy must demonstrate:

1. Positive net returns after fees and slippage
2. Strong probability calibration
3. Performance across different market conditions
4. Results on unseen chronological data
5. Sufficient sample size
6. Controlled drawdowns
7. Realistic executable fills
8. Better performance than simply using Polymarket’s probability

## Official Documentation

- [Polymarket API Overview](https://docs.polymarket.com/api-reference/predictions/overview)
- [Market Lookup by Slug](https://docs.polymarket.com/api-reference/markets/get-market-by-slug)
- [Order Book Endpoint](https://docs.polymarket.com/api-reference/market-data/get-order-book)
- [Market Details](https://docs.polymarket.com/market-data/market-details)
- [Trading Fees](https://docs.polymarket.com/trading/fees)
- [Real-Time Market Data](https://docs.polymarket.com/market-data/realtime-data)

API behavior, fee schedules, and market rules may change. Always review the exact contract rules before conducting research.

## Disclaimer

This project is for educational and quantitative research purposes only.

It does not provide financial advice, guarantee profitability, or currently execute real-money trades. Prediction markets and cryptocurrency-related products involve substantial risk.

This project is independent and is not affiliated with Polymarket, Bitcoin, or Chainlink.
