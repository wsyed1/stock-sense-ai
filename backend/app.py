"""StockSense API — watchlist sentiment analysis.

Routes only; the real work lives in services/. Run with:

    cd APIs && ../venv/bin/python app.py
"""
import json
import time

from flask import Flask, request, jsonify, Response

import config
from services import polygon_client, price_client, sentiment_service

app = Flask(__name__)


def _parse_tickers(raw):
    """Parse a comma-separated 'tickers' param into a clean list.

    Returns (tickers, error_message). error_message is None on success.
    """
    raw = (raw or "").strip()
    if not raw:
        return None, ("Missing required 'tickers' parameter. Pass a comma-separated "
                      "list, e.g. ?tickers=AAPL,MSFT,NVDA")
    tickers = [t for t in (part.strip() for part in raw.split(",")) if t]
    if not tickers:
        return None, "No valid tickers found in the 'tickers' parameter."
    return tickers, None


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
        "usage": {
            "sentiment": "/sentiment/?tickers=AAPL,MSFT,NVDA",
            "prices": "/prices/?tickers=AAPL,MSFT,NVDA",
        },
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
    tickers, error = _parse_tickers(request.args.get("tickers"))
    if error:
        return _json_response({"error": error, "sentiments": []}, status=400)

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


@app.route("/prices/", methods=["GET"])
def prices_page():
    """Fetch the latest (previous-close) price + day change per ticker.

    Query param:
        tickers (required) — comma-separated symbols, e.g. AAPL,MSFT,NVDA

    Note: Polygon's free tier returns delayed / end-of-day data, so 'price' is
    the previous close, not a real-time quote. The 'note' field says so.
    """
    tickers, error = _parse_tickers(request.args.get("tickers"))
    if error:
        return _json_response({"error": error, "prices": []}, status=400)

    try:
        prices = price_client.fetch_prices(tickers)
    except price_client.PriceError as exc:
        return _json_response({"error": str(exc), "prices": []}, status=502)
    except config.ConfigError as exc:
        return _json_response({"error": str(exc), "prices": []}, status=500)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("Unexpected error fetching prices")
        return _json_response({"error": f"Unexpected error: {exc}", "prices": []}, status=500)

    return _json_response({
        "note": "Prices are previous close (Polygon free tier = delayed / end-of-day data).",
        "prices": prices,
    })


if __name__ == "__main__":
    app.run(port=config.PORT)
