"""StockSense API — watchlist sentiment analysis.

Routes only; the real work lives in services/. Run with:

    cd APIs && ../venv/bin/python app.py
"""
import json
import time

from flask import Flask, request, jsonify, Response

import config
from services import polygon_client, sentiment_service

app = Flask(__name__)


# Enable CORS so the frontend (served from a different origin or file://) can
# call this API from the browser. Done manually so no extra package is required.
@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


def _json_response(data, status=200):
    """Return pretty-printed JSON so responses are readable in the browser."""
    return Response(
        json.dumps(data, indent=2),
        status=status,
        mimetype="application/json",
    )


@app.route("/", methods=["GET"])
def home_page():
    return _json_response({
        "app": "StockSense",
        "message": "Watchlist sentiment analysis API.",
        "usage": "/sentiment/?tickers=AAPL,MSFT,NVDA",
        "timestamp": time.time(),
    })


@app.route("/sentiment/", methods=["GET"])
def sentiment_page():
    """Analyse sentiment for a watchlist of tickers.

    Query params:
        tickers (required) — comma-separated symbols, e.g. AAPL,MSFT,NVDA
        method  (optional) — "structured" (default) or "function", selecting how
                             consistent JSON is obtained from the model.
    """
    raw = request.args.get("tickers", "").strip()
    if not raw:
        return _json_response({
            "error": "Missing required 'tickers' parameter. "
                     "Pass a comma-separated list, e.g. /sentiment/?tickers=AAPL,MSFT,NVDA",
            "sentiments": [],
        }, status=400)

    tickers = [t for t in (part.strip() for part in raw.split(",")) if t]
    if not tickers:
        return _json_response({
            "error": "No valid tickers found in the 'tickers' parameter.",
            "sentiments": [],
        }, status=400)

    method = request.args.get("method", sentiment_service.DEFAULT_METHOD).strip().lower()

    try:
        result = sentiment_service.analyse_watchlist(tickers, method=method)
    except polygon_client.PolygonError as exc:
        return _json_response({"error": str(exc), "sentiments": []}, status=502)
    except config.ConfigError as exc:
        return _json_response({"error": str(exc), "sentiments": []}, status=500)
    except Exception as exc:  # noqa: BLE001 — surface a clean message, log the rest
        app.logger.exception("Unexpected error during sentiment analysis")
        return _json_response(
            {"error": f"Unexpected error: {exc}", "sentiments": []}, status=500
        )

    return _json_response(result)


if __name__ == "__main__":
    app.run(port=config.PORT)
