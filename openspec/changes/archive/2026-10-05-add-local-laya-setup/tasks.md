## 1. Adapter

- [x] 1.1 Make `model` optional in `SystemOneBackend`: omit it from the request body when it is `None`, give `laya()` no default model, keep `jev-latest` for Jev, and label an unset model `"auto"` in LLM logs. Verify with respx tests: no `model` key without `LAYA_MODEL`, `"model": "english"` when it is set, and the Jev body unchanged
- [x] 1.2 Add Jev-scale confidence recomputation for Laya (design D3) in `parse_answer`, enabled only for the laya backend, with fallbacks to `answer_confidence`/`confidence` when probabilities are missing. Verify with tests on Laya's documented sample: choice 0.9519/0.0327/0.0154 → 0.928; score max 0.4136 of 4 → 0.218 and marked uncertain in insights; Jev's `confidence` 0.81 passes through unchanged; `noul` is unaffected

## 2. Configuration

- [x] 2.1 Read `LAYA_API_KEY` in `Settings`, pass it to `SystemOneBackend.laya(api_key=...)`, add it to `secrets()`, and show the Laya model as `"auto"` in `backends()` when it is unset. Verify with config tests (`--brain laya` reports nothing missing; the key is read and listed in secrets) and a respx test (bearer header only when the key is set)
- [x] 2.2 Verify redaction: a logged Laya call made with `LAYA_API_KEY=local-secret` shows `"authorization": "[REDACTED]"` and does not contain `local-secret` anywhere in the file

## 3. Documentation

- [x] 3.1 Add the README section "Running Laya locally" (design D4): requirements, `uv tool install "laya[serve]"` plus the pip alternative, `LAYA_MODELS=english LAYA_PRELOAD=1 laya-serve`, the Docker Compose HTTP route, the `/health` check, `.env` settings with the CPU timeout tip, the options table, and troubleshooting (connection refused, first-download time, 401, 422, 503, C compiler, confidence note). Update the backends table row for laya. Verify that every command and variable name matches Laya v0.3.27's docs and our code
- [x] 3.2 Update `.env.example`: add a commented `LAYA_API_KEY`, and reword `LAYA_MODEL` as optional ("unset = Laya's router picks"). Verify the `.env.example` completeness and "copying changes nothing" tests pass

## 4. Verification

- [x] 4.1 Run `uv run ruff check src tests` and the full `uv run pytest`, and verify both are clean
- [x] 4.2 Manual, best-effort live check, which needs about 2 GB of downloads: install `laya[serve]` with `uv tool install`, start `LAYA_MODELS=english LAYA_PRELOAD=1 laya-serve`, confirm `/health`, play one game with `--brain laya --voice stub --log-dir <tmp>`, and inspect `brain-laya/` logs (no `model` field, `routing.model` is `english`, answers parsed). Record the result (including CPU latency and any 422) in the README playtest notes. If it can't be run, say so in the notes instead
