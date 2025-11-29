# Equity Trigger Analysis Skill

Use this skill when you already have fundamental metrics, technicals, risk metrics, and news signals for a stock
and need to map them into GREEN FLAGS, RED FLAGS, and a VERDICT.

## Data Quality Context

**IMPORTANT**: You will receive a DATA QUALITY CONTEXT section that includes:
- **Completeness Score** (0-100%): Percentage of available metrics
- **Confidence Level** (High/Medium/Low): Overall data reliability
- **Missing Critical Metrics**: List of unavailable essential data points

**Rules for Handling Missing Data:**
1. If Completeness Score < 70%, you MUST add a "⚠️ Data Quality Warning" section to your report
2. If critical metrics are missing, explicitly state limitations in your verdict
3. Do NOT make strong Buy/Sell recommendations with Low confidence data
4. Use alternative signals when primary metrics are unavailable (e.g., use news sentiment if financials are incomplete)
5. Always acknowledge data gaps in your analysis

## Available Financial Metrics

The `get_deep_financials` tool provides the following metrics:
- `ticker`: Stock ticker symbol
- `current_price`: Current stock price
- `revenue_growth`: Revenue growth rate (decimal)
- `profit_margins`: Profit margins (decimal)
- `debt_to_equity`: Debt-to-equity ratio
- `total_debt`: Total debt amount
- `trailing_pe` / `forward_pe`: P/E ratios
- `peg_ratio`: Price/Earnings to Growth ratio
- `dividend_yield` / `payout_ratio`: Dividend metrics
- `return_on_equity` / `return_on_assets`: Return metrics
- `free_cash_flow` / `operating_cashflow`: Cash flow metrics

**New Metrics:**
- `technicals`: Dictionary containing `rsi`, `macd`, `sma_50`, `sma_200`.
- `risk_metrics`: Dictionary containing `volatility_annualized`, `max_drawdown`, `sharpe_ratio`.
- `financial_trends`: Dictionary containing `revenue_trend`, `debt_trend`, `capex_trend`, `retained_earnings_trend` (based on last 4 quarters).
- `volume_trends`: Dictionary containing `latest_volume`, `avg_volume_10d`, `avg_volume_50d`, `volume_spike`, `volume_trend`.
- `dividend_trends`: Dictionary containing `annual_dividends`, `dividend_years`, `dividend_trend`.

## Analysis Rules by Metric Category

### 1. Technical Analysis (New)

**RSI (Relative Strength Index)**
- 🚩 Overbought: `rsi > 70` (Caution: potential pullback)
- 🟢 Oversold: `rsi < 30` (Potential buying opportunity)
- 🟡 Neutral: `30 <= rsi <= 70`

**Moving Averages (SMA)**
- 🟢 Bullish Trend: `current_price > sma_200`
- 🚩 Bearish Trend: `current_price < sma_200`
- 🟢 Golden Cross: `sma_50` crosses above `sma_200` (Strong Buy Signal)
- 🚩 Death Cross: `sma_50` crosses below `sma_200` (Strong Sell Signal)

**MACD**
- 🟢 Bullish: `macd > macd_signal`
- 🚩 Bearish: `macd < macd_signal`

### 2. Risk Analysis (New)

**Sharpe Ratio**
- 🟢 Excellent: `sharpe_ratio > 2.0`
- 🟢 Good: `1.0 < sharpe_ratio <= 2.0`
- 🟡 Acceptable: `0.0 < sharpe_ratio <= 1.0`
- 🚩 Poor: `sharpe_ratio < 0.0` (Returns less than risk)

**Volatility & Drawdown**
- 🚩 High Risk: `max_drawdown < -0.50` (Lost >50% at some point)
- 🟡 Moderate Risk: `volatility_annualized > 0.40` (High volatility)

### 3. Financial Trends

**Debt Trend**
- 🟢 Deleveraging: `debt_trend == "decreasing"` (Green Flag)
- 🚩 Increasing Debt: `debt_trend == "increasing"` (Red Flag, unless matched by revenue growth)

**Revenue Trend**
- 🟢 Growing: `revenue_trend == "increasing"`
- 🚩 Shrinking: `revenue_trend == "decreasing"`

**CapEx Trend (NEW)**
- 🟢 Expanding CapEx: `capex_trend == "increasing"` (Growth investment)
- 🟢 **Best Case**: CapEx increasing while Debt decreasing (Self-funded growth)
- 🚩 CapEx increasing with Debt increasing (Leveraged expansion - risky)

**Retained Earnings Trend (NEW)**
- 🟢 Growing Retained Earnings: `retained_earnings_trend == "increasing"` (Reinvesting profits)
- 🚩 Declining Retained Earnings: `retained_earnings_trend == "decreasing"` (Burning through reserves)

### 4. Volume Analysis (NEW)

**Volume Trends**
- 🟢 Volume Spike: `volume_spike == True` (High interest, potential breakout)
- 🟢 Increasing Volume: `volume_trend == "increasing"` (Growing interest)
- 🚩 Decreasing Volume: `volume_trend == "decreasing"` (Declining interest)

### 5. Dividend Analysis (NEW)

**Dividend Trends**
- 🟢 Growing Dividends: `dividend_trend == "increasing"` (Shareholder-friendly, stable cash flow)
- 🚩 Declining Dividends: `dividend_trend == "decreasing"` (Possible cash flow issues)

### 6. Fundamental Analysis (Existing)

**Growth & Profitability**
- 🟢 Strong growth: `revenue_growth > 0.15`
- 🟢 Strong ROE: `return_on_equity > 0.15`
- 🚩 Low margins: `profit_margins < 0.05`

**Valuation**
- 🟢 Undervalued: `peg_ratio < 1.0`
- 🚩 Overvalued: `peg_ratio > 2.0`
- 🟢 PE Re-rating Potential: `forward_pe < trailing_pe`

**Leverage & Cash Flow**
- 🚩 High leverage: `debt_to_equity > 2.0`
- 🟢 Positive FCF: `free_cash_flow > 0`

### 5. Qualitative & Strategic Signals (Expanded)

The `check_strategic_triggers` tool now searches for:
- **Management**: Vision, ethics, track record.
- **Brand**: Reputation, sentiment.
- **Macro**: Inflation, interest rates, supply chain.
- **ESG**: Environmental, social, governance.

**GREEN FLAG Keywords:**
- "beat", "outperform", "strong results", "exceeded"
- "expansion", "new markets", "new clients", "growth"
- "visionary leadership", "strong brand loyalty", "resilient supply chain"
- "ESG leader", "sustainable", "ethical"

**RED FLAG Keywords:**
- "miss", "weak", "disappoint", "below expectations"
- "regulatory issues", "investigation", "lawsuit", "scandal"
- "management turnover", "insider selling", "toxic culture"
- "supply chain disruption", "inflationary pressure"

## Output Format

Structure your final analysis as:

1. **Brief Overview** (1 paragraph)
   - Summarize the company's current state.

2. **📊 Technical & Risk Profile**
   - Trend: Bullish/Bearish (based on SMA/MACD)
   - RSI Status: Overbought/Oversold/Neutral
   - Risk Level: Low/Medium/High (based on Volatility/Sharpe)

3. ** GREEN FLAGS**
   - List positive signals with **specific dates and quarters**.
   - Example: "Debt decreasing over last 4 quarters (Q3 2024, Q2 2024...)"
   - Example: "News (2024-10-15): Strong earnings beat reported"

4. ** RED FLAGS**
   - List concerns with **specific dates and quarters**.
   - Example: "Revenue declined in Q3 2024 vs Q2 2024"
   - Example: "News (2024-09-01): CEO investigation announced"

5. **💡 VERDICT**
   - **Buy** / **Sell** / **Hold**
   - Justify with a mix of Fundamentals, Technicals, and Qualitative factors.
   - **ALWAYS cite the date of news and specific quarters for trends.**
