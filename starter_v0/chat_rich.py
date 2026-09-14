from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from env_loader import load_lab_env
from providers import make_provider
from tools import load_tool_declarations, to_openai_tools
from versioning import artifact_version_dict, build_artifact_version

from chat import run_model_tool_loop, trim_history, write_transcript, now_iso, safe_slug, json_text


ROOT = Path(__file__).parent
ARTIFACTS_DIR = ROOT / "artifacts"
load_lab_env(ROOT)

console = Console()


def render_turn(result: dict) -> None:
    status = result.get("status", "")
    color = {"answered": "green", "waiting_for_user": "yellow",
             "max_tool_rounds": "red", "provider_error": "red"}.get(status, "white")
    console.print(Panel(f"[bold {color}]status: {status}[/]",
                        title="Turn result", expand=False))
    for rnd in result.get("rounds", []):
        calls = rnd.get("tool_calls", [])
        results = rnd.get("tool_results", [])
        if calls:
            table = Table(title=f"Round {rnd.get('round')} tool calls",
                          show_lines=True)
            table.add_column("Tool", style="cyan", no_wrap=True)
            table.add_column("Args", style="white")
            for c in calls:
                table.add_row(c.get("name", ""),
                              json_text(c.get("args", {}), max_chars=800))
            console.print(table)
        for ev in results:
            res = ev.get("result", {})
            is_err = isinstance(res, dict) and res.get("error")
            style = "red" if is_err else "green"
            console.print(Panel(json_text(res, max_chars=2000),
                                title=f"[{style}]{ev.get('tool')} result[/]",
                                border_style=style, expand=False))
    if result.get("status") == "provider_error":
        console.print(Panel(result.get("error", "unknown error"),
                            title="[red]Provider error[/]", border_style="red"))
    else:
        console.print(Panel(Markdown(result.get("assistant_text") or "(empty)"),
                            title="[bold green]Agent[/]", border_style="green"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Rich IT Helpdesk Agent chat.")
    parser.add_argument("--provider", choices=["openrouter", "openai", "anthropic", "gemini"], required=True)
    parser.add_argument("--model", default=None)
    parser.add_argument("--version", required=True)
    parser.add_argument("--system-prompt", type=Path, default=ARTIFACTS_DIR / "system_prompt.md")
    parser.add_argument("--tools", type=Path, default=ARTIFACTS_DIR / "tools.yaml")
    parser.add_argument("--transcripts-dir", type=Path, default=ROOT / "transcripts")
    parser.add_argument("--history-window", type=int, default=5)
    parser.add_argument("--max-tool-rounds", type=int, default=4)
    args = parser.parse_args()

    system_prompt = args.system_prompt.read_text(encoding="utf-8")
    tool_declarations = load_tool_declarations(args.tools)
    openai_tools = to_openai_tools(tool_declarations)
    provider = make_provider(args.provider)
    selected_model = args.model or getattr(provider, "default_model", None)
    artifact_version = build_artifact_version(args.version, args.system_prompt, args.tools)

    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    transcript_id = "_".join([safe_slug(args.version), safe_slug(args.provider), "rich", timestamp])
    transcript_path = args.transcripts_dir / f"{transcript_id}.transcript.json"
    transcript = {
        "transcript_id": transcript_id,
        **artifact_version_dict(artifact_version),
        "provider": args.provider,
        "model": selected_model,
        "system_prompt": str(args.system_prompt),
        "tools": str(args.tools),
        "history_window": args.history_window,
        "max_tool_rounds": args.max_tool_rounds,
        "ui": "chat_rich",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "turns": [],
    }

    console.print(Panel(
        f"[bold]IT Helpdesk Agent[/]\n"
        f"artifact: [cyan]{artifact_version.artifact_version}[/]\n"
        f"provider: [cyan]{args.provider}[/]  model: [cyan]{selected_model}[/]\n"
        f"tools: [cyan]{len(openai_tools)}[/]  history: {args.history_window}  rounds: {args.max_tool_rounds}\n"
        f"Type [bold]/exit[/] to stop.",
        title="[bold magenta]Northstar Labs service desk[/]", border_style="magenta"))

    history: list[dict[str, str]] = []
    turn_index = 0
    while True:
        try:
            user_text = Prompt.ask("\n[bold cyan]You[/]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break
        if not user_text:
            continue
        if user_text in {"/exit", "/quit"}:
            break

        turn_index += 1
        messages = [
            {"role": "system", "content": system_prompt},
            *trim_history(history, args.history_window),
            {"role": "user", "content": user_text},
        ]
        turn_record = {"turn_index": turn_index, "started_at": now_iso(),
                       "user": user_text, "status": "started",
                       "assistant_text": None, "rounds": [], "tool_events": []}
        try:
            with console.status("[bold green]Thinking + calling tools...[/]"):
                result = run_model_tool_loop(
                    provider=provider, messages=messages, tools=openai_tools,
                    model=args.model, max_tool_rounds=args.max_tool_rounds)
            turn_record.update(result)
            render_turn(result)
            history.append({"role": "user", "content": user_text})
            history.append({"role": "assistant", "content": result["assistant_text"]})
        except Exception as exc:
            turn_record.update({"status": "provider_error",
                                "error": f"{type(exc).__name__}: {exc}"})
            console.print(Panel(turn_record["error"], title="[red]ERROR[/]", border_style="red"))

        turn_record["ended_at"] = now_iso()
        transcript["turns"].append(turn_record)
        write_transcript(transcript_path, transcript)
        console.print(f"[dim]Transcript saved: {transcript_path}[/dim]")

    write_transcript(transcript_path, transcript)
    console.print(f"[bold]Final transcript: {transcript_path}[/bold]")


if __name__ == "__main__":
    main()
