import os
import re
from pathlib import Path
from typing import Dict, Any, List


from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool


import yfinance as yf
from ddgs import DDGS
from cachetools import cached, TTLCache
import pandas as pd
import numpy as np


# Cache for 1 hour (3600 seconds)
cache = TTLCache(maxsize=100, ttl=3600)


# Base directory for skills
SKILLS_DIR = Path(__file__).parent.parent / "context_engineering" / "skills"



# PLANNING TOOL (no-op TODO list)


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



# SKILL LOADER TOOL


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



# QUANT TOOL: DEEP FINANCIALS (YFINANCE)


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
        
        #1. Historical Data & Technicals 
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
            
            #2. Risk Metrics 
            daily_returns = hist['Close'].pct_change().dropna()
            volatility = daily_returns.std() * np.sqrt(252)
            
            # Max Drawdown
            rolling_max = hist['Close'].cummax()
            drawdown = (hist['Close'] - rolling_max) / rolling_max
            max_drawdown = drawdown.min()
            
            # Sharpe Ratio (Simplified, assuming 0% risk free for now)
            sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252) if daily_returns.std() != 0 else 0
            
            # Value at Risk (VaR) - 95% confidence
            # The 5th percentile of daily returns
            var_95 = daily_returns.quantile(0.05)
            
            risk_metrics = {
                "volatility_annualized": volatility,
                "max_drawdown": max_drawdown,
                "sharpe_ratio": sharpe,
                "value_at_risk_95": var_95,
            }

        #3. Financial Trends (Quarterly & Annual)
        # Comprehensive trend analysis: both quarterly and annual
        financial_trends = {}
        try:
            #QUARTERLY TRENDS
            q_fin = stock.quarterly_financials
            q_bal = stock.quarterly_balance_sheet
            q_cf = stock.quarterly_cashflow
            
            quarterly_data = {}
            if not q_fin.empty and not q_bal.empty:
                # Extract dates and convert to string
                quarter_dates = [d.strftime('%Y-%m-%d') for d in q_fin.columns[:4]] if not q_fin.empty else []
                
                # Revenue & Debt
                recent_rev = q_fin.loc['Total Revenue'].head(4).tolist() if 'Total Revenue' in q_fin.index else []
                recent_debt = q_bal.loc['Total Debt'].head(4).tolist() if 'Total Debt' in q_bal.index else []
                
                # CapEx Tracking
                recent_capex = []
                if not q_cf.empty and 'Capital Expenditure' in q_cf.index:
                    recent_capex = q_cf.loc['Capital Expenditure'].head(4).tolist()
                elif not q_cf.empty and 'Capital Expenditures' in q_cf.index:
                    recent_capex = q_cf.loc['Capital Expenditures'].head(4).tolist()
                
                # Retained Earnings
                recent_retained_earnings = []
                if 'Retained Earnings' in q_bal.index:
                    recent_retained_earnings = q_bal.loc['Retained Earnings'].head(4).tolist()
                
                # Net Income
                recent_net_income = []
                if 'Net Income' in q_fin.index:
                    recent_net_income = q_fin.loc['Net Income'].head(4).tolist()
                
                quarterly_data = {
                    "quarter_dates": quarter_dates,  # [Newest, ..., Oldest]
                    "revenue_quarters": recent_rev, 
                    "debt_quarters": recent_debt,
                    "capex_quarters": recent_capex,
                    "retained_earnings_quarters": recent_retained_earnings,
                    "net_income_quarters": recent_net_income,
                    # Quarterly trends (Q-o-Q)
                    "revenue_trend_qoq": "increasing" if len(recent_rev) > 1 and recent_rev[0] > recent_rev[1] else "decreasing",
                    "debt_trend_qoq": "decreasing" if len(recent_debt) > 1 and recent_debt[0] < recent_debt[1] else "increasing",
                    "capex_trend_qoq": "increasing" if len(recent_capex) > 1 and abs(recent_capex[0]) > abs(recent_capex[1]) else "decreasing",
                    "retained_earnings_trend_qoq": "increasing" if len(recent_retained_earnings) > 1 and recent_retained_earnings[0] > recent_retained_earnings[1] else "decreasing",
                    "net_income_trend_qoq": "increasing" if len(recent_net_income) > 1 and recent_net_income[0] > recent_net_income[1] else "decreasing",
                }
            
            #ANNUAL TRENDS 
            a_fin = stock.financials  # Annual financials
            a_bal = stock.balance_sheet  # Annual balance sheet
            a_cf = stock.cashflow  # Annual cashflow
            
            annual_data = {}
            if not a_fin.empty and not a_bal.empty:
                # Extract year dates (last 3 years)
                year_dates = [d.strftime('%Y') for d in a_fin.columns[:3]] if not a_fin.empty else []
                
                # Annual Revenue
                annual_rev = a_fin.loc['Total Revenue'].head(3).tolist() if 'Total Revenue' in a_fin.index else []
                
                # Annual Debt
                annual_debt = a_bal.loc['Total Debt'].head(3).tolist() if 'Total Debt' in a_bal.index else []
                
                # Annual CapEx
                annual_capex = []
                if not a_cf.empty and 'Capital Expenditure' in a_cf.index:
                    annual_capex = a_cf.loc['Capital Expenditure'].head(3).tolist()
                elif not a_cf.empty and 'Capital Expenditures' in a_cf.index:
                    annual_capex = a_cf.loc['Capital Expenditures'].head(3).tolist()
                
                # Annual Retained Earnings
                annual_retained_earnings = []
                if 'Retained Earnings' in a_bal.index:
                    annual_retained_earnings = a_bal.loc['Retained Earnings'].head(3).tolist()
                
                # Annual Net Income
                annual_net_income = []
                if 'Net Income' in a_fin.index:
                    annual_net_income = a_fin.loc['Net Income'].head(3).tolist()
                
                # Annual Total Assets
                annual_assets = []
                if 'Total Assets' in a_bal.index:
                    annual_assets = a_bal.loc['Total Assets'].head(3).tolist()
                
                annual_data = {
                    "year_dates": year_dates,  # [Newest, ..., Oldest]
                    "revenue_annual": annual_rev,
                    "debt_annual": annual_debt,
                    "capex_annual": annual_capex,
                    "retained_earnings_annual": annual_retained_earnings,
                    "net_income_annual": annual_net_income,
                    "total_assets_annual": annual_assets,
                    # Annual trends (Y-o-Y)
                    "revenue_trend_yoy": "increasing" if len(annual_rev) > 1 and annual_rev[0] > annual_rev[1] else "decreasing",
                    "debt_trend_yoy": "decreasing" if len(annual_debt) > 1 and annual_debt[0] < annual_debt[1] else "increasing",
                    "capex_trend_yoy": "increasing" if len(annual_capex) > 1 and abs(annual_capex[0]) > abs(annual_capex[1]) else "decreasing",
                    "retained_earnings_trend_yoy": "increasing" if len(annual_retained_earnings) > 1 and annual_retained_earnings[0] > annual_retained_earnings[1] else "decreasing",
                    "net_income_trend_yoy": "increasing" if len(annual_net_income) > 1 and annual_net_income[0] > annual_net_income[1] else "decreasing",
                    "assets_trend_yoy": "increasing" if len(annual_assets) > 1 and annual_assets[0] > annual_assets[1] else "decreasing",
                }
            
            # Combine both quarterly and annual trends
            financial_trends = {
                "quarterly": quarterly_data,
                "annual": annual_data,
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
                annual_divs = dividends.resample('YE').sum()  # 'YE' = Year End (Y is deprecated)
                recent_annual_divs = annual_divs.tail(3).tolist()
                div_years = [d.strftime('%Y') for d in annual_divs.tail(3).index]
                
                dividend_trends = {
                    "annual_dividends": recent_annual_divs,
                    "dividend_years": div_years,
                    "dividend_trend": "increasing" if len(recent_annual_divs) > 1 and recent_annual_divs[-1] > recent_annual_divs[-2] else "decreasing"
                }
        except Exception as e:
            print(f"Warning: Could not fetch dividend trends: {e}")

        #6. ROCE Calculation (NEW)
        # ROCE = EBIT / (Total Assets - Current Liabilities)
        roce = None
        try:
            # Try to get from annual financials first
            if not a_fin.empty and not a_bal.empty:
                # EBIT
                ebit = None
                if 'EBIT' in a_fin.index:
                    ebit = a_fin.loc['EBIT'].iloc[0]
                elif 'Pretax Income' in a_fin.index and 'Interest Expense' in a_fin.index:
                     # Approximation: EBIT ~ Pretax Income + Interest Expense
                     ebit = a_fin.loc['Pretax Income'].iloc[0] + abs(a_fin.loc['Interest Expense'].iloc[0])

                # Capital Employed
                total_assets = a_bal.loc['Total Assets'].iloc[0] if 'Total Assets' in a_bal.index else None
                current_liabilities = None
                if 'Total Current Liabilities' in a_bal.index:
                    current_liabilities = a_bal.loc['Total Current Liabilities'].iloc[0]
                elif 'Current Liabilities' in a_bal.index: # Sometimes named differently
                     current_liabilities = a_bal.loc['Current Liabilities'].iloc[0]
                
                if ebit is not None and total_assets is not None and current_liabilities is not None:
                    capital_employed = total_assets - current_liabilities
                    if capital_employed != 0:
                        roce = ebit / capital_employed

        except Exception as e:
            print(f"Warning: Could not calculate ROCE: {e}")

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
            "return_on_capital_employed": roce,
            
            # Risk
            "beta": info.get("beta"),
            
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



# NEWS TOOL: STRATEGIC TRIGGERS (DUCKDUCKGO)


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

        # Investor Relations & Transparency
        f"{ticker} investor presentation earnings call transcript",
        f"{ticker} annual report integrated report",
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
# WEB SEARCH TOOL (GENERAL)


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
# GOOGLE NEWS TOOL

class SearchResult(BaseModel):
    title: str
    url: str
    published_date: str = ""

def _parse_rss_content(xml_content: str, max_results: int) -> List[SearchResult]:
    """Parse Google News RSS XML content."""
    import xml.etree.ElementTree as ET
    from email.utils import parsedate_to_datetime
    
    results = []
    try:
        root = ET.fromstring(xml_content)
        for item in root.findall('.//item')[:max_results]:
            title = item.find('title').text if item.find('title') is not None else "No title"
            link = item.find('link').text if item.find('link') is not None else ""
            pub_date = item.find('pubDate').text if item.find('pubDate') is not None else ""
            
            results.append(SearchResult(title=title, url=link, published_date=pub_date))
    except Exception as e:
        print(f"Error parsing RSS: {e}")
    
    return results

def _resolve_google_news_url(url: str) -> str:
    if not url or 'news.google.com' not in url:
        return url
    try:
        from googlenewsdecoder import gnewsdecoder
        result = gnewsdecoder(url, interval=1)
        if result.get("status"):
            return result["decoded_url"]
        return url
    except ImportError:
        print("Warning: googlenewsdecoder not installed. Returning original URL.")
        return url
    except Exception as e:
        print(f"Error resolving URL {url}: {e}")
        return url

def _search_google_news(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """
    Search Google News for articles matching a given query.
    """
    import requests
    from concurrent.futures import ThreadPoolExecutor
    
    print(f" [Google News] Searching for: {query}...")
    
    search_url = f"https://news.google.com/rss/search?q={query.replace(' ', '%20')}&hl=en-US&gl=US&ceid=US:en"

    try:
        response = requests.get(search_url, timeout=10)
        if response.status_code != 200:
            return []
        
        results = _parse_rss_content(response.text, max_results)
        
        urls_to_resolve = [result.url for result in results]
        with ThreadPoolExecutor() as executor:
            resolved_urls = list(executor.map(_resolve_google_news_url, urls_to_resolve))

        final_results = []
        for r, resolved in zip(results, resolved_urls):
            final_results.append({
                "title": r.title,
                "url": resolved,
                "published_date": r.published_date
            })
            
        return final_results
        
    except Exception as e:
        print(f"Error searching Google News: {e}")
        return []

search_google_news_tool = StructuredTool.from_function(
    name="search_google_news",
    description=(
        "Search Google News for recent articles and current events. "
        "Useful for finding latest news on companies, earnings, or specific topics."
    ),
    func=_search_google_news,
)


# Convenience export
ALL_TOOLS = [
    make_plan_tool,
    load_skill_tool,
    get_deep_financials_tool,
    check_strategic_triggers_tool,
    search_web_tool,
    search_google_news_tool,
]


def resolve_ticker(query: str) -> str:
    """
    Resolve a company name or query to a stock ticker symbol.
    
    Args:
        query: Company name (e.g., "Apple", "Tesla") or ticker.
        
    Returns:
        The resolved ticker symbol (e.g., "AAPL", "TSLA").
        Returns the original query (upper-cased) if resolution fails.
    """
    query = query.strip()
    
    # If it looks like a ticker (2-5 chars, all letters), assume it is one
    if query.isalpha() and 2 <= len(query) <= 5 and query.isupper():
        return query
        
    print(f" 🔍 Resolving ticker for '{query}'...")
    
    try:
        # Use DuckDuckGo to find the ticker
        search_query = f"stock ticker symbol for {query}"
        with DDGS() as ddgs:
            results = list(ddgs.text(search_query, max_results=1))
            
        if results:
            # Look for patterns like "AAPL" or "(AAPL)" in the title or snippet
            text = results[0]['title'] + " " + results[0]['body']
            
            # Regex for common ticker patterns: (AAPL), : AAPL, $AAPL
            # Updated to support longer tickers (e.g. NSE: DATAPATTNS is 10 chars)
            match = re.search(r'\b[A-Z]{2,12}\b', text)
            
            # Refined regex to prioritize parenthesized tickers which are common in search results
            # e.g. "Apple Inc. (AAPL)"
            explicit_match = re.search(r'\(([A-Z]{2,12})\)', text)
            if explicit_match:
                return explicit_match.group(1)
                
            # Fallback to finding the most likely capitalized word if it looks like a ticker
            # This is a heuristic; might need refinement.
            # Let's try to extract the first valid ticker-looking string
            # that is NOT a common word.
            
            # Simple approach: If user typed "Apple", and we find "AAPL", return AAPL.
            # Let's just return the user query upper-cased if we can't be sure, 
            # but usually the search result title has it.
            
            # Let's try a direct search for the symbol
            for word in text.split():
                clean_word = word.strip('()[]{},.')
                if clean_word.isupper() and 2 <= len(clean_word) <= 12 and clean_word != "NYSE" and clean_word != "NASDAQ":
                     # Verify with yfinance to be sure? 
                     # That might be too slow. Let's trust the search for now.
                     return clean_word
                     
    except Exception as e:
        print(f"Warning: Ticker resolution failed: {e}")
        
    return query.upper()


