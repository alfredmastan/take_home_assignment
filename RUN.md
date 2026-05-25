# Running the Extraction Pipeline

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

## 1. Install dependencies

```bash
uv sync
```

uv resolves dependencies into `.venv/`. Prefix Python commands with `uv run`,
or `source .venv/bin/activate` once for your session.

## 2. Verify Database

```bash
uv run python verify.py
```

You should see `postgres is ready`.

## 3. Set environment variables

Copy the example file and add your Anthropic API key:

```bash
cp .env.example .env
```

Open `.env` and set:

```
ANTHROPIC_API_KEY=your_key_here
```

## 4. Run the full pipeline

```bash
uv run python run_pipeline.py
```

This runs Stage 1 (PDF → `data/items_raw.json`) then Stage 2 (`items_raw.json` → Postgres) in sequence.

---

## Run stages individually

```bash
uv run python reznar/parser.py   # Stage 1: PDF → data/items_raw.json
uv run python reznar/extract.py  # Stage 2: items_raw.json → Postgres
```

## Reset the database

```bash
rm -rf data/.pg/
```
