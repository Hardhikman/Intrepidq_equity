from typing import Dict, Any, List
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.prebuilt import create_react_agent

from tools.definitions import (
    get_deep_financials_tool,
    check_strategic_triggers_tool,
    search_web_tool,
    search_google_news_tool
)
from context_engineering.prompts import data_agent_prompt
from utils.llm_helper import get_llm_with_fallback
import numpy as np

def _convert_numpy_types(obj):
    """Recursively convert numpy types to native Python types for serialization."""
    if isinstance(obj, dict):
        return {k: _convert_numpy_types(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_numpy_types(item) for item in obj]
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, (np.floating,)):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return _convert_numpy_types(obj.tolist())
    elif isinstance(obj, np.bool_):
        return bool(obj)
    else:
        return obj

def build_data_agent(use_fallback: bool = False):
    """
    Builds the Data Collection Agent using LangGraph.
    """
    llm = get_llm_with_fallback(temperature=0, use_fallback=use_fallback)
    
    tools = [
        get_deep_financials_tool,
        check_strategic_triggers_tool,
        search_web_tool,
        search_google_news_tool
    ]
    
    # create_react_agent returns a CompiledGraph
    agent = create_react_agent(llm, tools)
    return agent

async def run_data_collection(ticker: str) -> Dict[str, Any]:
    """
    Run the data collection process for a ticker.
    """
    from utils.cli_logger import logger
    
    agent = build_data_agent()
    
    # Start phase tracking with spinner
    logger.tracker.start_phase("Data Collection")
    logger.phase_detail("Data Collection", f"Collecting data for {ticker}")
    
    # Extract system message from the prompt template
    system_message = data_agent_prompt.messages[0].prompt.template
    
    user_input = f"Collect all available data for {ticker}. Get financials, strategic triggers, and recent news."
    
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_input}
    ]
        
    result = await agent.ainvoke({"messages": messages})
    
    # Result from LangGraph agent is usually a dict with 'messages'
    # The last message is the AI response
    last_message = result["messages"][-1]
    output_content = last_message.content
    
    # Extract financial data from tool messages in history AND log tool usage
    financial_data = {}
    from langchain_core.messages import ToolMessage, AIMessage

    # Log tool usage from history
    for msg in result["messages"]:
        if isinstance(msg, AIMessage) and msg.tool_calls:
             for tool_call in msg.tool_calls:
                 logger.log_tool_used(tool_call['name'], tool_call['args'])
    
    for msg in result["messages"]:
        if isinstance(msg, ToolMessage) and msg.name == "get_deep_financials":
            # The content is usually a string representation of the dict
            # We might need to parse it or rely on the fact that we just want to pass it to validation
            # But validation expects a dict.
            # Let's try to eval it if it's a string, or check if it's already a dict (unlikely for ToolMessage content)
            import json
            import ast
            import re
            
            data = None
            try:
                if isinstance(msg.content, dict):
                    # Already a dict
                    data = msg.content
                elif isinstance(msg.content, str):
                    # String - try parsing
                    content_str = msg.content
                    
                    # Try JSON first
                    try:
                        data = json.loads(content_str)
                    except json.JSONDecodeError:
                        
                        # Sanitize string for ast.literal_eval
                        # Replace numpy/Python float references with None or string equivalents
                        fixed_str = re.sub(r'\bnp\.nan\b', 'None', content_str)
                        fixed_str = re.sub(r'\bnp\.inf\b', 'None', fixed_str)
                        fixed_str = re.sub(r'\bfloat\([\'"]inf[\'"]\)', 'None', fixed_str)
                        fixed_str = re.sub(r'\bfloat\([\'"]nan[\'"]\)', 'None', fixed_str)
                        fixed_str = re.sub(r'(?<![a-zA-Z_])\binf\b(?![a-zA-Z_])', 'None', fixed_str)
                        fixed_str = re.sub(r'(?<![a-zA-Z_])\bnan\b(?![a-zA-Z_])', 'None', fixed_str)
                        fixed_str = re.sub(r'(?<![a-zA-Z_])\bNaN\b(?![a-zA-Z_])', 'None', fixed_str)
                        fixed_str = re.sub(r'(?<![a-zA-Z_])\bInfinity\b(?![a-zA-Z_])', 'None', fixed_str)
                        fixed_str = re.sub(r'(?<![a-zA-Z_])\b-Infinity\b(?![a-zA-Z_])', 'None', fixed_str)
                        
                        try:
                            data = ast.literal_eval(fixed_str)
                        except (ValueError, SyntaxError) as e_ast:
                            logger.log_warning(f"Failed to parse tool output with ast.literal_eval: {e_ast}")
                
                if data and isinstance(data, dict) and data.get("status") == "success":
                    financial_data = data.get("data", {})
                    logger.log_success(f"Successfully extracted financial data for {ticker}")
                    break
            except (json.JSONDecodeError, ValueError, SyntaxError, TypeError, KeyError) as e:
                logger.log_error(f"Error parsing financial data: {e}")

    # Convert numpy types to native Python types for LangGraph serialization
    financial_data = _convert_numpy_types(financial_data)
    
    if not financial_data:
        logger.log_warning("No financial_data extracted from tool outputs!")
    else:
        # Log financial data to CLI with Rich table
        logger.log_financial_data(financial_data)
    
    return {
        "ticker": ticker,
        "raw_output": output_content,
        "financial_data": financial_data
    }
