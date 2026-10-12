import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
from urllib.error import URLError

from .engine import Config, evaluate
from .paper import replay
from .polymarket import capture_market


def emit(value):
    print(json.dumps(value, indent=2, allow_nan=False))


def main():
    parser = argparse.ArgumentParser(description="BTC 15-minute probability research; paper only")
    subs = parser.add_subparsers(dest="command", required=True)
    signal = subs.add_parser("signal", help="evaluate one normalized snapshot JSON")
    signal.add_argument("snapshot", type=Path)
    paper = subs.add_parser("replay", help="replay chronological JSONL with separate settlements")
    paper.add_argument("snapshots", type=Path)
    paper.add_argument("outcomes", type=Path)
    paper.add_argument("--cash", type=float, default=1000)
    collect = subs.add_parser("capture", help="capture raw public metadata/books; GET only")
    collect.add_argument("--slug", required=True)
    collect.add_argument("--output", type=Path, required=True)
    collect.add_argument("--count", type=int, default=1)
    collect.add_argument("--interval", type=float, default=5)
    for p in (signal, paper):
        p.add_argument("--config", type=Path, help="JSON object overriding Config defaults")
    args = parser.parse_args()
    try:
        if args.command == "capture":
            if args.count < 1 or not 1 <= args.interval <= 60:
                raise ValueError("count >= 1; interval must be between 1 and 60 seconds")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("a") as output:
                for index in range(args.count):
                    row = capture_market(args.slug)
                    output.write(json.dumps(row, allow_nan=False) + "\n")
                    output.flush()
                    if index + 1 < args.count:
                        time.sleep(args.interval)
            emit({"captured": args.count, "output": str(args.output)})
            return
        config = Config(**json.loads(args.config.read_text())) if args.config else Config()
        if args.command == "signal":
            emit({"config": asdict(config), **evaluate(json.loads(args.snapshot.read_text()), config)})
        else:
            snapshots = [json.loads(line) for line in args.snapshots.read_text().splitlines() if line.strip()]
            emit(replay(snapshots, json.loads(args.outcomes.read_text()), config, args.cash))
    except (OSError, ValueError, TypeError, KeyError, URLError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
