"""
Typer CLI interface and lightweight local FastAPI server for prompt-trimmer.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

# Ensure UTF-8 output encoding across Windows PowerShell / CMD terminals
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import typer
from rich.box import ROUNDED
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from prompt_trimmer import __version__
from prompt_trimmer.compressor import (
    CompressionLevel,
    CompressionResult,
    PromptCompressor,
)

app = typer.Typer(
    name="prompt-trimmer",
    help="Compress prompt texts and automatically save LLM API token costs.",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()
err_console = Console(stderr=True)


def _render_metrics_table(result: CompressionResult) -> None:
    """Render token savings summary table to the terminal."""
    table = Table(
        title="[bold cyan]Prompt Token Compression Metrics[/bold cyan]",
        box=ROUNDED,
        show_header=True,
        header_style="bold magenta",
    )

    table.add_column("Parameter", style="dim", width=24)
    table.add_column("Before", justify="right", style="red")
    table.add_column("After", justify="right", style="green")
    table.add_column("Savings", justify="right", style="bold yellow")

    table.add_row(
        "Token Count (Tiktoken)",
        str(result.original_tokens),
        str(result.compressed_tokens),
        f"-{result.tokens_saved} tokens ({result.savings_ratio:.1f}%)",
    )
    chars_saved = max(0, result.original_chars - result.compressed_chars)
    table.add_row(
        "Character Count",
        str(result.original_chars),
        str(result.compressed_chars),
        f"-{chars_saved} chars",
    )
    table.add_row(
        "Model / Encoding",
        result.model_or_encoding,
        result.model_or_encoding,
        "Optimized",
    )

    console.print(table)


@app.command("trim", help="Compress prompt text from an argument, file, or stdin pipe.")
def trim_command(
    text: Optional[str] = typer.Argument(
        None,
        help="Prompt text to compress. If omitted, input is read from --file or stdin.",
    ),
    file: Optional[Path] = typer.Option(
        None,
        "-f",
        "--file",
        help="Path to a text file containing the prompt.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    level: CompressionLevel = typer.Option(
        CompressionLevel.MODERATE,
        "-l",
        "--level",
        help="Compression aggressiveness: conservative, moderate, or aggressive.",
    ),
    model: str = typer.Option(
        "cl100k_base",
        "-m",
        "--model",
        help="Model name (e.g. gpt-4o, gpt-4) or tiktoken encoding (e.g. cl100k_base, o200k_base).",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "-o",
        "--output",
        help="Save compressed prompt text to a file.",
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Output raw JSON with metrics and compressed text.",
    ),
    quiet: bool = typer.Option(
        False,
        "-q",
        "--quiet",
        help="Output only the compressed text without metrics table (ideal for pipes).",
    ),
) -> None:
    """Main prompt trimming command."""
    input_text = ""

    if text:
        input_text = text
    elif file is not None:
        input_text = file.read_text(encoding="utf-8")
    elif not sys.stdin.isatty():
        input_text = sys.stdin.read()
    else:
        err_console.print(
            "[bold red]Error:[/bold red] Please provide prompt text, use [cyan]-f/--file[/cyan], or pipe via [cyan]stdin[/cyan]."
        )
        raise typer.Exit(code=1)

    if not input_text.strip():
        err_console.print("[bold red]Error:[/bold red] Input prompt text is empty.")
        raise typer.Exit(code=1)

    compressor = PromptCompressor(default_encoding=model)
    result = compressor.compress(text=input_text, level=level, encoding_or_model=model)

    if output is not None:
        output.write_text(result.compressed_text, encoding="utf-8")

    if as_json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        return

    if quiet:
        sys.stdout.write(result.compressed_text + "\n")
        return

    console.print(
        Panel(
            result.compressed_text,
            title="[bold green]Compressed Prompt Text[/bold green]",
            border_style="green",
        )
    )
    _render_metrics_table(result)

    if output:
        console.print(f"[dim]Compressed output saved to:[/dim] [cyan]{output}[/cyan]")


@app.command("version", help="Show prompt-trimmer version.")
def version_command() -> None:
    """Print project version."""
    console.print(f"[bold cyan]prompt-trimmer[/bold cyan] version [bold green]{__version__}[/bold green]")


try:
    from fastapi import Body, FastAPI
    from fastapi.responses import HTMLResponse
    from pydantic import BaseModel, Field

    class TrimRequest(BaseModel):
        text: str = Field(..., description="Prompt text to compress.")
        level: CompressionLevel = Field(
            default=CompressionLevel.MODERATE, description="Compression level."
        )
        model: str = Field(
            default="cl100k_base",
            description="LLM model or tiktoken encoding (e.g. gpt-4o, cl100k_base).",
        )

    class TrimResponse(BaseModel):
        original_text: str
        compressed_text: str
        original_tokens: int
        compressed_tokens: int
        tokens_saved: int
        savings_ratio: float
        original_chars: int
        compressed_chars: int
        model_or_encoding: str

except ImportError:  # pragma: no cover
    TrimRequest = None  # type: ignore
    TrimResponse = None  # type: ignore


def create_api_app():
    """Create FastAPI application instance for local compression API and playground."""
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse

    api_app = FastAPI(
        title="Prompt Trimmer API",
        version=__version__,
        description="High-performance local REST API for prompt text compression and token calculations.",
    )

    @api_app.post("/v1/trim", response_model=TrimResponse)
    def trim_api(req: TrimRequest):
        compressor = PromptCompressor(default_encoding=req.model)
        res = compressor.compress(text=req.text, level=req.level, encoding_or_model=req.model)
        return TrimResponse(**res.to_dict())

    @api_app.get("/health")
    def health_check():
        return {"status": "ok", "version": __version__}

    @api_app.get("/", response_class=HTMLResponse)
    def interactive_playground():
        return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Prompt Trimmer Playground</title>
  <style>
    :root {
      --bg: #0f172a;
      --card: #1e293b;
      --border: #334155;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --primary: #38bdf8;
      --accent: #22c55e;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
    body { background: var(--bg); color: var(--text); padding: 2rem 1rem; min-height: 100vh; }
    .container { max-width: 960px; margin: 0 auto; }
    header { text-align: center; margin-bottom: 2rem; }
    h1 { font-size: 2rem; color: var(--primary); margin-bottom: 0.5rem; }
    p.desc { color: var(--text-muted); font-size: 0.95rem; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }
    @media (max-width: 768px) { .grid { grid-template-columns: 1fr; } }
    .box { background: var(--card); border: 1px solid var(--border); border-radius: 0.75rem; padding: 1.25rem; display: flex; flex-direction: column; gap: 0.75rem; }
    label { font-weight: 600; font-size: 0.9rem; color: var(--primary); }
    textarea { width: 100%; height: 260px; background: #0b1120; border: 1px solid var(--border); border-radius: 0.5rem; color: #fff; padding: 0.75rem; font-size: 0.9rem; resize: none; outline: none; }
    textarea:focus { border-color: var(--primary); }
    .controls { display: flex; gap: 1rem; align-items: center; margin-top: 1rem; flex-wrap: wrap; }
    select, button { padding: 0.6rem 1.2rem; border-radius: 0.5rem; font-weight: 600; font-size: 0.9rem; cursor: pointer; border: none; }
    select { background: #0b1120; border: 1px solid var(--border); color: #fff; }
    button { background: var(--primary); color: #0f172a; transition: opacity 0.2s; }
    button:hover { opacity: 0.9; }
    .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-top: 1.5rem; }
    @media (max-width: 640px) { .stats { grid-template-columns: repeat(2, 1fr); } }
    .stat-card { background: var(--card); border: 1px solid var(--border); border-radius: 0.5rem; padding: 1rem; text-align: center; }
    .stat-val { font-size: 1.5rem; font-weight: bold; color: var(--accent); }
    .stat-label { font-size: 0.8rem; color: var(--text-muted); margin-top: 0.25rem; }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>✂️ Prompt Trimmer Playground</h1>
      <p class="desc">Intelligently compress prompts, remove fluff & dramatically cut LLM API token spend.</p>
    </header>

    <div class="controls">
      <div>
        <label for="level">Compression Level: </label>
        <select id="level">
          <option value="conservative">Conservative (Whitespace & Format Only)</option>
          <option value="moderate" selected>Moderate (Strip Fillers & Fluff)</option>
          <option value="aggressive">Aggressive (Compact Phrases)</option>
        </select>
      </div>
      <div>
        <label for="model">Model: </label>
        <select id="model">
          <option value="cl100k_base" selected>cl100k_base (GPT-4 / GPT-3.5)</option>
          <option value="o200k_base">o200k_base (GPT-4o)</option>
        </select>
      </div>
      <button id="trimBtn" onclick="runTrim()">⚡ Compress Prompt</button>
    </div>

    <div class="grid" style="margin-top: 1.5rem;">
      <div class="box">
        <label for="input">Original Prompt</label>
        <textarea id="input" placeholder="Type or paste your prompt here...">Hello! As an AI language model, could you kindly please assist me in order to summarize this article? Thank you in advance!</textarea>
      </div>
      <div class="box">
        <label for="output">Compressed Result</label>
        <textarea id="output" readonly placeholder="Compressed output will appear here..."></textarea>
      </div>
    </div>

    <div class="stats">
      <div class="stat-card">
        <div class="stat-val" id="origTokens">-</div>
        <div class="stat-label">Original Tokens</div>
      </div>
      <div class="stat-card">
        <div class="stat-val" id="compTokens">-</div>
        <div class="stat-label">Final Tokens</div>
      </div>
      <div class="stat-card">
        <div class="stat-val" id="savedTokens" style="color:#f59e0b;">-</div>
        <div class="stat-label">Tokens Saved</div>
      </div>
      <div class="stat-card">
        <div class="stat-val" id="savingRatio" style="color:var(--accent);">-</div>
        <div class="stat-label">Saved Ratio</div>
      </div>
    </div>
  </div>

  <script>
    async function runTrim() {
      const text = document.getElementById('input').value;
      const level = document.getElementById('level').value;
      const model = document.getElementById('model').value;
      const btn = document.getElementById('trimBtn');
      btn.innerText = 'Processing...';
      try {
        const res = await fetch('/v1/trim', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({text, level, model})
        });
        const data = await res.json();
        document.getElementById('output').value = data.compressed_text;
        document.getElementById('origTokens').innerText = data.original_tokens;
        document.getElementById('compTokens').innerText = data.compressed_tokens;
        document.getElementById('savedTokens').innerText = data.tokens_saved;
        document.getElementById('savingRatio').innerText = data.savings_ratio + '%';
      } catch (e) {
        alert('Failed to connect to Prompt Trimmer API server');
      } finally {
        btn.innerText = '⚡ Compress Prompt';
      }
    }
  </script>
</body>
</html>"""

    return api_app


@app.command("serve", help="Run local lightweight FastAPI server with interactive web playground.")
def serve_command(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Server host binding."),
    port: int = typer.Option(8000, "--port", "-p", help="Server HTTP port."),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload for development."),
) -> None:
    """Run local FastAPI server."""
    try:
        import uvicorn
    except ImportError:  # pragma: no cover
        err_console.print(
            "[bold red]Error:[/bold red] Package [cyan]uvicorn[/cyan] is required to run the server."
        )
        err_console.print("Please run: [green]pip install uvicorn[/green]")
        raise typer.Exit(code=1)

    api_app = create_api_app()
    console.print(f"[bold green]Starting Prompt Trimmer server at http://{host}:{port}[/bold green]")
    console.print(f"[dim]Swagger API Docs:[/dim] [cyan]http://{host}:{port}/docs[/cyan]")
    console.print(f"[dim]Interactive Web Playground:[/dim] [cyan]http://{host}:{port}/[/cyan]")
    uvicorn.run(api_app, host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
