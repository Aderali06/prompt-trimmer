"""
Quick launcher script for prompt-trimmer.
Execute directly with: python run.py
"""

import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from prompt_trimmer.main import app

if __name__ == "__main__":
    if len(sys.argv) == 1:
        # If executed with no arguments (e.g. IDE Run button),
        # automatically start the local FastAPI Playground server!
        print("[*] Starting local Prompt Trimmer Playground server...")
        print("[*] Open your browser at: http://127.0.0.1:8000")
        print("[*] Interactive Swagger API Docs: http://127.0.0.1:8000/docs")
        print("[*] Press Ctrl+C to stop.\n")
        from prompt_trimmer.main import serve_command

        serve_command(host="127.0.0.1", port=8000, reload=False)
    else:
        app()
