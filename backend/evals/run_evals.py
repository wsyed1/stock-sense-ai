"""Directional accuracy eval for StockSense sentiment.

Runs the real sentiment pipeline over a small hand-labeled dataset and reports
how often the model's directional call (bullish / bearish / neutral) matches the
human label. This is a directional sanity check, not a precision benchmark.

Run from the backend/ directory:

    cd backend && ../venv/bin/python -m evals.run_evals

Optionally pass a scoring method (structured | function):

    ../venv/bin/python -m evals.run_evals function
"""
import sys

from services import sentiment_service
from evals.labeled_dataset import LABELED_CASES, direction_of


def run(method: str = sentiment_service.DEFAULT_METHOD) -> float:
    correct = 0
    total = len(LABELED_CASES)

    print(f"Running {total} directional cases (method={method})\n")
    for case in LABELED_CASES:
        ticker = case["ticker"]
        expected = case["expected_direction"]

        result = sentiment_service.analyse_watchlist([ticker], method=method)
        entry = result["sentiments"][0]
        recommendation = entry["recommendation"]
        actual = direction_of(recommendation)

        match = actual == expected
        mark = "PASS" if match else "FAIL"
        print(
            f"[{mark}] {ticker:6s} expected={expected:8s} "
            f"actual={actual:8s} (score={entry['sentiment_score']}, "
            f"label={recommendation})"
        )
        if match:
            correct += 1

    accuracy = correct / total * 100 if total else 0.0
    print(f"\nDirectional accuracy: {correct}/{total} = {accuracy:.1f}%")
    return accuracy


if __name__ == "__main__":
    chosen = sys.argv[1] if len(sys.argv) > 1 else sentiment_service.DEFAULT_METHOD
    run(chosen)
