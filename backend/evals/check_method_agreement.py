"""Method-agreement eval for StockSense sentiment.

The service can produce structured JSON two ways — modern structured outputs
(json_schema) and classic function/tool calling. Both share the same schema and
prompt, so in principle they should agree. This eval runs BOTH on the same
tickers and reports where their sentiment scores diverge.

Close agreement is a nice credibility signal: the result isn't an artifact of one
particular API mechanism. Large divergence is worth investigating.

Run from the backend/ directory:

    cd backend && ../venv/bin/python -m evals.check_method_agreement AAPL,NVDA,MSFT

Defaults to the demo watchlist if no tickers are given.
"""
import sys

import config
from services import sentiment_service

# Max acceptable per-ticker score difference between the two methods.
AGREEMENT_THRESHOLD = 10


def _scores_by_ticker(result: dict) -> dict:
    return {
        (row.get("ticker") or "").strip().upper(): row.get("sentiment_score")
        for row in result.get("sentiments", [])
    }


def check_agreement(tickers: list) -> int:
    structured = _scores_by_ticker(
        sentiment_service.analyse_watchlist(tickers, method="structured")
    )
    function = _scores_by_ticker(
        sentiment_service.analyse_watchlist(tickers, method="function")
    )

    print(f"{'ticker':8s} {'structured':>10s} {'function':>10s} {'diff':>6s}  verdict")
    print("-" * 48)

    worst = 0
    for symbol in (t.strip().upper() for t in tickers if t.strip()):
        s = structured.get(symbol)
        f = function.get(symbol)
        if s is None or f is None:
            print(f"{symbol:8s} {str(s):>10s} {str(f):>10s} {'?':>6s}  MISSING")
            continue
        diff = abs(s - f)
        worst = max(worst, diff)
        verdict = "agree" if diff <= AGREEMENT_THRESHOLD else "DIVERGE"
        print(f"{symbol:8s} {s:>10d} {f:>10d} {diff:>6d}  {verdict}")

    overall = "AGREE" if worst <= AGREEMENT_THRESHOLD else "DIVERGE"
    print("-" * 48)
    print(f"Worst divergence: {worst}  ->  {overall} (threshold {AGREEMENT_THRESHOLD})")
    return worst


if __name__ == "__main__":
    tickers = sys.argv[1].split(",") if len(sys.argv) > 1 else config.DEMO_WATCHLIST
    check_agreement(tickers)
