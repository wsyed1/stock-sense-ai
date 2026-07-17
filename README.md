# StockSense — Portfolio & AI Stock Sentiment

A demo app with two screens:

1. **Portfolio** (home) — a sample stock portfolio with summary tiles (total
   value, gain/loss) and a holdings table.
2. **Recommendations** — enter a watchlist (or jump straight from the portfolio
   via *Get AI Recommendations*) and StockSense pulls recent news per ticker,
   runs it through an OpenAI model, and shows a sentiment score (1–100), a
   Bearish / Neutral / Bullish / Strongly Bullish recommendation, and a short
   reason per stock.

```
frontend (browser)  ──GET /sentiment/?tickers=AAPL,MSFT,NVDA──►  backend (Flask)
       ▲                                                                │
       │                                                    1. Polygon.io news per ticker
       │                                                    2. (optional) scrape full article text
       └──────────────  JSON { sentiments: [...] }  ◄───────  3. OpenAI structured output
```

## Project layout

```
stock-sense-ai/
├── frontend/                 Static single-page app (no build step)
│   ├── index.html            Markup + view structure
│   ├── css/styles.css        All styles
│   └── js/app.js             Portfolio + recommendations logic
├── backend/                  Flask API
│   ├── app.py                Routes only (/ and /sentiment/)
│   ├── config.py             Central config; reads secrets from .env
│   ├── .env.example          Template — copy to .env and add your keys
│   ├── services/
│   │   ├── polygon_client.py     Fetches news from Polygon.io
│   │   ├── scraper_service.py    Scrapes full article text (newspaper3k or fallback)
│   │   └── sentiment_service.py  Orchestrates fetch → scrape → model → result
│   ├── models/news_item.py   News data model
│   └── legacy/               Earlier prototypes, kept for reference only
├── venv/                     Python virtual environment (Flask, requests, openai…)
└── README.md
```

## Setup

1. **Activate the virtualenv** (ships with Flask, requests, openai, python-dotenv):

   ```bash
   source venv/bin/activate
   # For full-text scraping (recommended — the app falls back to a lightweight
   # requests-based scraper if this is not installed):
   ./venv/bin/pip install newspaper3k lxml_html_clean
   ```

   Check which scraper is active at runtime with
   `python -c "from services import scraper_service; print(scraper_service.backend_name())"`
   from the `backend/` directory — it prints `newspaper3k` or `requests-fallback`.

2. **Add your API keys:**

   ```bash
   cd backend
   cp .env.example .env
   # edit .env — set polygon_api_key and openai_api_key
   ```

   - Polygon.io key: https://polygon.io
   - OpenAI key: https://platform.openai.com

## Running

**Backend** (run from the `backend/` directory so imports resolve):

```bash
cd backend
../venv/bin/python app.py
# serving on http://127.0.0.1:8888
```

**Frontend** — serve the `frontend/` directory with any static server:

```bash
cd frontend
../venv/bin/python -m http.server 5500
# open http://127.0.0.1:5500/index.html
```

## Using it

- The **Portfolio** screen loads first with a sample portfolio.
- Click **Get AI Recommendations** to send all your holdings to the analyzer, or
  switch to the **Recommendations** tab and type tickers manually / click **Demo**.
- Tickers with no recent news come back marked **No Data**.

### Pointing the frontend at a different backend

`js/app.js` resolves its API base in this order (no code edit needed):

1. `?api=<url>` query param — `index.html?api=http://myhost:9000`
2. `window.STOCKSENSE_API_BASE` global
3. `localStorage['stocksense_api_base']`
4. default `http://127.0.0.1:8888`

## Concepts demonstrated (for the write-up)

This project intentionally showcases several patterns:

- **Web scraping** — `services/scraper_service.py` fetches full article text
  (newspaper3k, with a requests-based fallback) and feeds it to the model, so
  sentiment is grounded in the article body, not just a headline.
- **Two ways to get consistent, schema-valid JSON from an LLM**, sharing one
  schema and prompt so they can be compared directly:
  - **Structured outputs** (default) — `response_format` with a strict
    `json_schema`. See `_score_structured_outputs()`.
  - **Function / tool calling** — the schema is declared as a function's
    `parameters`; the model is forced to call it via `tool_choice`, and the JSON
    is read from `message.tool_calls[0].function.arguments`. See
    `_score_function_calling()`.

  Select the mechanism with the `method` query param:

  ```
  GET /sentiment/?tickers=AAPL,MSFT&method=structured   # default
  GET /sentiment/?tickers=AAPL,MSFT&method=function      # function calling
  ```

  The response echoes which one ran in a top-level `"method"` field.

## API

`GET /sentiment/?tickers=AAPL,MSFT,NVDA` → one entry per requested ticker, in order:

```json
{
  "method": "structured",
  "sentiments": [
    {
      "ticker": "AAPL",
      "stock_name": "Apple Inc.",
      "sentiment_score": 78,
      "recommendation": "Bullish",
      "reason": "...",
      "source": "..."
    }
  ]
}
```

Errors return the same shape with an `error` string and empty `sentiments`
(400 bad input, 502 upstream/Polygon failure, 500 otherwise).

## Configuration reference

Optional settings in `backend/.env` (see `backend/.env.example`): `openai_model`,
`news_limit`, `port`, `enable_scraping`, `scrape_articles_per_ticker`.

> **Disclaimer:** portfolio holdings/prices are illustrative sample data, and AI
> sentiment scores/recommendations are model-generated — not financial advice.
