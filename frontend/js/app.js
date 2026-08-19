    // ---- API base resolution (query param > global > localStorage > default) ----
    const API_BASE = (() => {
      const fromQuery = new URLSearchParams(location.search).get('api');
      return (
        fromQuery ||
        window.STOCKSENSE_API_BASE ||
        localStorage.getItem('stocksense_api_base') ||
        'http://127.0.0.1:8888'
      ).replace(/\/+$/, '');
    })();

    // ---- Portfolio (holdings are sample data; prices are fetched live) ----
    // shares/cost are illustrative; `price` starts as a fallback and is
    // overwritten with the real previous close from Polygon on load (see
    // refreshPrices). `priceIsLive` tracks whether the live fetch succeeded.
    const PORTFOLIO = [
      { ticker: 'AAPL',  company: 'Apple Inc.',            shares: 42, price: 229.35, cost: 178.20, color: '#0f172a' },
      { ticker: 'MSFT',  company: 'Microsoft Corp.',       shares: 18, price: 441.10, cost: 402.55, color: '#2563eb' },
      { ticker: 'NVDA',  company: 'NVIDIA Corp.',          shares: 60, price: 128.72, cost: 96.40,  color: '#16a34a' },
      { ticker: 'AMZN',  company: 'Amazon.com Inc.',       shares: 25, price: 197.85, cost: 165.10, color: '#f59e0b' },
      { ticker: 'GOOGL', company: 'Alphabet Inc.',         shares: 30, price: 178.42, cost: 141.90, color: '#6366f1' },
      { ticker: 'TSLA',  company: 'Tesla Inc.',            shares: 15, price: 251.44, cost: 289.30, color: '#dc2626' },
      { ticker: 'META',  company: 'Meta Platforms Inc.',   shares: 12, price: 563.27, cost: 470.15, color: '#1d4ed8' },
    ];

    const DEMO_WATCHLIST = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA'];

    const fmtMoney = n => n.toLocaleString('en-US', { style: 'currency', currency: 'USD' });
    const fmtPct = n => (n >= 0 ? '+' : '') + n.toFixed(2) + '%';

    // ---------- View switching ----------
    window.showView = function(name) {
      const isPortfolio = name === 'portfolio';
      document.getElementById('view-portfolio').hidden = !isPortfolio;
      document.getElementById('view-recommendations').hidden = isPortfolio;
      document.getElementById('tab-portfolio').classList.toggle('active', isPortfolio);
      document.getElementById('tab-recommendations').classList.toggle('active', !isPortfolio);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    // ---------- Portfolio rendering ----------
    function renderPortfolio() {
      let totalValue = 0, totalCost = 0;
      PORTFOLIO.forEach(h => {
        totalValue += h.shares * h.price;
        totalCost  += h.shares * h.cost;
      });
      const totalGain = totalValue - totalCost;
      const totalGainPct = totalCost ? (totalGain / totalCost) * 100 : 0;
      // A plausible "today" move derived from the sample data.
      const dayChange = totalValue * 0.0087;
      const up = totalGain >= 0;
      const dayUp = dayChange >= 0;

      document.getElementById('portfolioTiles').innerHTML = `
        <div class="tile">
          <div class="tile-label">Total Value</div>
          <div class="tile-value">${fmtMoney(totalValue)}</div>
          <span class="tile-delta ${dayUp ? 'delta-up' : 'delta-down'}">
            ${dayUp ? '▲' : '▼'} ${fmtMoney(Math.abs(dayChange))} today
          </span>
        </div>
        <div class="tile">
          <div class="tile-label">Total Gain / Loss</div>
          <div class="tile-value ${up ? 'up' : 'down'}">${up ? '+' : '−'}${fmtMoney(Math.abs(totalGain))}</div>
          <span class="tile-delta ${up ? 'delta-up' : 'delta-down'}">
            ${up ? '▲' : '▼'} ${fmtPct(totalGainPct)} all time
          </span>
        </div>
        <div class="tile">
          <div class="tile-label">Holdings</div>
          <div class="tile-value">${PORTFOLIO.length}</div>
          <span class="tile-delta delta-up" style="background:#eff6ff;color:var(--primary)">
            ${PORTFOLIO.reduce((s, h) => s + h.shares, 0)} shares total
          </span>
        </div>
      `;

      const rows = PORTFOLIO.map(h => {
        const value = h.shares * h.price;
        const gainPct = ((h.price - h.cost) / h.cost) * 100;
        const g = gainPct >= 0;
        return `
          <div class="holding-row">
            <div class="holding-name-cell">
              <div class="avatar" style="background:${h.color}">${h.ticker.slice(0,2)}</div>
              <div style="min-width:0">
                <div class="holding-ticker">${h.ticker}</div>
                <div class="holding-company">${h.company}</div>
                <div class="holding-shares">${h.shares} shares · avg ${fmtMoney(h.cost)}</div>
              </div>
            </div>
            <div class="num col-price">
              <div class="holding-value">${fmtMoney(h.price)}</div>
              <div class="holding-company">${h.priceIsLive ? 'prev. close' : 'sample price'}</div>
            </div>
            <div class="num">
              <div class="holding-value">${fmtMoney(value)}</div>
              <div class="holding-company">value</div>
            </div>
            <div class="num">
              <div class="holding-delta ${g ? 'up' : 'down'}">${g ? '▲' : '▼'} ${fmtPct(gainPct)}</div>
            </div>
          </div>`;
      }).join('');

      document.getElementById('holdingsTable').innerHTML = `
        <div class="holding-row holding-row-head">
          <div>Holding</div>
          <div class="num col-price">Price</div>
          <div class="num">Value</div>
          <div class="num">Gain</div>
        </div>
        ${rows}`;
    }

    // ---------- Segue: analyze whole portfolio ----------
    window.analyzePortfolio = function() {
      const tickers = PORTFOLIO.map(h => h.ticker);
      document.getElementById('tickerInput').value = tickers.join(', ');
      showView('recommendations');
      searchSentiment();
    };

    // ---------- Recommendations logic ----------
    document.getElementById('tickerInput').addEventListener('input', e => {
      e.target.value = e.target.value.toUpperCase();
    });
    document.getElementById('tickerInput').addEventListener('keydown', e => {
      if (e.key === 'Enter') searchSentiment();
    });

    // Mirrors the backend's score -> recommendation mapping (see
    // _RECOMMENDATION_THRESHOLDS in sentiment_service.py) so the bar color
    // always lines up with the badge shown next to it. Seven bands,
    // symmetric around 50 (Neutral).
    function getBarColor(score) {
      if (score <= 10) return '#b91c1c';  // Strongly Bearish
      if (score <= 25) return '#ef4444';  // Bearish
      if (score <= 40) return '#f97316';  // Slightly Bearish
      if (score <= 59) return '#f59e0b';  // Neutral
      if (score <= 74) return '#84cc16';  // Slightly Bullish
      if (score <= 89) return '#22c55e';  // Bullish
      return '#16a34a';                   // Strongly Bullish
    }

    function getBadgeClass(rec) {
      if (!rec) return 'badge-default';
      const r = rec.toLowerCase().trim();
      if (r === 'strongly bullish')  return 'badge-strongly-bullish';
      if (r === 'bullish')           return 'badge-bullish';
      if (r === 'slightly bullish')  return 'badge-slightly-bullish';
      if (r === 'neutral')           return 'badge-neutral';
      if (r === 'slightly bearish')  return 'badge-slightly-bearish';
      if (r === 'bearish')           return 'badge-bearish';
      if (r === 'strongly bearish')  return 'badge-strongly-bearish';
      return 'badge-default';
    }

    function avatarColor(ticker) {
      const known = Object.fromEntries(PORTFOLIO.map(h => [h.ticker, h.color]));
      if (known[ticker]) return known[ticker];
      // Deterministic hue from the ticker so colors are stable.
      let hash = 0;
      for (let i = 0; i < ticker.length; i++) hash = ticker.charCodeAt(i) + ((hash << 5) - hash);
      return `hsl(${Math.abs(hash) % 360}, 55%, 42%)`;
    }

    function isValidUrl(str) {
      try { new URL(str); return true; } catch { return false; }
    }

    // Renders a compact price + day-change line for a card, when live price
    // data is available. Fails soft: returns '' (card just omits the line)
    // if the /prices/ call failed, timed out, or has no data for this ticker
    // — mirrors how the Portfolio tab treats missing live prices.
    function buildPriceHTML(priceInfo) {
      if (!priceInfo || typeof priceInfo.price !== 'number') return '';
      const hasChange = typeof priceInfo.change_pct === 'number';
      const up = hasChange && priceInfo.change_pct >= 0;
      return `
        <div class="card-price-row">
          <span class="card-price">${fmtMoney(priceInfo.price)}</span>
          <span class="card-price-label">prev. close</span>
          ${hasChange ? `<span class="card-price-delta ${up ? 'up' : 'down'}">${up ? '▲' : '▼'} ${fmtPct(priceInfo.change_pct)}</span>` : ''}
        </div>`;
    }

    // item.sources is built server-side straight from Polygon's article data
    // (see _sources_for_ticker in sentiment_service.py) — never from the
    // model, so titles/URLs here are always real. escapeHTML guards against
    // headline text containing characters that would otherwise break markup.
    function escapeHTML(str) {
      const div = document.createElement('div');
      div.textContent = str == null ? '' : String(str);
      return div.innerHTML;
    }

    function buildSourcesHTML(sources) {
      if (!sources || sources.length === 0) {
        return `<span style="font-size:0.8rem;color:var(--text-muted)">No sources available</span>`;
      }
      const items = sources.map(s => {
        if (!isValidUrl(s.url)) return '';
        const label = s.publisher ? `${escapeHTML(s.title)} — ${escapeHTML(s.publisher)}` : escapeHTML(s.title);
        return `
          <a class="source-link" href="${s.url}" target="_blank" rel="noopener noreferrer">
            ↗ ${label}
          </a>`;
      }).filter(Boolean).join('');
      return items || `<span style="font-size:0.8rem;color:var(--text-muted)">No sources available</span>`;
    }

    function buildCardHTML(item, priceInfo) {
      const badgeClass = getBadgeClass(item.recommendation);
      const barColor = getBarColor(item.sentiment_score);
      const sourcesHTML = buildSourcesHTML(item.sources);
      const priceHTML = buildPriceHTML(priceInfo);

      return `
        <div class="card-header">
          <div class="card-head-left">
            <div class="avatar" style="background:${avatarColor(item.ticker)}">${(item.ticker || '—').slice(0,2)}</div>
            <div>
              <div class="card-ticker">${item.ticker || '—'}</div>
              <div class="card-name">${item.stock_name || ''}</div>
            </div>
          </div>
          <span class="badge ${badgeClass}">${item.recommendation || 'N/A'}</span>
        </div>
        ${priceHTML}
        <hr class="card-divider" />
        <div class="score-section">
          <div class="score-label-row">
            <span class="score-label">Sentiment Score</span>
            <span class="score-value">${item.sentiment_score} / 100</span>
          </div>
          <div class="score-bar-track">
            <div class="score-bar-fill" data-score="${item.sentiment_score}" style="background:${barColor}"></div>
          </div>
        </div>
        <hr class="card-divider" />
        <div class="reason-section">
          <div class="reason-title">Analysis</div>
          <p class="reason-text">${item.reason || '—'}</p>
          <button class="toggle-btn" onclick="toggleReason(this)">Show more</button>
        </div>
        <hr class="card-divider" />
        <div class="sources-section">
          <div class="reason-title">Sources</div>
          <div class="sources-list">${sourcesHTML}</div>
        </div>
      `;
    }

    function buildSummaryHTML(sentiments, asOf, cached) {
      const items = sentiments.map(item => {
        const color = getBarColor(item.sentiment_score);
        return `
          <a class="summary-item" href="#card-${item.ticker}" onclick="scrollToCard('${item.ticker}')">
            <span class="summary-ticker-label">${item.ticker}</span>
            <span class="summary-score-pill" style="background:${color}">${item.sentiment_score}</span>
            <div class="summary-mini-bar-track">
              <div class="summary-mini-bar-fill" data-score="${item.sentiment_score}" style="background:${color}"></div>
            </div>
          </a>`;
      }).join('');
      const asOfHTML = formatAsOf(asOf);
      // `cached` (from the API's "cached" field) is True only when every
      // Polygon/scrape call this request needed was served from the backend's
      // in-memory cache — a static dot + "Cached" label reflects that no live
      // fetch happened, vs. the pulsing dot for a request that did real work.
      const pillClass = cached ? 'summary-as-of cached' : 'summary-as-of';
      const pillText = cached ? `Cached · As of ${asOfHTML}` : `As of ${asOfHTML}`;
      return `
        <div class="summary-strip">
          <div class="summary-strip-head">
            <div class="summary-strip-label">${sentiments.length} stock${sentiments.length !== 1 ? 's' : ''} analyzed</div>
            ${asOfHTML ? `<span class="${pillClass}"><span class="dot"></span>${pillText}</span>` : ''}
          </div>
          <div class="summary-items">${items}</div>
        </div>`;
    }

    // Renders the backend's `as_of` (ISO 8601, UTC) in the viewer's local time,
    // e.g. "Aug 19, 2026, 10:00 AM". Cached responses can share the same as_of
    // as a recent prior request — that's expected, not a bug (see app.py).
    function formatAsOf(asOf) {
      if (!asOf) return '';
      const d = new Date(asOf);
      if (Number.isNaN(d.getTime())) return '';
      return d.toLocaleString('en-US', {
        month: 'short', day: 'numeric', year: 'numeric',
        hour: 'numeric', minute: '2-digit',
      });
    }

    function renderCards(sentiments, ticker, asOf, cached, priceByTicker) {
      const results = document.getElementById('results');
      if (!sentiments || sentiments.length === 0) {
        results.innerHTML = `
          <div class="state-box">
            <p>No sentiment data found for <strong>${ticker}</strong>. Try a different ticker.</p>
          </div>`;
        return;
      }

      const wrapper = document.createElement('div');
      wrapper.innerHTML = buildSummaryHTML(sentiments, asOf, cached);

      const grid = document.createElement('div');
      grid.className = 'results-grid';

      const fragment = document.createDocumentFragment();
      sentiments.forEach(item => {
        const card = document.createElement('article');
        card.className = 'card';
        card.id = `card-${item.ticker}`;
        card.innerHTML = buildCardHTML(item, priceByTicker && priceByTicker[item.ticker]);
        fragment.appendChild(card);
      });
      grid.appendChild(fragment);
      wrapper.appendChild(grid);

      results.innerHTML = '';
      results.appendChild(wrapper);

      requestAnimationFrame(() => {
        document.querySelectorAll('.score-bar-fill, .summary-mini-bar-fill').forEach(bar => {
          bar.style.width = bar.dataset.score + '%';
        });
      });
    }

    window.scrollToCard = function(ticker) {
      const card = document.getElementById('card-' + ticker);
      if (card) setTimeout(() => card.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50);
    };

    function showLoading() {
      document.getElementById('results').innerHTML = `
        <div class="state-box">
          <div class="spinner"></div>
          <p>Analyzing recent news sentiment…</p>
        </div>`;
    }

    function showError(msg) {
      document.getElementById('results').innerHTML = `
        <div class="error-box">
          <span class="error-icon">⚠</span>
          <p>${msg}</p>
        </div>`;
    }

    window.toggleReason = function(btn) {
      const p = btn.previousElementSibling;
      const expanded = p.classList.toggle('expanded');
      btn.textContent = expanded ? 'Show less' : 'Show more';
    };

    window.loadDemo = function() {
      document.getElementById('tickerInput').value = DEMO_WATCHLIST.join(', ');
      searchSentiment();
    };

    function parseTickers(raw) {
      const seen = new Set();
      return raw
        .split(/[\s,]+/)
        .map(t => t.trim().toUpperCase())
        .filter(t => t && !seen.has(t) && seen.add(t));
    }

    async function searchSentiment() {
      const tickers = parseTickers(document.getElementById('tickerInput').value);
      const btn = document.getElementById('searchBtn');

      if (tickers.length === 0) {
        showError('Please enter at least one ticker symbol.');
        return;
      }

      btn.disabled = true;
      showLoading();

      const controller = new AbortController();
      const timeoutMs = Math.min(60000, 15000 + tickers.length * 4000);
      const timer = setTimeout(() => controller.abort(), timeoutMs);

      try {
        const tickerParam = encodeURIComponent(tickers.join(','));
        const sentimentUrl = `${API_BASE}/sentiment/?tickers=${tickerParam}`;
        const pricesUrl = `${API_BASE}/prices/?tickers=${tickerParam}`;

        // Fetch sentiment and prices concurrently — they're independent calls,
        // and prices are the same fast endpoint the Portfolio tab already uses.
        // Prices fail soft: if that call errors/times out, cards just render
        // without a price line rather than blocking on it (see fetchPricesSoft).
        const [res, priceByTicker] = await Promise.all([
          fetch(sentimentUrl, { signal: controller.signal }),
          fetchPricesSoft(tickers),
        ]);
        clearTimeout(timer);

        let data = null;
        try { data = await res.json(); } catch { /* non-JSON body */ }

        if (!res.ok) {
          showError((data && data.error) ? data.error : `API returned an error (HTTP ${res.status}).`);
          return;
        }

        renderCards(data.sentiments, tickers.join(', '), data.as_of, data.cached, priceByTicker);
      } catch (err) {
        clearTimeout(timer);
        if (err.name === 'AbortError') {
          showError('The request timed out. The server may be busy scraping articles.');
        } else {
          showError(`Unable to reach the API at ${API_BASE}. Is the Flask server running?`);
        }
      } finally {
        btn.disabled = false;
      }
    }

    // ---------- Live prices ----------
    // Fetch previous-close prices from the backend /prices/ endpoint. Fails
    // soft: returns {} on any error/timeout rather than throwing, so callers
    // (Portfolio's refreshPrices, Recommendations' searchSentiment) can treat
    // "no price data" as just an empty map instead of needing their own
    // try/catch around every call site.
    async function fetchPricesSoft(tickers) {
      const url = `${API_BASE}/prices/?tickers=${encodeURIComponent(tickers.join(','))}`;
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 20000);
      try {
        const res = await fetch(url, { signal: controller.signal });
        clearTimeout(timer);
        if (!res.ok) return {};

        const data = await res.json();
        return Object.fromEntries((data.prices || []).map(p => [p.ticker, p]));
      } catch {
        clearTimeout(timer);
        return {};
      }
    }

    // Fetch real previous-close prices and patch them into PORTFOLIO, then
    // re-render. Fails soft: if the API is down or a ticker has no data, that
    // holding keeps its sample price (labeled as such) and the rest of the
    // app is unaffected.
    async function refreshPrices() {
      const tickers = PORTFOLIO.map(h => h.ticker);
      const byTicker = await fetchPricesSoft(tickers);

      PORTFOLIO.forEach(h => {
        const p = byTicker[h.ticker];
        if (p && typeof p.price === 'number') {
          h.price = p.price;
          h.priceIsLive = true;
        }
      });
      renderPortfolio();
    }

    // ---- init ----
    renderPortfolio();   // paint immediately with sample prices
    refreshPrices();     // then swap in live prices when they arrive
