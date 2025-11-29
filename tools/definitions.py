import os
from pathlib import Path
from typing import Dict, Any, List


from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool


import yfinance as yf
#from duckduckgo_search import DDGS
from ddgs import DDGS
from cachetools import cached, TTLCache
import pandas as pd
import numpy as np


# Cache for 1 hour (3600 seconds)
cache = TTLCache(maxsize=100, ttl=3600)


# Base directory for skills
# Adjusted path to look in the project root/context_engineering/skills
SKILLS_DIR = Path(__file__).parent.parent / "context_engineering" / "skills"



# =============================================================================
# PLANNING TOOL (no-op TODO list)
# =============================================================================


def _make_plan(goal: str) -> List[str]:
    """
    No-op planning tool: returns a rough todo list for deep equity analysis.

    Args:
        goal: High-level goal, e.g. 'Deep equity analysis for TSLA'

    This is mainly for 'context engineering' as per deep-agents:
    it forces the LLM to externalize a plan before calling other tools.
    """
    return [
        f"Goal: {goal}",
        "1. Call get_deep_financials on the ticker to gather fundamentals.",
        "2. Call check_strategic_triggers on the ticker to gather news and strategic signals.",
        "3. Call search_web for targeted research on any anomalies or specific questions.",
        "4. Load the 'equity_trigger_analysis' skill for domain-specific trigger rules.",
        "5. Combine fundamentals + news + skill instructions into:",
        "   - RED FLAGS (risks)",
        "   - GREEN FLAGS (strengths)",
        "   - VERDICT (Buy / Sell / Hold) with reasoning."
    ]


make_plan_tool = StructuredTool.from_function(
    name="make_plan",
    description=(
        "Create a todo list for how to perform a deep equity analysis on a stock. "
        "Use this BEFORE calling other tools so you plan the steps."
    ),
    func=_make_plan,
)



# =============================================================================
# SKILL LOADER TOOL
# =============================================================================


def _load_skill(name: str) -> str:
    """
    Load SKILL.md content for a given skill name.

    Args:
        name: Skill folder name under skills/, e.g. 'equity_trigger_analysis'

    The agent can then read and follow these instructions.
    """
    skill_dir = SKILLS_DIR / name
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.exists():
        return f"Skill '{name}' not found at {skill_file}."
    try:
        return skill_file.read_text(encoding="utf-8")
    except Exception as e:
        return f"Failed to read SKILL.md for '{name}': {e}"



load_skill_tool = StructuredTool.from_function(
    name="load_skill",
    description=(
        "Load instructions for a named skill from a SKILL.md file on disk. "
        "Use this to get domain-specific rules, like 'equity_trigger_analysis'."
    ),
    func=_load_skill,
)



# =============================================================================
# QUANT TOOL: DEEP FINANCIALS (YFINANCE)
# =============================================================================


@cached(cache)
def _get_deep_financials(ticker: str) -> Dict[str, Any]:
    """
    Fetch specific quantitative metrics for a stock using yfinance.

    Args:
        ticker: Stock ticker symbol (e.g., TSLA, AAPL, GOOGL)

    Returns a structured dict; the agent should interpret it using skills.
    """
    ticker = ticker.upper().strip()
    print(f" [Quant Tool] Fetching Deep Financials for {ticker}...")


    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        # --- 1. Historical Data & Technicals ---
        hist = stock.history(period="2y")
        technicals = {}
        risk_metrics = {}
        
        if not hist.empty:
            # SMA
            hist['SMA_50'] = hist['Close'].rolling(window=50).mean()
            hist['SMA_200'] = hist['Close'].rolling(window=200).mean()
            
            # RSI
            delta = hist['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            hist['RSI'] = 100 - (100 / (1 + rs))
            
            # MACD
            exp1 = hist['Close'].ewm(span=12, adjust=False).mean()
            exp2 = hist['Close'].ewm(span=26, adjust=False).mean()
            macd = exp1 - exp2
            signal = macd.ewm(span=9, adjust=False).mean()
            
            # Get latest values
            latest = hist.iloc[-1]
            technicals = {
                "current_price": latest['Close'],
                "sma_50": latest['SMA_50'] if not np.isnan(latest['SMA_50']) else None,
                "sma_200": latest['SMA_200'] if not np.isnan(latest['SMA_200']) else None,
                "rsi": latest['RSI'] if not np.isnan(latest['RSI']) else None,
                "macd": macd.iloc[-1] if not np.isnan(macd.iloc[-1]) else None,
                "macd_signal": signal.iloc[-1] if not np.isnan(signal.iloc[-1]) else None,
            }
            
            # --- 2. Risk Metrics ---
            daily_returns = hist['Close'].pct_change().dropna()
            volatility = daily_returns.std() * np.sqrt(252)
            
            # Max Drawdown
            rolling_max = hist['Close'].cummax()
            drawdown = (hist['Close'] - rolling_max) / rolling_max
            max_drawdown = drawdown.min()
            
            # Sharpe Ratio (Simplified, assuming 0% risk free for now)
            sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252) if daily_returns.std() != 0 else 0
            
            risk_metrics = {
                "volatility_annualized": volatility,
                "max_drawdown": max_drawdown,
                "sharpe_ratio": sharpe,
            }

        # --- 3. Financial Trends (Quarterly) ---
        # Attempt to get quarterly financials for trend analysis
        financial_trends = {}
        try:
            q_fin = stock.quarterly_financials
            q_bal = stock.quarterly_balance_sheet
            q_cf = stock.quarterly_cashflow
            
            if not q_fin.empty and not q_bal.empty:
                # Extract dates and convert to string
                quarter_dates = [d.strftime('%Y-%m-%d') for d in q_fin.columns[:4]] if not q_fin.empty else []
                
                # Revenue & Debt (existing)
                recent_rev = q_fin.loc['Total Revenue'].head(4).tolist() if 'Total Revenue' in q_fin.index else []
                recent_debt = q_bal.loc['Total Debt'].head(4).tolist() if 'Total Debt' in q_bal.index else []
                
                # CapEx Tracking (NEW)
                recent_capex = []
                if not q_cf.empty and 'Capital Expenditure' in q_cf.index:
                    recent_capex = q_cf.loc['Capital Expenditure'].head(4).tolist()
                elif not q_cf.empty and 'Capital Expenditures' in q_cf.index:
                    recent_capex = q_cf.loc['Capital Expenditures'].head(4).tolist()
                
                capex_trend = "increasing" if len(recent_capex) > 1 and abs(recent_capex[0]) > abs(recent_capex[1]) else "decreasing"
                
                # Retained Earnings (NEW)
                recent_retained_earnings = []
                if 'Retained Earnings' in q_bal.index:
                    recent_retained_earnings = q_bal.loc['Retained Earnings'].head(4).tolist()
                
                retained_earnings_trend = "increasing" if len(recent_retained_earnings) > 1 and recent_retained_earnings[0] > recent_retained_earnings[1] else "decreasing"

                financial_trends = {
                    "quarter_dates": quarter_dates, # [Newest, ..., Oldest]
                    "revenue_quarters": recent_rev, 
                    "debt_quarters": recent_debt,
                    "capex_quarters": recent_capex,
                    "retained_earnings_quarters": recent_retained_earnings,
                    "revenue_trend": "increasing" if len(recent_rev) > 1 and recent_rev[0] > recent_rev[1] else "decreasing",
                    "debt_trend": "decreasing" if len(recent_debt) > 1 and recent_debt[0] < recent_debt[1] else "increasing",
                    "capex_trend": capex_trend,
                    "retained_earnings_trend": retained_earnings_trend
                }
        except Exception as e:
            print(f"Warning: Could not fetch financial trends: {e}")
        
        # --- 4. Volume Trends (NEW) ---
        volume_trends = {}
        if not hist.empty and 'Volume' in hist.columns:
            # Calculate average volume for different periods
            avg_volume_10d = hist['Volume'].tail(10).mean()
            avg_volume_50d = hist['Volume'].tail(50).mean()
            avg_volume_200d = hist['Volume'].tail(200).mean()
            
            # Recent volume spike detection
            latest_volume = hist['Volume'].iloc[-1]
            volume_spike = latest_volume > (avg_volume_50d * 1.5)  # 50% above average
            
            volume_trends = {
                "latest_volume": int(latest_volume),
                "avg_volume_10d": int(avg_volume_10d),
                "avg_volume_50d": int(avg_volume_50d),
                "avg_volume_200d": int(avg_volume_200d),
                "volume_spike": volume_spike,
                "volume_trend": "increasing" if avg_volume_10d > avg_volume_50d else "decreasing"
            }
        
        # --- 5. Dividend Yield Trend (NEW) ---
        dividend_trends = {}
        try:
            dividends = stock.dividends
            if not dividends.empty and len(dividends) > 0:
                # Get annual dividends for last 3 years
                annual_divs = dividends.resample('Y').sum()
                recent_annual_divs = annual_divs.tail(3).tolist()
                div_years = [d.strftime('%Y') for d in annual_divs.tail(3).index]
                
                dividend_trends = {
                    "annual_dividends": recent_annual_divs,
                    "dividend_years": div_years,
                    "dividend_trend": "increasing" if len(recent_annual_divs) > 1 and recent_annual_divs[-1] > recent_annual_divs[-2] else "decreasing"
                }
        except Exception as e:
            print(f"Warning: Could not fetch dividend trends: {e}")

        financial_data = {
            "ticker": ticker,
            # Basic Info
            "current_price": info.get("currentPrice"),
            "market_cap": info.get("marketCap"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            
            # Growth & Margins
            "revenue_growth": info.get("revenueGrowth"),
            "profit_margins": info.get("profitMargins"),
            
            # Valuation
            "trailing_pe": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "peg_ratio": info.get("pegRatio"),
            "price_to_book": info.get("priceToBook"),
            
            # Dividends
            "dividend_yield": info.get("dividendYield"),
            "payout_ratio": info.get("payoutRatio"),
            
            # Returns
            "return_on_equity": info.get("returnOnEquity"),
            "return_on_assets": info.get("returnOnAssets"),
            
            # Debt & Cash
            "debt_to_equity": info.get("debtToEquity"),
            "total_debt": info.get("totalDebt"),
            "free_cash_flow": info.get("freeCashflow"),
            "operating_cashflow": info.get("operatingCashflow"),
            
            # New: Technicals & Risk
            "technicals": technicals,
            "risk_metrics": risk_metrics,
            "financial_trends": financial_trends,
            "volume_trends": volume_trends,
            "dividend_trends": dividend_trends
        }

        return {
            "status": "success",
            "data": financial_data,
        }

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"Failed to fetch financials for {ticker}: {e}",
        }



get_deep_financials_tool = StructuredTool.from_function(
    name="get_deep_financials",
    description=(
        "Fetch detailed quantitative financial metrics for a stock ticker, "
        "including revenue growth, margins, debt, cash flow, and valuation metrics."
    ),
    func=_get_deep_financials,
)



# =============================================================================
# NEWS TOOL: STRATEGIC TRIGGERS (DUCKDUCKGO)
# =============================================================================


def _check_strategic_triggers(ticker: str) -> Dict[str, Any]:
    """
    Search news for qualitative 'green flag' or 'red flag' strategic signals.

    Args:
        ticker: Stock ticker symbol to scan for news signals

    Uses DuckDuckGo search (DDGS) synchronously for simplicity.
    """
    ticker = ticker.upper().strip()
    print(f" [News Tool] Scanning headlines for {ticker}...")


    search_queries = [
        # Original Strategic Triggers
        f"{ticker} quarterly earnings beat guidance estimates",
        f"{ticker} company acquisition merger deal",
        f"{ticker} expansion new market new clients",
        f"{ticker} new product innovation R&D investment",
        f"{ticker} industry sector trends tailwinds",
        
        # New Qualitative Triggers
        f"{ticker} management leadership vision ethics CEO track record",
        f"{ticker} brand reputation sentiment customer trust",
        f"{ticker} macroeconomic impact interest rates inflation supply chain",
        f"{ticker} ESG environment social governance rating controversy",
        f"{ticker} insider trading management buying selling",
    ]


    signals: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []


    for q in search_queries:
        try:
            with DDGS() as ddgs:
                results = list(ddgs.news(q, max_results=3))
            if results:
                for r in results:
                    signals.append(
                        {
                            "query": q,
                            "title": r.get("title"),
                            "date": r.get("date"),
                            "url": r.get("url", ""),
                        }
                    )
        except Exception as e:
            errors.append({"query": q, "error": str(e)})


    if not signals:
        summary = "No specific strategic signals found in recent news."
    else:
        parts = []
        for s in signals:
            parts.append(
                f"🔎 Query: {s['query']}\n"
                f"   Title: {s['title']}\n"
                f"   Date: {s['date']}"
            )
        summary = "\n\n".join(parts)


    return {
        "status": "success",
        "data": {
            "ticker": ticker,
            "signals": signals,
            "signals_found": len(signals),
            "total_queries": len(search_queries),
            "summary": summary,
            "errors": errors or None,
        },
    }



check_strategic_triggers_tool = StructuredTool.from_function(
    name="check_strategic_triggers",
    description=(
        "Search recent news and headlines for strategic signals about a stock, "
        "including earnings beats, M&A, expansion, innovation, and industry trends."
    ),
    func=_check_strategic_triggers,
)



# Convenience export
# =============================================================================
# WEB SEARCH TOOL (GENERAL)
# =============================================================================


def _search_web(query: str) -> List[Dict[str, str]]:
    """
    Perform a general web search for a given query.
    
    Args:
        query: The search query string.
        
    Returns:
        List of top 5 search results with title, snippet, and link.
    """
    print(f" [Web Search] Searching for: {query}...")
    results = []
    try:
        with DDGS() as ddgs:
            # text() is the general search method in duckduckgo_search
            # It returns a generator, so we convert to list
            search_results = list(ddgs.text(query, max_results=5))
            
        for r in search_results:
            results.append({
                "title": r.get("title"),
                "snippet": r.get("body"),
                "link": r.get("href")
            })
            
    except Exception as e:
        return [{"error": f"Search failed: {str(e)}"}]
        
    return results


search_web_tool = StructuredTool.from_function(
    name="search_web",
    description=(
        "Perform a general web search to find information on any topic. "
        "Use this to investigate specific questions, verify claims, or find recent events "
        "that might explain financial anomalies."
    ),
    func=_search_web,
)


# Convenience export
ALL_TOOLS = [
    make_plan_tool,
    load_skill_tool,
    get_deep_financials_tool,
    check_strategic_triggers_tool,
    search_web_tool,
]
