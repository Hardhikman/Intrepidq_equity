from typing import TypedDict, Annotated, List, Dict, Any, Union
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from agents.data_agent import run_data_collection
from agents.validation_agent import run_validation
from agents.analysis_agent import run_analysis
from agents.synthesis_agent import run_synthesis

class AgentState(TypedDict):
    ticker: str
    data_result: Dict[str, Any]
    validation_result: Dict[str, Any]
    analysis_result: Dict[str, Any]
    final_report: str
    conflicts: List[Dict[str, Any]]

#Node Wrappers

async def data_collection_node(state: AgentState):
    from utils.cli_logger import logger
    ticker = state.get("ticker")
    if not ticker:
        raise ValueError("Missing 'ticker' in state for data_collection_node")
    
    # Explicit phase start logging
    logger.tracker.start_phase("Data Collection")
    logger.phase_detail("Data Collection", f"Collecting data for {ticker}")
    logger.console.print(f"\n[bold cyan]▶ Phase 1: Data Collection[/bold cyan] - Fetching financials, news, and signals for {ticker}")
    
    result = await run_data_collection(ticker)
    
    logger.console.print(f"[green]✓ Data Collection complete[/green]")
    return {"data_result": result}

async def validation_node(state: AgentState):
    from utils.cli_logger import logger
    ticker = state.get("ticker")
    data_result = state.get("data_result", {})
    
    if not ticker:
        raise ValueError("Missing 'ticker' in state for validation_node")
    
    # Phase tracking with spinner
    logger.tracker.start_phase("Validation")
    logger.phase_detail("Validation", f"Validating data for {ticker}")
    logger.console.print(f"\n[bold cyan]▶ Phase 2: Validation[/bold cyan] - Checking data quality and completeness")
    
    result = await run_validation(ticker, data_result)
    
    logger.console.print(f"[green]✓ Validation complete[/green] - Completeness: {result.get('completeness_score', 0):.0f}%")
    
    return {
        "validation_result": result,
        "conflicts": result.get("conflicts", [])
    }

async def human_review_node(state: AgentState):
    # This node is a pass-through. 
    # The interrupt happens BEFORE this node is executed.
    # When we resume, the state (specifically data_result) will have been updated by the user.
    return {}

async def analysis_node(state: AgentState):
    from utils.cli_logger import logger
    ticker = state["ticker"]
    data_result = state["data_result"]
    validation_result = state.get("validation_result", {})
    
    # Phase tracking with spinner
    logger.tracker.start_phase("Analysis")
    logger.phase_detail("Analysis", f"Analyzing {ticker}")
    logger.console.print(f"\n[bold cyan]▶ Phase 3: Analysis[/bold cyan] - Generating investment thesis for {ticker}")
    
    # Use enriched data if available (data filled from Alpha Vantage)
    enriched_data = validation_result.get("enriched_data")
    if enriched_data:
        data_result = {**data_result, "financial_data": enriched_data}
    
    result = await run_analysis(ticker, data_result)
    
    logger.console.print(f"[green]✓ Analysis complete[/green]")
    return {"analysis_result": result}

async def synthesis_node(state: AgentState):
    from utils.cli_logger import logger
    ticker = state["ticker"]
    analysis_result = state["analysis_result"]
    validation_result = state["validation_result"]
    data_result = state["data_result"]
    
    # Phase tracking with spinner
    logger.tracker.start_phase("Synthesis")
    logger.phase_detail("Synthesis", f"Generating report for {ticker}")
    logger.console.print(f"\n[bold cyan]▶ Phase 4: Synthesis[/bold cyan] - Compiling final report for {ticker}")
    
    report = await run_synthesis(ticker, analysis_result, validation_result, data_result)
    
    logger.console.print(f"[green]✓ Synthesis complete[/green]")
    return {"final_report": report}

#Conditional Logic

def should_human_review(state: AgentState):
    if state.get("conflicts") and len(state["conflicts"]) > 0:
        return "human_review"
    return "analysis"

#Graph Construction

def build_graph():
    workflow = StateGraph(AgentState)
    
    workflow.add_node("data_collection", data_collection_node)
    workflow.add_node("validation", validation_node)
    workflow.add_node("human_review", human_review_node)
    workflow.add_node("analysis", analysis_node)
    workflow.add_node("synthesis", synthesis_node)
    
    workflow.set_entry_point("data_collection")
    
    workflow.add_edge("data_collection", "validation")
    
    workflow.add_conditional_edges(
        "validation",
        should_human_review,
        {
            "human_review": "human_review",
            "analysis": "analysis"
        }
    )
    
    workflow.add_edge("human_review", "analysis")
    workflow.add_edge("analysis", "synthesis")
    workflow.add_edge("synthesis", END)
    
    # Compile with checkpointer to enable interrupts
    memory = MemorySaver()
    app = workflow.compile(checkpointer=memory, interrupt_before=["human_review"])
    
    return app
