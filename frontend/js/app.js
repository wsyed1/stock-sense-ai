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

    // ---- Mock portfolio (illustrative sample data) ----
    // price = current price, cost = average cost basis per share.
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
              <div class="holding-company">last price</div>
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

    // Mirrors the backend's 5-tier score -> recommendation mapping
    // (see _recommendation_for_score in sentiment_service.py) so the bar color
    // always lines up with the badge shown next to it.
    function getBarColor(score) {
      if (score <= 25) return '#ef4444';  // Do Not Buy
      if (score <= 45) return '#f97316';  // Watch
      if (score <= 65) return '#f59e0b';  // Hold
      if (score <= 85) return '#22c55e';  // Buy
      return '#16a34a';                   // Strong Buy
    }

    function getBadgeClass(rec) {
      if (!rec) return 'badge-default';
      const r = rec.toLowerCase().trim();
      if (r === 'strong buy') return 'badge-strong-buy';
      if (r === 'buy')        return 'badge-buy';
      if (r === 'hold')       return 'badge-hold';
      if (r === 'watch')      return 'badge-watch';
      if (r === 'do not buy') return 'badge-do-not-buy';
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

    function buildCardHTML(item) {
      const badgeClass = getBadgeClass(item.recommendation);
      const barColor = getBarColor(item.sentiment_score);
      const sourceHTML = isValidUrl(item.source)
        ? `<a class="source-link" href="${item.source}" target="_blank" rel="noopener noreferrer">↗ View Source</a>`
        : `<span style="font-size:0.8rem;color:var(--text-muted)">${item.source || '—'}</span>`;

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
        ${sourceHTML}
      `;
    }

    function buildSummaryHTML(sentiments) {
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
      return `
        <div class="summary-strip">
          <div class="summary-strip-label">${sentiments.length} stock${sentiments.length !== 1 ? 's' : ''} analyzed</div>
          <div class="summary-items">${items}</div>
        </div>`;
    }

    function renderCards(sentiments, ticker) {
      const results = document.getElementById('results');
      if (!sentiments || sentiments.length === 0) {
        results.innerHTML = `
          <div class="state-box">
            <p>No sentiment data found for <strong>${ticker}</strong>. Try a different ticker.</p>
          </div>`;
        return;
      }

      const wrapper = document.createElement('div');
      wrapper.innerHTML = buildSummaryHTML(sentiments);

      const grid = document.createElement('div');
      grid.className = 'results-grid';

      const fragment = document.createDocumentFragment();
      sentiments.forEach(item => {
        const card = document.createElement('article');
        card.className = 'card';
        card.id = `card-${item.ticker}`;
        card.innerHTML = buildCardHTML(item);
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
        const url = `${API_BASE}/sentiment/?tickers=${encodeURIComponent(tickers.join(','))}`;
        const res = await fetch(url, { signal: controller.signal });
        clearTimeout(timer);

        let data = null;
        try { data = await res.json(); } catch { /* non-JSON body */ }

        if (!res.ok) {
          showError((data && data.error) ? data.error : `API returned an error (HTTP ${res.status}).`);
          return;
        }

        renderCards(data.sentiments, tickers.join(', '));
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

    // ---- init ----
    renderPortfolio();
