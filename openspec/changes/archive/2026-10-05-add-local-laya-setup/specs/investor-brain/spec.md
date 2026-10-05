## ADDED Requirements

### Requirement: Laya server compatibility
When the `laya` backend is selected, the brain SHALL talk to a `laya-serve` server at `LAYA_BASE_URL` (default `http://localhost:8000`) using `POST /v1/systemone`, and SHALL apply these Laya-specific rules:
- **Model:** the `model` field SHALL be omitted unless `LAYA_MODEL` is set. In that case the configured value (for example `english`, `multilingual` or `typed-decisions`) SHALL be sent unchanged.
- **Auth:** when `LAYA_API_KEY` is set, every request SHALL carry `Authorization: Bearer <key>`. When it is not set, no `Authorization` header SHALL be sent.
- **Confidence scale:** for every `choice` and `score` answer, the confidence used by the game (thresholds, "uncertain" marks and Brain insights) SHALL be computed from the returned probabilities on Jev's scale, `(n·p − 1)/(n − 1)`, where `n` is the number of options or levels and `p` is the probability of the chosen option or level. The result SHALL be clamped to `[0, 1]`. Laya's own `confidence` value SHALL NOT be used for these decisions. If the probabilities are missing, the probability of the chosen answer (`answer_confidence`) SHALL be used instead. `noul` answers SHALL be unaffected.

The `jev` backend SHALL keep using the confidence the server returns.

#### Scenario: No model configured
- **WHEN** the brain is `laya` and `LAYA_MODEL` is not set
- **THEN** the request body has `state` and `questions` but no `model` field

#### Scenario: Model configured
- **WHEN** `LAYA_MODEL=english`
- **THEN** the request body has `"model": "english"`

#### Scenario: Secured server
- **WHEN** `LAYA_API_KEY=local-secret` is set
- **THEN** each Laya request carries `Authorization: Bearer local-secret`, and LLM call logs show it as `[REDACTED]`, with `local-secret` appearing nowhere in the log files

#### Scenario: Confidence recomputed on Jev's scale
- **WHEN** Laya answers a 3-option choice with probabilities 0.9519, 0.0327 and 0.0154, and reports `confidence` 0.797
- **THEN** the game uses confidence 0.928 for that answer

#### Scenario: Spread-out score
- **WHEN** Laya answers a 4-level score whose highest probability is 0.4136, and reports `confidence` 0.1925
- **THEN** the game uses confidence 0.218, and Brain insights mark the answer "uncertain"

#### Scenario: Jev unchanged
- **WHEN** the brain is `jev` and Jev returns `confidence` 0.81 for a choice
- **THEN** the game uses 0.81
