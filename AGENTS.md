# AGENTS.md

Last updated: 2026-03-02

## Verified local workflows

### 1) Start the app locally
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
# set OPENAI_API_KEY in your environment or .env loader
uvicorn app:app --reload --port 8000
```

Then open `http://localhost:8000`.

### 2) Run tests
```bash
source .venv/bin/activate
pytest -q
```

Reference baseline from repo docs: `7 passed`.

## TODO
- Add a concrete deployment command workflow when this repo documents a canonical HF/GitHub deploy command sequence.
