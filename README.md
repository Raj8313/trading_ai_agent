# 🤖 Personal AI Trading Agent

A modular, personal trading agent built for ₹0 running locally on Indian equity markets (NSE).
Phase 1 focuses on the Foundation & Signal Engine — providing an auditable, deterministic Confidence Meter that scores historical data and logs every signal to SQLite.

## 🚀 Quickstart

### Prerequisites
- Python >= 3.11
- `uv` package manager

### Installation
```bash
uv sync --extra dev
```

### Running Tests
Run unit tests (all use synthetic data, no network required):
```bash
uv run pytest --cov=src/trading_agent/strategy --cov-report=term-missing
```

### CLI Usage
- **Backfill Historical Data**:
  ```bash
  uv run backfill
  ```
- **Inspect Score for a Symbol on a Date**:
  ```bash
  uv run score RELIANCE.NS 2024-01-15
  ```
