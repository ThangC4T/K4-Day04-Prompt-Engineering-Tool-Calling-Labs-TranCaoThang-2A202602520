from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax
from rich.table import Table

from chat import (
    run_model_tool_loop,
    trim_history,
    write_transcript,
    now_iso,
    safe_slug,
)
from env_loader import load_lab_env
from providers import make_provider
from tools import load_tool_declarations, to_openai_tools
from versioning import artifact_version_dict, build_artifact_version

ROOT = Path(__file__).parent
ARTIFACTS_DIR = ROOT / "artifacts"
load_lab_env(ROOT)

app = typer.Typer(add_completion=False, help="IT Helpdesk Agent — modern Rich+Typer CLI.")
console = Console()


def _args_json(args: dict) -> str:
    try:
        return json.dumps(args, ensure_ascii=False, sort_keys=True)
    except Exception:
        return str(args)


def _show_rounds_table(rounds: list[dict]) -> None:
    table = Table(title="Tool trace", box=box.ROUNDED, show_lines=True)
    table.add_column("Round", style="cyan", width=6)
    table.add_column("Tool call + args", style="magenta")
    table.add_column("Result / error", style="green")
    for rd in rounds:
        calls = rd.get("tool_calls", [])
        results = {r.get("tool"): r for r in rd.get("tool_results", [])}
        if not calls:
            table.add_row(str(rd.get("round")), "[dim]no tool call[/dim]", (rd.get("assistant_text") or "")[:300])
            continue
        for c in calls:
            name = c.get("name", "?")
            ev = results.get(name, {})
            res = ev.get("result", {})
            if isinstance(res, dict) and res.get("error"):
                res_str = f"[red]{res.get('error')}: {str(res.get('message'))[:300]}[/red]"
            else:
                res_str = json.dumps(res, ensure_ascii=False, default=str)[:600]
            table.add_row(str(rd.get("round")), f"[bold]{name}[/bold]\n{_args_json(c.get('args', {}))}", res_str)
    console.print(table)


def _show_header(artifact_version: str, provider: str, model: str | None) -> None:
    console.print(
        Panel.fit(
            f"[bold cyan]IT Helpdesk Agent[/bold cyan]\n"
            f"artifact: [yellow]{artifact_version}[/yellow] | provider: [green]{provider}[/green] | model: [green]{model}[/green]\n"
            f"[dim]Commands: /exit quit • /tools list tools • /version show hashes • /clear clear history[/dim]",
            title="Northstar Labs Service Desk",
            border_style="cyan",
        )
    )


@app.command()
def chat(
    provider: str = typer.Option("openai", help="openrouter|openai|anthropic|gemini"),
    model: Optional[str] = typer.Option(None, help="Model override, e.g. deepseek-flash"),
    version: str = typer.Option("v3", help="Artifact version label"),
    system_prompt: Path = typer.Option(ARTIFACTS_DIR / "system_prompt.md"),
    tools: Path = typer.Option(ARTIFACTS_DIR / "tools.yaml"),
    transcripts_dir: Path = typer.Option(ROOT / "transcripts"),
    history_window: int = typer.Option(5, help="Keep last N pairs"),
    max_tool_rounds: int = typer.Option(4),
) -> None:
    """Interactive chat reusing run_model_tool_loop from chat.py."""
    sys_prompt = Path(system_prompt).read_text(encoding="utf-8")
    decls = load_tool_declarations(Path(tools))
    openai_tools = to_openai_tools(decls)
    prov = make_provider(provider)
    selected_model = model or getattr(prov, "default_model", None)
    aver = build_artifact_version(version, Path(system_prompt), Path(tools))

    ts = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    tid = "_".join([safe_slug(version), safe_slug(provider), ts])
    tpath = Path(transcripts_dir) / f"{tid}.transcript.json"
    transcript: dict = {
        "transcript_id": tid,
        **artifact_version_dict(aver),
        "provider": provider,
        "model": selected_model,
        "system_prompt": str(system_prompt),
        "tools": str(tools),
        "history_window": history_window,
        "max_tool_rounds": max_tool_rounds,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "turns": [],
    }

    _show_header(aver.artifact_version, provider, selected_model)
    history: list[dict[str, str]] = []
    turn_index = 0

    while True:
        try:
            user_text = Prompt.ask("\n[bold cyan]You[/bold cyan]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break
        if not user_text:
            continue
        if user_text in {"/exit", "/quit"}:
            break
        if user_text == "/tools":
            t = Table(title="Declared tools", box=box.SIMPLE)
            t.add_column("Tool", style="magenta")
            for d in decls:
                t.add_row(d.get("name", "?"))
            console.print(t)
            continue
        if user_text == "/version":
            console.print(
                Panel(
                    f"version: {aver.version}\nartifact: {aver.artifact_version}\n"
                    f"prompt_hash: {aver.prompt_hash[:12]}\ntools_hash: {aver.tools_hash[:12]}",
                    title="Artifact version",
                )
            )
            continue
        if user_text == "/clear":
            history.clear()
            console.print("[dim]History cleared.[/dim]")
            continue

        turn_index += 1
        messages = [
            {"role": "system", "content": sys_prompt},
            *trim_history(history, history_window),
            {"role": "user", "content": user_text},
        ]
        turn_record: dict = {
            "turn_index": turn_index,
            "started_at": now_iso(),
            "user": user_text,
            "status": "started",
            "assistant_text": None,
            "rounds": [],
            "tool_events": [],
        }
        try:
            with console.status("[bold green]Agent thinking + calling tools...[/bold green]"):
                result = run_model_tool_loop(
                    provider=prov,
                    messages=messages,
                    tools=openai_tools,
                    model=model,
                    max_tool_rounds=max_tool_rounds,
                )
            turn_record.update(result)
            status = result.get("status", "?")
            color = "green" if status == "answered" else "yellow"
            console.print(
                Panel(
                    result.get("assistant_text") or "",
                    title=f"Agent • status={status} • turn={turn_index}",
                    border_style=color,
                )
            )
            _show_rounds_table(result.get("rounds", []))
            history.append({"role": "user", "content": user_text})
            history.append({"role": "assistant", "content": result.get("assistant_text") or ""})
        except Exception as exc:
            turn_record.update({"status": "provider_error", "error": f"{type(exc).__name__}: {exc}"})
            console.print(Panel(str(exc), title="Provider error", border_style="red"))

        turn_record["ended_at"] = now_iso()
        transcript["turns"].append(turn_record)
        write_transcript(tpath, transcript)
        console.print(f"[dim]Transcript: {tpath} • status={turn_record.get('status')}[/dim]")

    write_transcript(tpath, transcript)
    console.print(Panel(str(tpath), title="Final transcript", border_style="cyan"))


@app.command()
def ask(
    text: str = typer.Argument(..., help="Single user request"),
    provider: str = typer.Option("openai"),
    model: Optional[str] = typer.Option(None),
    version: str = typer.Option("v3"),
    system_prompt: Path = typer.Option(ARTIFACTS_DIR / "system_prompt.md"),
    tools: Path = typer.Option(ARTIFACTS_DIR / "tools.yaml"),
    max_tool_rounds: int = typer.Option(4),
    show_json: bool = typer.Option(False, help="Print raw JSON trace"),
) -> None:
    """Single-shot request (scriptable, same loop as chat)."""
    sys_prompt = Path(system_prompt).read_text(encoding="utf-8")
    decls = load_tool_declarations(Path(tools))
    openai_tools = to_openai_tools(decls)
    prov = make_provider(provider)
    selected_model = model or getattr(prov, "default_model", None)
    aver = build_artifact_version(version, Path(system_prompt), Path(tools))
    console.print(Panel(f"artifact={aver.artifact_version} provider={provider} model={selected_model}", border_style="cyan"))
    result = run_model_tool_loop(
        provider=prov,
        messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": text}],
        tools=openai_tools,
        model=model,
        max_tool_rounds=max_tool_rounds,
    )
    console.print(Panel(result.get("assistant_text") or "", title=f"Agent • {result.get('status')}", border_style="green"))
    _show_rounds_table(result.get("rounds", []))
    if show_json:
        console.print(Syntax(json.dumps(result, ensure_ascii=False, indent=2, default=str)[:8000], "json"))


if __name__ == "__main__":
    app()
