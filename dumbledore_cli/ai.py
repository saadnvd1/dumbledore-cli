"""Claude CLI integration for AI responses."""

import shutil
import subprocess
import sys
from typing import Optional, Generator

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel

console = Console()


def check_claude_cli() -> bool:
    """Check if Claude CLI is installed."""
    return shutil.which("claude") is not None


def run_claude(prompt: str, system_context: Optional[str] = None) -> Optional[str]:
    """Run Claude CLI with a prompt (non-streaming).

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


def run_claude_stream(prompt: str, system_context: Optional[str] = None) -> Optional[str]:
    """Run Claude CLI with streaming output.

    Displays response as it streams, returns full response when done.
    """
    import json

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

    full_prompt = build_prompt(prompt, system_context)

    try:
        process = subprocess.Popen(
            ["claude", "-p", full_prompt, "--output-format", "stream-json", "--verbose", "--include-partial-messages"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        full_response = ""
        console.print()

        # Stream output with live markdown rendering
        with Live(Markdown("▌"), refresh_per_second=20, console=console, vertical_overflow="visible") as live:
            for line in iter(process.stdout.readline, ''):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    msg_type = data.get("type")

                    # Handle streaming events with partial messages
                    if msg_type == "stream_event":
                        event = data.get("event", {})
                        event_type = event.get("type")

                        if event_type == "content_block_delta":
                            delta = event.get("delta", {})
                            if delta.get("type") == "text_delta":
                                full_response += delta.get("text", "")
                                live.update(Markdown(full_response + "▌"))

                    elif msg_type == "result":
                        # Final result - use this as the definitive response
                        result_text = data.get("result", "")
                        if result_text:
                            full_response = result_text
                        live.update(Markdown(full_response))

                except json.JSONDecodeError:
                    pass

            # Final update without cursor
            if full_response:
                live.update(Markdown(full_response))

        process.wait()

        if process.returncode != 0:
            stderr = process.stderr.read()
            if stderr:
                console.print(f"[red]Claude error: {stderr}[/red]")
            return None

        console.print()
        return full_response.strip() if full_response else None

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
- If a "Writing Style to Match" section is provided, mimic that writing style in your responses

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


def display_response(response: str) -> None:
    """Display a response cleanly for easy copying."""
    console.print()
    console.print(Markdown(response))
    console.print()


def display_thinking() -> None:
    """Show a thinking indicator."""
    return console.status("[bold blue]Thinking...", spinner="dots")
