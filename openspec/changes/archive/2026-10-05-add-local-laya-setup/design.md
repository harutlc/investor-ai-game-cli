## Context

See proposal.md for the motivation. Facts from the Laya repository (v0.3.27 on PyPI; Python ≥ 3.10; Apache-2.0), read from `README.md`, `docs/http-api.md`, `docs/docker.md`, `compose.http.yaml`, `pyproject.toml` and `laya/serve.py`:

- **Install and run:** `pip install "laya[serve]"` adds FastAPI and uvicorn and the `laya-serve` console script. `laya-serve` binds `0.0.0.0:8000` by default and is configured only through environment variables (`LAYA_HOST`, `LAYA_PORT`, `LAYA_DEVICE`, `LAYA_PRELOAD`, `LAYA_MODELS`, `LAYA_THREADS`, `LAYA_API_KEY`, …). It does not read `.env` files.
- **Checkpoints:** downloaded from Hugging Face on first use. `english` and `typed-decisions` are about 421M parameters each, and `multilingual` about 322M. The router picks by language unless `model` names a checkpoint. A `model` that is unknown and not a path ("laya", "jev-1") means "router chooses"; a path or an unpublished Hub id is a 422.
- **Docker:** from a Laya checkout, `docker compose -f compose.yaml -f compose.http.yaml up --build laya-serve` publishes `127.0.0.1:8000`, uses `LAYA_PRELOAD=0` by default, and needs about 8 GB RAM and 10 GB disk.
- **Wire format:** the same as Jev (`POST /v1/systemone`, `answers`, `usage`), plus extra keys (`routing`, `answer_confidence`, `action`), which our parser already ignores. `GET /health` is always open. Errors include 401 (bearer), 413 (limits), 422 (an invalid question, or options over the head token budget), 500 and 503 (busy).
- **Confidence:** on choice and score answers it is `1 − H(p)/log(k)`, not Jev's `(n·p_max − 1)/(n − 1)`. Checked against TypeSafe's documented example: probabilities 0.88/0.12/0 give 0.82 by the Jev formula (Jev reports 0.81), and 0/0.95/0.05 give 0.925 (Jev reports 0.92).

What exists in our code today:
- `SystemOneBackend.laya()` defaults to `LAYA_BASE_URL=http://localhost:8000` and `LAYA_MODEL="laya"`, always sends `model`, and accepts `api_key` that `config.build_brain` never passes.
- `parse_answer()` uses the server's `confidence` when present.
- `Settings.secrets()` covers the TypeSafe and Anthropic keys only.

## Goals / Non-Goals

**Goals:**
- A copy-paste path from zero to `investor-game --brain laya` on macOS or Linux, with and without Docker.
- Defaults that match Laya's real behaviour, optional auth, and thresholds that behave the same on both decision backends.

**Non-Goals:**
- Installing or launching Laya from the game, or making Laya a dependency.
- A startup health check or a different default timeout for Laya. The user declined both; they are covered by documentation.
- Calibrating thresholds per backend, or using Laya's batch endpoint, `min_confidence`, `lang` or `task` controls.

## Decisions

### D1. Optional model: omit the field unless configured
`SystemOneBackend` takes `model: str | None`. The body includes `"model"` only when it is not `None`. `LAYA_MODEL` has no default, while Jev keeps `jev-latest`. For display (log `model` field, `game.json`, `Settings.backends()`), an unset Laya model is shown as `"auto"`, meaning the router's choice. The checkpoint that actually answered is visible in the logged response's `routing.model`.
*Alternative:* default to `english`, since our states are English JSON. This was rejected because players may type in other languages, and Laya's router handles that. Users can still pin `LAYA_MODEL=english`.

### D2. `LAYA_API_KEY` for the client
`Settings` gains `laya_api_key`, read with `get("LAYA_API_KEY")`. `build_brain` passes it to `SystemOneBackend.laya(api_key=...)`, which already adds the `Authorization: Bearer` header. `Settings.secrets()` includes it, so log redaction scrubs its value. It stays optional, with no missing-key error, because a local server has no auth by default.
The name deliberately matches the variable `laya-serve` reads. When the user exports it in the shell that runs both, one value secures both. The docs note that `.env` is read only by the game, so `laya-serve` needs the key exported, or passed through Docker's `LAYA_API_KEY`/`LAYA_API_KEY_FILE`.

### D3. Jev-scale confidence for Laya, computed in the adapter
`SystemOneBackend` gets `jev_confidence: bool`, set to `False` for Jev and `True` for Laya, and `parse_answer(data, question, recompute_confidence=...)` applies it. For `choice`, it uses `n = len(probabilities)` (falling back to the number of criteria) and `p = probabilities[choice]`. For `score`, it uses `n` levels and `p = probabilities[str(level)]`. Then `conf = clamp((n·p − 1)/(n − 1), 0, 1)`; when `n < 2`, it uses `p`. When the probabilities are missing or empty, it falls back to `answer_confidence`, then to `confidence`. `noul` answers carry no confidence in our model and are unchanged.
Doing this at parse time means everything downstream (policy thresholds, the `uncertain` flag, insights) sees one scale with no backend checks. The raw response, including Laya's own `confidence` and `answer_confidence`, is preserved in the LLM call logs.
*Alternatives:* (a) use Laya's `answer_confidence` (p_max). This was rejected because p_max has a different scale from Jev's confidence when there are many options (0.4 of 7 options is not "40% sure"), so thresholds would still drift. (b) Per-backend thresholds. This was rejected because it spreads backend knowledge into the policy; one normalised scale is simpler.

### D4. Documentation layout
The README gets a new section, "Running Laya locally (free decision AI)", placed after "Choosing AI backends":
1. **What and requirements:** Laya is a separate open-source project. It needs Python ≥ 3.10, about 2 GB of downloads (PyTorch plus the English checkpoint), and runs on CPU, CUDA or Apple Silicon.
2. **Option A, `uv tool install "laya[serve]"`** (an isolated tool environment, with `laya-serve` on the PATH), then `LAYA_MODELS=english LAYA_PRELOAD=1 laya-serve`. A pip alternative: `python3 -m venv ~/.venvs/laya && ~/.venvs/laya/bin/pip install "laya[serve]"`.
3. **Option B, Docker:** `git clone`, then `docker compose -f compose.yaml -f compose.http.yaml up --build laya-serve` with `LAYA_PRELOAD=1`.
4. **Check:** `curl -s localhost:8000/health` should show `"loaded": ["english"]`.
5. **Connect:** in `.env`, set `INVESTOR_GAME_BRAIN=laya`, optionally `LAYA_BASE_URL`, and `INVESTOR_GAME_BRAIN_TIMEOUT=30` on CPU. Run `uv run investor-game --log-dir logs` and confirm `brain-laya/` logs appear.
6. **Options table:** `LAYA_MODEL` (optional pin), `LAYA_API_KEY` (shared with the server), `LAYA_DEVICE`, `LAYA_THREADS`.
7. **Troubleshooting:** connection refused, a slow first request (download and preload), 401 (key mismatch), 422 (option budget), 503 (busy), `Failed to find C compiler` (`TORCH_DISABLE_NATIVE_JIT=1`), and the confidence note.

`.env.example` gains `LAYA_API_KEY` and an updated `LAYA_MODEL` comment ("optional; unset = Laya picks"). The backend table's laya row lists the new settings.

### D5. Tests
- Build adapter tests from Laya's documented `/v1/systemone` sample (respx): with no model, assert that the body has no `model` key; with `LAYA_MODEL`, assert that it is present; assert the bearer header is sent only with a key; assert recomputed confidences of 0.928 (choice) and 0.218 (score, marked uncertain); and assert Jev's confidence passes through unchanged.
- Config tests: `LAYA_API_KEY` is read, passed to the backend and included in `secrets()`; `backends()` shows `"auto"`; and `--brain laya` reports no missing settings.
- A logging test: a Laya call with a key has a redacted header, and the key value does not appear in the file.
- The `.env.example` completeness test automatically requires `LAYA_API_KEY`.
- A manual, optional, best-effort check against a real `laya-serve` via `uv tool install`, playing one game with `--brain laya --log-dir`. It is recorded in the README playtest notes.

## Risks / Trade-offs

- [Our question criteria may exceed Laya's option token budget: `head_max_len` of 192 tokens on the English checkpoint] → Our largest question (intent) has 7 short descriptions, which should fit. A 422 surfaces as a normal `BrainError` ("couldn't respond"), and the manual live check will reveal it. Shortening criteria is follow-up work if needed.
- [CPU latency on a 10-question request may approach the 10-second default timeout] → Documented `INVESTOR_GAME_BRAIN_TIMEOUT=30` for CPU, plus `LAYA_PRELOAD=1` so the first turn doesn't pay for the load.
- [Jev-scale confidence from Laya probabilities is still uncalibrated against our thresholds] → It keeps the same meaning as on Jev. Laya's own docs recommend fitting thresholds on real traffic, which is out of scope.
- [The Laya API may evolve (the project releases often)] → The docs pin the tested version (0.3.27) and link to the upstream docs. Our parser tolerates extra keys.
