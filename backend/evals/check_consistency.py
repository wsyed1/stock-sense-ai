"""Consistency eval for StockSense sentiment.

Runs the same ticker through the pipeline several times and reports how much the
sentiment_score drifts between runs. With config.OPENAI_TEMPERATURE = 0 the score
should be stable (variance ~0); a large spread signals a non-deterministic setup.

Run from the backend/ directory:

    cd backend && ../venv/bin/python -m evals.check_consistency

Optional args: ticker and number of runs:

    ../venv/bin/python -m evals.check_consistency NVDA 5
"""
import sys

import config
from services import sentiment_service

# Max acceptable spread (max - min) in sentiment_score across runs.
STABILITY_THRESHOLD = 5


def check_consistency(ticker: str, runs: int = 5) -> int:
    scores = []
    for _ in range(runs):
        result = sentiment_service.analyse_watchlist([ticker])
        scores.append(result["sentiments"][0]["sentiment_score"])

    spread = max(scores) - min(scores) if scores else 0
    verdict = "stable" if spread <= STABILITY_THRESHOLD else "UNSTABLE"

    print(f"temperature = {config.OPENAI_TEMPERATURE}")
    print(f"{ticker} sentiment_score over {runs} runs: {scores}")
    print(f"Spread (max - min): {spread}  ->  {verdict} "
          f"(threshold {STABILITY_THRESHOLD})")
    return spread


if __name__ == "__main__":
    ticker = sys.argv[1] if len(sys.argv) > 1 else "NVDA"
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    check_consistency(ticker, runs)
