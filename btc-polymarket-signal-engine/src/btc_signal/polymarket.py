"""Public GET-only capture adapter. Does not produce trading-ready snapshots."""

import json
import time
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


def get_json(url: str) -> dict:
    request = Request(url, headers={"User-Agent": "btc-signal-research/0.1"}, method="GET")
    with urlopen(request, timeout=10) as response:
        return json.load(response)


def capture_market(slug: str) -> dict:
    """Retrieve metadata and outcome books by label, never by assumed index."""
    market = get_json("https://gamma-api.polymarket.com/markets/slug/" + quote(slug, safe=""))
    outcomes = market["outcomes"]
    tokens = market["clobTokenIds"]
    outcomes = json.loads(outcomes) if isinstance(outcomes, str) else outcomes
    tokens = json.loads(tokens) if isinstance(tokens, str) else tokens
    if len(outcomes) != 2 or len(tokens) != 2 or {str(o).upper() for o in outcomes} != {"UP", "DOWN"}:
        raise ValueError("expected exactly Up/Down tokens; inspect market rules")
    books = {}
    for outcome, token in zip(outcomes, tokens):
        raw = get_json("https://clob.polymarket.com/book?" + urlencode({"token_id": token}))
        if str(raw["asset_id"]) != str(token) or raw["market"] != market["conditionId"]:
            raise ValueError("returned book identity mismatch")
        books[str(outcome).upper()] = {"received_at": time.time(), "raw": raw}
    return {"type": "raw_public_market_capture", "received_at": time.time(),
            "market": market, "books": books}
