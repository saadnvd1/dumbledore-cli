"""Claude CLI integration for AI responses."""

import shutil
import subprocess
from typing import Optional

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

console = Console()


def check_claude_cli() -> bool:
    """Check if Claude CLI is installed."""
    return shutil.which("claude") is not None


def run_claude(prompt: str, system_context: Optional[str] = None) -> Optional[str]:
    """Run Claude CLI with a prompt.

    Args:
        prompt: The user's question/message
        system_context: Additional context to prepend (RAG results, profile, etc.)

    Returns:
        Claude's response or None if failed
    """
    if not check_claude_cli():
        console.print(
            Panel(
                "[yellow]Claude CLI not found.[/yellow]\n\n"
                "Install: npm install -g @anthropic-ai/claude-code\n"
                "Auth: claude login",
                title="Claude CLI Required",
                border_style="yellow",
            )
        )
        return None

    # Build full prompt with context
    full_prompt = build_prompt(prompt, system_context)

    try:
        result = subprocess.run(
            ["claude", "-p", full_prompt],
            capture_output=True,
            text=True,
            timeout=300,  # 5 min timeout for complex questions
        )
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            console.print(f"[red]Claude error: {result.stderr}[/red]")
            return None
    except subprocess.TimeoutExpired:
        console.print("[red]Claude timed out[/red]")
        return None
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return None


def build_prompt(user_message: str, context: Optional[str] = None) -> str:
    """Build the full prompt with system instructions and context."""

    system_prompt = """You are Dumbledore, a wise and thoughtful personal advisor. You have access to the user's personal notes and knowledge about their life, goals, projects, and values.

Your role is to:
1. Provide thoughtful, personalized advice based on what you know about them
2. Reference specific notes and past reflections when relevant
3. Challenge assumptions gently but directly when needed
4. Be concise but substantive - no fluff
5. Remember context from the conversation

Style:
- Speak naturally, not formally
- Be direct and honest, even when it's uncomfortable
- Draw connections between different areas of their life
- Ask clarifying questions when needed
- Avoid generic advice - make it specific to them

You're not just an AI assistant - you're a trusted advisor who knows them well."""

    if context:
        full_prompt = f"""{system_prompt}

---

{context}

---

User: {user_message}"""
    else:
        full_prompt = f"""{system_prompt}

---

User: {user_message}"""

    return full_prompt


def get_system_context_summary() -> str:
    """Get a brief summary for context-less queries."""
    return """Note: No specific notes were retrieved for this query.
Responding based on general conversation context only.
If this seems wrong, try being more specific or run 'dumbledore sync' to update the knowledge base."""


def display_response(response: str, title: str = "Dumbledore") -> None:
    """Display a response in a nice panel."""
    console.print()
    console.print(Panel(
        Markdown(response),
        title=f"[bold blue]{title}[/bold blue]",
        border_style="blue",
    ))


def display_thinking() -> None:
    """Show a thinking indicator."""
    return console.status("[bold blue]Thinking...", spinner="dots")
