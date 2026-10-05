"""
Core text compression logic and token calculation module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

try:
    import tiktoken

    _TIKTOKEN_AVAILABLE = True
except ImportError:  # pragma: no cover
    tiktoken = None
    _TIKTOKEN_AVAILABLE = False


class CompressionLevel(str, Enum):
    """Compression aggressiveness levels."""

    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


@dataclass(frozen=True)
class CompressionResult:
    """Compression result containing cleaned text and token reduction metrics."""

    original_text: str
    compressed_text: str
    original_tokens: int
    compressed_tokens: int
    tokens_saved: int
    savings_ratio: float
    original_chars: int
    compressed_chars: int
    model_or_encoding: str

    def to_dict(self) -> dict:
        """Convert compression result to dictionary representation."""
        return {
            "original_text": self.original_text,
            "compressed_text": self.compressed_text,
            "original_tokens": self.original_tokens,
            "compressed_tokens": self.compressed_tokens,
            "tokens_saved": self.tokens_saved,
            "savings_ratio": round(self.savings_ratio, 2),
            "original_chars": self.original_chars,
            "compressed_chars": self.compressed_chars,
            "model_or_encoding": self.model_or_encoding,
        }


class PromptCompressor:
    """Intelligent prompt compressor to minimize LLM API token consumption."""

    # English politeness and conversational fillers
    EN_POLITE_FILLERS = [
        r"(?i)\b(?:please\s+)?could\s+you\s+(?:possibly\s+|kindly\s+)?(?:please\s+)?",
        r"(?i)\b(?:please\s+)?can\s+you\s+(?:kindly\s+)?(?:please\s+)?",
        r"(?i)\b(?:please\s+)?would\s+you\s+(?:kindly\s+|mind\s+)?(?:please\s+)?",
        r"(?i)\bi\s+would\s+like\s+you\s+to\b",
        r"(?i)\bi\s+want\s+you\s+to\b",
        r"(?i)\bi\s+need\s+you\s+to\b",
        r"(?i)\bas\s+an\s+ai(?:\s+language\s+model)?,\s*",
        r"(?i)\bif\s+you\s+don'?t\s+mind,?\s*",
        r"(?i)\bthank\s+you\s+in\s+advance[.,!]?\s*",
        r"(?i)\bthanks\s+in\s+advance[.,!]?\s*",
        r"(?i)\bany\s+help\s+(?:would\s+be|is)\s+(?:greatly\s+)?appreciated[.,!]?\s*",
        r"(?i)\bi\s+hope\s+you\s+are\s+doing\s+well[.,!]?\s*",
        r"(?i)\bhello[.,!]?\s+can\s+you\b",
    ]

    # Indonesian politeness and conversational fillers
    ID_POLITE_FILLERS = [
        r"(?i)\btolong\s+(?:bantu\s+)?(?:saya\s+)?(?:untuk\s+)?",
        r"(?i)\bbisakah\s+anda\s+(?:tolong\s+)?(?:membantu\s+saya\s+untuk\s+)?",
        r"(?i)\bmohon\s+(?:bantuan(?:nya)?\s+)?(?:untuk\s+)?",
        r"(?i)\bsaya\s+ingin\s+meminta\s+anda\s+untuk\s+",
        r"(?i)\bterima\s+kasih\s+sebelumnya[.,!]?\s*",
        r"(?i)\bsemoga\s+hari\s+anda\s+menyenangkan[.,!]?\s*",
        r"(?i)\bsebagai\s+(?:seorang\s+)?(?:asisten\s+)?ai,\s*",
        r"(?i)\bjangan\s+ragu\s+untuk\s+",
    ]

    # Verbose phrase compaction (Aggressive mode)
    VERBOSE_PHRASES = [
        (r"(?i)\bin\s+order\s+to\b", "to"),
        (r"(?i)\bdue\s+to\s+the\s+fact\s+that\b", "because"),
        (r"(?i)\bat\s+this\s+point\s+in\s+time\b", "now"),
        (r"(?i)\bmake\s+sure\s+(?:that\s+)?(?:you\s+)?", "ensure "),
        (r"(?i)\bkeep\s+in\s+mind\s+(?:that\s+)?", "note: "),
        (r"(?i)\btake\s+into\s+consideration\b", "consider"),
        (r"(?i)\bfor\s+the\s+purpose\s+of\b", "for"),
        (r"(?i)\bin\s+the\s+event\s+that\b", "if"),
        (r"(?i)\bwith\s+regard\s+to\b", "regarding"),
        (r"(?i)\bpada\s+saat\s+ini\b", "saat ini"),
        (r"(?i)\bdengan\s+tujuan\s+untuk\b", "untuk"),
        (r"(?i)\bdikarenakan\s+oleh\s+karena\b", "karena"),
        (r"(?i)\bharap\s+diperhatikan\s+bahwa\b", "catatan:"),
    ]

    def __init__(self, default_encoding: str = "cl100k_base"):
        """Initialize PromptCompressor with the designated tiktoken encoding."""
        self.default_encoding = default_encoding
        self._tokenizer = self._load_tokenizer(default_encoding)

    def _load_tokenizer(self, encoding_or_model: str):
        """Load tiktoken tokenizer or safely return None if unavailable."""
        if not _TIKTOKEN_AVAILABLE:
            return None

        try:
            return tiktoken.get_encoding(encoding_or_model)
        except Exception:
            try:
                return tiktoken.encoding_for_model(encoding_or_model)
            except Exception:
                # Fallback to standard base encoding
                try:
                    return tiktoken.get_encoding("cl100k_base")
                except Exception:
                    return None

    def count_tokens(self, text: str, encoding_or_model: Optional[str] = None) -> int:
        """Count tokens in text using tiktoken with graceful heuristic fallback."""
        if not text:
            return 0

        tokenizer = self._tokenizer
        if encoding_or_model and encoding_or_model != self.default_encoding:
            tokenizer = self._load_tokenizer(encoding_or_model)

        if tokenizer is not None:
            try:
                return len(tokenizer.encode(text, disallowed_special=()))
            except Exception:
                pass

        # Heuristic fallback if tiktoken is offline/unavailable: ~4 chars per token
        return max(1, len(text) // 4)

    def compress(
        self,
        text: str,
        level: CompressionLevel = CompressionLevel.MODERATE,
        encoding_or_model: Optional[str] = None,
    ) -> CompressionResult:
        """Compress prompt text and compute token savings metrics.

        Args:
            text: Raw input prompt text to compress.
            level: Aggressiveness level (conservative, moderate, aggressive).
            encoding_or_model: Tiktoken model or encoding name.

        Returns:
            CompressionResult with cleaned text and comparative metrics.
        """
        if not text or not text.strip():
            return CompressionResult(
                original_text=text or "",
                compressed_text="",
                original_tokens=0,
                compressed_tokens=0,
                tokens_saved=0,
                savings_ratio=0.0,
                original_chars=len(text or ""),
                compressed_chars=0,
                model_or_encoding=encoding_or_model or self.default_encoding,
            )

        target_model = encoding_or_model or self.default_encoding
        original_tokens = self.count_tokens(text, target_model)
        original_chars = len(text)

        # 1. Pipeline Execution
        compressed = text

        # Stage A: Whitespace & blank line normalization
        compressed = self._normalize_whitespace(compressed)

        # Stage B: Deduplicate identical consecutive lines
        compressed = self._deduplicate_lines(compressed)

        # Stage C: Remove repetitive redundant punctuation
        compressed = self._clean_redundant_punctuation(compressed)

        # Stage D: Filter conversational fillers for MODERATE or AGGRESSIVE levels
        if level in (CompressionLevel.MODERATE, CompressionLevel.AGGRESSIVE):
            compressed = self._remove_polite_fillers(compressed)

        # Stage E: Compact verbose phrasing in AGGRESSIVE level
        if level == CompressionLevel.AGGRESSIVE:
            compressed = self._compact_verbose_phrases(compressed)

        # Stage F: Final cleanup
        compressed = self._final_cleanup(compressed)

        compressed_tokens = self.count_tokens(compressed, target_model)
        compressed_chars = len(compressed)
        tokens_saved = max(0, original_tokens - compressed_tokens)

        savings_ratio = (
            (tokens_saved / original_tokens * 100.0) if original_tokens > 0 else 0.0
        )

        return CompressionResult(
            original_text=text,
            compressed_text=compressed,
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            tokens_saved=tokens_saved,
            savings_ratio=savings_ratio,
            original_chars=original_chars,
            compressed_chars=compressed_chars,
            model_or_encoding=target_model,
        )

    def _normalize_whitespace(self, text: str) -> str:
        """Strip trailing spaces per line and compress excessive blank lines."""
        lines = [re.sub(r"[ \t]+$", "", line) for line in text.splitlines()]
        result = "\n".join(lines)

        # Collapse 3 or more consecutive newlines to maximum 2
        result = re.sub(r"\n{3,}", "\n\n", result)

        # Collapse multiple horizontal whitespace while preserving indentation
        clean_lines = []
        for line in result.splitlines():
            indent_match = re.match(r"^(\s*)", line)
            indent = indent_match.group(1) if indent_match else ""
            rest = line[len(indent) :]
            rest = re.sub(r"[ \t]{2,}", " ", rest)
            clean_lines.append(indent + rest)

        return "\n".join(clean_lines)

    def _deduplicate_lines(self, text: str) -> str:
        """Remove consecutive identical lines while preserving structure."""
        lines = text.splitlines()
        if not lines:
            return ""

        deduped = []
        prev_line = None

        for line in lines:
            stripped = line.strip()
            if not stripped:
                if prev_line != "":
                    deduped.append("")
                    prev_line = ""
                continue

            if stripped != prev_line:
                deduped.append(line)
                prev_line = stripped

        return "\n".join(deduped)

    def _clean_redundant_punctuation(self, text: str) -> str:
        """Normalize repetitive punctuation marks (e.g. ???? -> ?)."""
        text = re.sub(r"\?{2,}", "?", text)
        text = re.sub(r"!{2,}", "!", text)
        text = re.sub(r"\.{4,}", "...", text)
        return text

    def _remove_polite_fillers(self, text: str) -> str:
        """Remove filler polite preambles and boilerplate conversational fluff."""
        result = text
        fillers = self.EN_POLITE_FILLERS + self.ID_POLITE_FILLERS

        for pattern in fillers:
            result = re.sub(pattern, "", result)

        # Fix capitalization of the first word on each line if stripped
        lines = result.splitlines()
        fixed_lines = []
        for line in lines:
            stripped = line.lstrip()
            indent = line[: len(line) - len(stripped)]
            if stripped:
                fixed = stripped[0].upper() + stripped[1:] if len(stripped) > 1 else stripped.upper()
                fixed_lines.append(indent + fixed)
            else:
                fixed_lines.append("")

        return "\n".join(fixed_lines)

    def _compact_verbose_phrases(self, text: str) -> str:
        """Replace verbose phrases with concise, token-efficient alternatives."""
        result = text
        for pattern, replacement in self.VERBOSE_PHRASES:
            result = re.sub(pattern, replacement, result)
        return result

    def _final_cleanup(self, text: str) -> str:
        """Final cleanup of spaces around punctuation and trailing blanks."""
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\s+([,.:;!?])", r"\1", text)
        lines = [line.strip() for line in text.splitlines()]
        cleaned = "\n".join(lines)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()


def compress_prompt(
    text: str,
    level: CompressionLevel = CompressionLevel.MODERATE,
    encoding_or_model: str = "cl100k_base",
) -> CompressionResult:
    """Convenience helper to compress prompt text in a single call."""
    compressor = PromptCompressor(default_encoding=encoding_or_model)
    return compressor.compress(text=text, level=level, encoding_or_model=encoding_or_model)
