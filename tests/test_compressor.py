"""
Comprehensive unit test suite for prompt compressor and CLI interface.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from prompt_trimmer.compressor import (
    CompressionLevel,
    PromptCompressor,
    compress_prompt,
)
from prompt_trimmer.main import app

runner = CliRunner()


@pytest.fixture
def compressor() -> PromptCompressor:
    return PromptCompressor(default_encoding="cl100k_base")


def test_empty_and_whitespace_input(compressor: PromptCompressor):
    """Ensure empty or whitespace-only inputs are handled gracefully."""
    res_empty = compressor.compress("")
    assert res_empty.compressed_text == ""
    assert res_empty.original_tokens == 0
    assert res_empty.compressed_tokens == 0
    assert res_empty.savings_ratio == 0.0

    res_spaces = compressor.compress("     \n\n\t   ")
    assert res_spaces.compressed_text == ""
    assert res_spaces.tokens_saved == 0


def test_normalize_whitespace(compressor: PromptCompressor):
    """Test whitespace collapse and excessive newline limitation."""
    dirty_text = "Line 1    with   excessive    spaces.   \n\n\n\n\nLine 2."
    result = compressor.compress(dirty_text, level=CompressionLevel.CONSERVATIVE)
    assert "    " not in result.compressed_text
    assert "\n\n\n" not in result.compressed_text
    assert "Line 1 with excessive spaces." in result.compressed_text
    assert "Line 2." in result.compressed_text


def test_deduplicate_identical_consecutive_lines(compressor: PromptCompressor):
    """Test deduplication of identical consecutive lines."""
    repetitive_text = (
        "Step 1: Prepare data\n"
        "Step 1: Prepare data\n"
        "Step 2: Clean input\n"
        "Step 2: Clean input\n"
        "Step 3: Save results"
    )
    result = compressor.compress(repetitive_text, level=CompressionLevel.CONSERVATIVE)
    expected = (
        "Step 1: Prepare data\n"
        "Step 2: Clean input\n"
        "Step 3: Save results"
    )
    assert result.compressed_text == expected


def test_redundant_punctuation(compressor: PromptCompressor):
    """Test reduction of repetitive punctuation marks."""
    text = "Is this right???? Answer now!!!! Do not delay....."
    result = compressor.compress(text, level=CompressionLevel.CONSERVATIVE)
    assert "????" not in result.compressed_text
    assert "!!!!" not in result.compressed_text
    assert "....." not in result.compressed_text
    assert "Is this right?" in result.compressed_text
    assert "Answer now!" in result.compressed_text


def test_remove_polite_fillers_english(compressor: PromptCompressor):
    """Test removal of English politeness fillers."""
    text = (
        "Hello! Could you kindly please summarize the following text for me? "
        "Thank you in advance!"
    )
    result = compressor.compress(text, level=CompressionLevel.MODERATE)
    assert "could you kindly please" not in result.compressed_text.lower()
    assert "thank you in advance" not in result.compressed_text.lower()
    assert "summarize the following text" in result.compressed_text.lower()
    assert result.tokens_saved > 0


def test_remove_polite_fillers_indonesian(compressor: PromptCompressor):
    """Test removal of Indonesian politeness fillers."""
    text = (
        "Tolong bantu saya untuk membuatkan fungsi pengurutan dalam Python. "
        "Terima kasih sebelumnya!"
    )
    result = compressor.compress(text, level=CompressionLevel.MODERATE)
    assert "tolong bantu saya untuk" not in result.compressed_text.lower()
    assert "terima kasih sebelumnya" not in result.compressed_text.lower()
    assert "membuatkan fungsi pengurutan" in result.compressed_text.lower()
    assert result.tokens_saved > 0


def test_aggressive_compression_replaces_phrases(compressor: PromptCompressor):
    """Test verbose phrase compaction under aggressive mode."""
    text = "In order to complete this task, due to the fact that time is short, do it now."
    res_mod = compressor.compress(text, level=CompressionLevel.MODERATE)
    res_agg = compressor.compress(text, level=CompressionLevel.AGGRESSIVE)

    assert "In order to" in res_mod.compressed_text or "in order to" in res_mod.compressed_text.lower()
    assert "To complete this task" in res_agg.compressed_text or "to complete this task" in res_agg.compressed_text.lower()
    assert "because" in res_agg.compressed_text.lower()
    assert res_agg.compressed_tokens <= res_mod.compressed_tokens


def test_token_savings_metrics(compressor: PromptCompressor):
    """Verify accuracy of token reduction metrics."""
    text = (
        "Please could you kindly provide a list of all fruits? "
        "I would like you to make sure that they are tropical fruits. "
        "Thank you in advance for your assistance!"
    )
    res = compressor.compress(text, level=CompressionLevel.MODERATE)

    assert res.original_tokens > res.compressed_tokens
    assert res.tokens_saved == res.original_tokens - res.compressed_tokens
    assert res.savings_ratio > 0.0
    assert 0.0 <= res.savings_ratio <= 100.0

    dict_data = res.to_dict()
    assert "tokens_saved" in dict_data
    assert "savings_ratio" in dict_data
    assert dict_data["tokens_saved"] == res.tokens_saved


def test_compress_prompt_helper():
    """Test the standalone compress_prompt helper function."""
    res = compress_prompt("Could you please explain Python decorators? Thanks in advance!")
    assert "explain python decorators" in res.compressed_text.lower()
    assert res.tokens_saved > 0


# --- CLI TYPER TESTS ---


def test_cli_version():
    """Test CLI version command."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "prompt-trimmer version" in result.stdout.lower()


def test_cli_trim_with_argument():
    """Test CLI trim command with direct positional argument."""
    prompt = "Could you kindly summarize this document? Thank you in advance!"
    result = runner.invoke(app, ["trim", prompt])
    assert result.exit_code == 0
    assert "Prompt Token Compression Metrics" in result.stdout
    assert "Compressed Prompt Text" in result.stdout


def test_cli_trim_json_output():
    """Test CLI trim command with --json option."""
    prompt = "Please could you kindly format this JSON? Thanks in advance!"
    result = runner.invoke(app, ["trim", prompt, "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "original_tokens" in payload
    assert "compressed_tokens" in payload
    assert "tokens_saved" in payload
    assert payload["tokens_saved"] > 0


def test_cli_trim_quiet_mode():
    """Test CLI trim command with -q / --quiet option."""
    prompt = "Please could you kindly calculate 2 + 2?"
    result = runner.invoke(app, ["trim", prompt, "-q"])
    assert result.exit_code == 0
    assert "Prompt Token Compression Metrics" not in result.stdout
    assert "calculate 2 + 2" in result.stdout.strip().lower()


def test_cli_trim_file_input(tmp_path: Path):
    """Test CLI trim with --file and --output options."""
    input_file = tmp_path / "prompt_input.txt"
    output_file = tmp_path / "prompt_output.txt"

    input_file.write_text(
        "Could you kindly help me write a poem?\n\n\n\nThank you in advance!",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["trim", "-f", str(input_file), "-o", str(output_file), "-l", "moderate"],
    )
    assert result.exit_code == 0
    assert output_file.exists()
    compressed_content = output_file.read_text(encoding="utf-8")
    assert "help me write a poem" in compressed_content.lower()


def test_cli_empty_input():
    """Test handling when no input text is provided."""
    result = runner.invoke(app, ["trim"])
    assert result.exit_code == 1
    assert "Error" in result.stderr or "Error" in result.stdout


# --- FASTAPI SERVER TESTS ---


def test_fastapi_endpoints():
    """Test local FastAPI REST API endpoints using TestClient."""
    from fastapi.testclient import TestClient
    from prompt_trimmer.main import create_api_app

    client = TestClient(create_api_app())

    # Health check
    res_health = client.get("/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "ok"

    # Playground UI
    res_ui = client.get("/")
    assert res_ui.status_code == 200
    assert "Prompt Trimmer Playground" in res_ui.text

    # Trim endpoint
    payload = {
        "text": "Hello! Could you kindly please summarize this? Thank you in advance!",
        "level": "moderate",
        "model": "cl100k_base",
    }
    res_trim = client.post("/v1/trim", json=payload)
    assert res_trim.status_code == 200
    data = res_trim.json()
    assert "compressed_text" in data
    assert "tokens_saved" in data
    assert data["tokens_saved"] > 0
    assert "summarize this" in data["compressed_text"].lower()
