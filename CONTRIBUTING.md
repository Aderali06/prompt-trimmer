# Contributing to prompt-trimmer

Thank you for your interest in contributing to **prompt-trimmer**! We welcome contributions of all kinds: bug fixes, documentation enhancements, feature proposals, and performance optimizations.

---

## 🛠️ Development Setup

1. **Fork and Clone the Repository**
   ```bash
   git clone https://github.com/Aderali06/prompt-trimmer.git
   cd prompt-trimmer
   ```

2. **Create a Virtual Environment**
   ```bash
   python -m venv .venv
   # On Windows:
   .venv\Scripts\activate
   # On macOS / Linux:
   source .venv/bin/activate
   ```

3. **Install Dependencies in Editable Mode**
   ```bash
   pip install --upgrade pip
   pip install -e ".[dev]"
   ```

---

## 🧪 Running Tests & Quality Checks

Before submitting any code changes, ensure all tests pass:

```bash
# Run pytest with code coverage
pytest --cov=prompt_trimmer --cov-report=term-missing
```

---

## 🚀 Development Workflow

1. Create a descriptive feature branch:
   ```bash
   git checkout -b feat/your-feature-name
   # or
   git checkout -b fix/your-bugfix-name
   ```
2. Implement your changes with clear, well-tested code.
3. Add corresponding unit tests in `tests/test_compressor.py`.
4. Commit your changes with meaningful commit messages:
   ```bash
   git commit -m "feat: add support for custom regex filler rules"
   ```
5. Push to your fork and submit a **Pull Request**.

---

## 📜 Code of Conduct

Please note that this project is governed by the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.
