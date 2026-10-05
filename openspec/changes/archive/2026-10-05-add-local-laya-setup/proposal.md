## Why

The game supports Laya as a local, free decision AI (`--brain laya`), but the README only says "a local server at `LAYA_BASE_URL`", with no install or run steps. Its defaults were also guesses written before we had read Laya's documentation. Having now read the Laya repository (https://github.com/NandhaKishorM/laya, v0.3.27, Apache-2.0), we found that the endpoint and port are right, but three things are not:
1. **Auth:** `laya-serve` can require `Authorization: Bearer <LAYA_API_KEY>`, and our client never sends a key.
2. **Model name:** we send `model: "laya"`, a made-up name that Laya only treats as "let the router choose" by accident.
3. **Confidence scale:** Laya's `confidence` on choice and score answers is 1 − normalised entropy, not Jev's (n·p_max − 1)/(n − 1). Laya's own docs warn that Jev thresholds do not transfer. Our 0.55 "clarify" and "uncertain" thresholds were set on Jev's scale, so with Laya the investor would misjudge how sure it is: often far too unsure on spread-out answers, and differently on others.

## What Changes

- **Docs:** a new README section, "Running Laya locally":
  - install with `uv tool install "laya[serve]"`, or pip in its own virtual environment;
  - run with `laya-serve` (preloading the English checkpoint), or through Laya's Docker Compose HTTP service;
  - check the server with `GET /health`, then connect the game through `.env`;
  - GPU and CPU notes, the recommended brain timeout on CPU, the shared `LAYA_API_KEY`, and troubleshooting (401, 503, first-download time, the C-compiler error).
  - The backend table and `.env.example` are updated to match.
- **Config:** a new `LAYA_API_KEY` setting. When set, the game sends it as a bearer token to the Laya server, and it is redacted from LLM logs like the other keys.
- **Config:** `LAYA_MODEL` becomes optional with no default. When it is unset, the request carries no `model` field and Laya's router picks the checkpoint. When it is set (for example `english`), it is sent as-is. Logs and `game.json` record the model as `auto` when unset.
- **Behaviour:** for the `laya` backend only, the adapter recomputes each choice and score answer's confidence on Jev's scale from the returned probabilities, so the existing thresholds mean the same thing on both backends. Raw Laya responses, including Laya's own `confidence`, stay visible in the LLM call logs.
- Not included (by choice): a startup reachability check and a different default timeout for Laya. Both are covered by documentation instead.

## Capabilities

### New Capabilities
<!-- None. -->

### Modified Capabilities
- `investor-brain`: adds a "Laya server compatibility" requirement covering the optional model, bearer auth and Jev-scale confidence.
- `cli-interface`: the "Configuration" requirement adds `LAYA_API_KEY`, `LAYA_MODEL` and `TYPESAFE_MODEL` (an already supported but undocumented setting) to the backend settings read from the environment.

## Impact

- **Code:**
  - `brain/systemone.py`: optional model, and confidence normalisation for Laya.
  - `config.py`: `LAYA_API_KEY`, the Laya model default, secrets for log redaction, and the `backends()` model label.
  - No changes to the policy, engine or CLI flow.
- **Docs:** `README.md` and `.env.example`. The existing test that keeps `.env.example` complete will require the new variable.
- **Tests:** adapter tests built from Laya's documented sample response, config tests, and a log-redaction test for the Laya key. An optional manual check runs against a real `laya-serve` (it downloads about 2 GB of PyTorch and checkpoint weights).
- **Dependencies:** none for the game. Laya is installed separately and is never a dependency of this project.
