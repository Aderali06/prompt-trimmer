"""prompt-trimmer: Compress prompt texts and save LLM API token costs automatically."""

from prompt_trimmer.compressor import (
    CompressionLevel,
    CompressionResult,
    PromptCompressor,
    compress_prompt,
)

__version__ = "0.1.0"
__author__ = "Prompt Trimmer Contributors"
__license__ = "MIT"
__all__ = [
    "__version__",
    "PromptCompressor",
    "CompressionResult",
    "CompressionLevel",
    "compress_prompt",
]

if __name__ == "__main__":
    from prompt_trimmer.main import app

    app()
