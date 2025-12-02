"""
Interactive Chat Interface for Intrepidq Equity Analysis.
"""

import asyncio
import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from agents.chat_agent import build_chat_agent
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from context_engineering.prompts import chat_agent_prompt

app = typer.Typer()
console = Console()

@app.callback()
def callback() -> None:
    """Intrepidq Equity Chat CLI"""
    pass

def _history_to_messages(history: list[dict]) -> list:
    """Convert internal dict history to LangChain Message objects.
    Always prepend the system prompt.
    """
    msgs: list = [SystemMessage(content=chat_agent_prompt)]
    for entry in history:
        if entry["role"] == "user":
            msgs.append(HumanMessage(content=entry["content"]))
        else:
            msgs.append(AIMessage(content=entry["content"]))
    return msgs

def _extract_response_content(content: str | list) -> str:
    """Extract text content from potential list structure."""
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                text_parts.append(item["text"])
        return "".join(text_parts)
    return str(content)

async def run_chat_loop(initial_ticker: str | None = None) -> None:
    """Main chat loop."""
    console.print(
        Panel.fit(
            "[bold cyan]🤖 Intrepidq Equity Chat[/bold cyan]\n\n"
            "Ask questions about your analyzed stocks.\n"
            "Type [bold yellow]/help[/bold yellow] for commands, "
            "[bold yellow]/exit[/bold yellow] to quit.",
            border_style="cyan",
        )
    )

    agent = build_chat_agent()
    chat_history: list[dict] = []

    # Optional initial ticker context
    if initial_ticker:
        initial_msg = f"Tell me about {initial_ticker} based on the analysis."
        console.print(f"\n[bold green]You:[/bold green] {initial_msg}")
        chat_history.append({"role": "user", "content": initial_msg})
        with console.status("[bold green]Thinking...[/bold green]"):
            msgs = _history_to_messages(chat_history)
            result = await agent.ainvoke({"messages": msgs})
            response = _extract_response_content(result["messages"][-1].content)
        chat_history.append({"role": "assistant", "content": response})
        console.print("\n[bold blue]AI:[/bold blue]")
        console.print(Markdown(response))

    while True:
        try:
            user_input = Prompt.ask("\n[bold green]You[/bold green]")
            user_input = user_input.strip()
            if not user_input:
                continue
            # Commands
            if user_input.lower() in ["/exit", "/quit", "exit", "quit"]:
                console.print("[yellow]Goodbye![/yellow]")
                break
            if user_input.lower() == "/help":
                console.print(
                    Panel(
                        "[bold]Commands:[/bold]\n"
                        "- /tickers : List analyzed tickers\n"
                        "- /clear   : Clear conversation history\n"
                        "- /exit    : Exit chat",
                        title="Help",
                    )
                )
                continue
            if user_input.lower() == "/tickers":
                user_input = "List all analyzed tickers."
            if user_input.lower() == "/clear":
                chat_history = []
                console.print("[yellow]Conversation history cleared.[/yellow]")
                continue
            # Add user message
            chat_history.append({"role": "user", "content": user_input})
            with console.status("[bold green]Thinking...[/bold green]"):
                msgs = _history_to_messages(chat_history)
                result = await agent.ainvoke({"messages": msgs})
                response = _extract_response_content(result["messages"][-1].content)
            chat_history.append({"role": "assistant", "content": response})
            console.print("\n[bold blue]AI:[/bold blue]")
            console.print(Markdown(response))
        except KeyboardInterrupt:
            console.print("\n[yellow]Goodbye![/yellow]")
            break
        except Exception as e:
            console.print(f"\n[red]Error: {e}[/red]")

@app.command()
def start(ticker: str = typer.Argument(None)):
    """Start the chat interface."""
    asyncio.run(run_chat_loop(ticker))

if __name__ == "__main__":
    app()