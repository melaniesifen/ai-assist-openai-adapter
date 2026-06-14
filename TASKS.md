# Task Breakdown

Update this file as implementation progresses. Check off completed tasks in the same change that implements or verifies them.

Canonical cross-repo source: `../ai-assist-architecture/implementation-task-breakdown.md`.
Relevant design sources: provider adapter section in `../ai-assist-architecture/ai-workflow-assistant-platform-architecture-spec.md`, `../ai-assist-architecture/lld-auth-secrets-tenancy.md`, and `../ai-assist-architecture/lld-operations-safety.md`.

## Completed Bootstrap And Migration

- [x] Create the initial temporary dependency-light Node.js ESM package.
- [x] Replace the temporary Node.js ESM bootstrap with the current Python stdlib package layout.
- [x] Implement injected OpenAI client boundary.
- [x] Implement credential validation wrapper.
- [x] Implement generation and stream normalization.
- [x] Implement usage/error normalization and safe logging helper.
- [x] Port unit tests from `node:test` to Python stdlib `unittest`.
- [x] Document tests and coverage commands.
- [x] Ignore local prompts, feedback, coverage output, dependencies, and build artifacts.
- [x] Standardize Python layout to `src/ai_assist_openai_adapter/` and `tests/`, with package metadata in `pyproject.toml`.

## Architecture Tasks

- [ ] REPO-001: Decide final language, runtime, package manager, and package/module layout for this adapter; distinguish the completed temporary Node.js ESM bootstrap history and current Python REPO-002 state from the final production shape.
- [x] REPO-002: Migrate this adapter from the temporary Node.js ESM bootstrap to Python, preserving or intentionally superseding current validation, generation, streaming, usage normalization, error normalization, safe logging, and tests.
- Migration gate satisfied for this repo by the Python stdlib package migration; REPO-001 remains open for final package manager and published package/module decisions.
- [ ] PROVIDER-001: Align the local adapter contract with the shared provider interface from `ai-assist-contracts` once published.
- [x] PROVIDER-001: Support local injected-client methods for credential validation, generate response, stream response, usage metadata, and normalized provider errors.
- [x] PROVIDER-001: Keep prompt strategy, workflow selection, context retrieval, `SessionSecrets` storage, proposed actions, and session transport outside this repo.
- [ ] PROVIDER-001: Add shared provider contract tests with orchestration/contracts for validation, generation, streaming chunks, usage metadata, and error categories.
- [ ] PROVIDER-001: Add integration tests against the published provider contract and an OpenAI-compatible fake for validation, generate, stream, usage, and normalized errors.
- [ ] PROVIDER-002: Add a production OpenAI SDK or HTTP client wrapper behind the injected boundary.
- [ ] PROVIDER-002: Document and implement OpenAI credential-validation retry bounds and rate-limit behavior.
- [x] PROVIDER-002: Support platform-owned provider access metadata as the default generation and stream path without requiring user-pasted credentials.
- [x] PROVIDER-002: Normalize OpenAI streaming deltas into provider-neutral stream output in the bootstrap adapter.
- [x] PROVIDER-002: Return usage metadata without logging raw prompts, context, model responses, or provider keys.
- [x] PROVIDER-002: Normalize OpenAI quota, auth, model, timeout, context-too-large, policy-blocked, and provider rate-limit failures to the shared error categories.
- [ ] PROVIDER-004: Surface expired or missing `SessionSecrets` as re-enter-key provider errors without attempting provider calls.
- [ ] PROVIDER-004: Return typed provider failures suitable for orchestration to emit through `SessionEvent` errors.
- [ ] AUTH-005: Support safe backend provider-key validation through this adapter without storing raw keys or logging raw provider errors.
- [x] OPS-003: Verify metadata-only logging against the operations LLD allow-list and forbidden-field list.
- [x] SAFE-003: Verify this adapter does not retain raw prompts, document context, model responses, screenshots, OCR text, accessibility trees, provider keys, or decrypted action payloads.

## M5 Provider Adapter Stream Contract Evidence

- [x] M5-T4.1 OpenAI fake stream tests cover deterministic deltas, final response metadata, usage metadata, and safe errors without real provider calls.
- [x] M5-T4.3 OpenAI stream output uses provider-neutral event names: `assistant.delta`, `assistant.final`, and `error`; OpenAI error categories align to platform-safe contract/orchestration categories.
- [x] M5-T4.4 OpenAI tests verify metadata-only logging excludes raw prompts, model response bodies, provider keys, and secret material.
- [x] M5-T4.5 OpenAI adapter `TASKS.md` updated for M5-T4 OpenAI evidence. Anthropic evidence remains owned by the Anthropic adapter worker.
- [x] M5-T4.6 OpenAI adapter tests and compile checks passed after review feedback was resolved.
- [x] M5-T4.7 Fresh review feedback was written for the current OpenAI diff and the blocking contract-category finding was resolved.

## E2E-Owned Validation Support

- [ ] E2E-001: Provide testable OpenAI key-validation behavior for onboarding without raw key leakage in logs.
- [ ] E2E-002: Provide testable OpenAI generate/stream behavior for the read/context/generate path.
- [x] E2E-005: Provide test hooks or fixtures for provider quota, rate-limit, timeout, missing access, optional BYO, platform access, and metadata-only logging scenarios.
- [ ] E2E-005: Validate OpenAI outage, quota exhaustion, timeout, invalid model, invalid key, and provider rate-limit failure modes without raw prompt or key logging.

## M8 Provider Access Evidence

- [x] M8-T4.1: OpenAI adapter accepts platform-owned provider access metadata for generation and streaming without user-pasted credentials.
- [x] M8-T4.2: OpenAI provider status helper reports available, unavailable, misconfigured, quota-limited, and optional BYO states without secrets.
- [x] M8-T4.3: BYO credential handling remains explicit and optional; missing provider access fails closed.
- [x] M8-T4.4: Existing stream/error wrappers plus new tests cover timeout, rate-limit, auth, quota, empty stream, successful stream, and metadata-only logging.
- [x] M8-T4.7: Added provider-access tests for platform access, optional BYO, missing access, status metadata, and safe logs.

## M9 Provider Access Evidence

- [x] M9-T4.4: OpenAI adapter deployed-shaped request and stream behavior stays behind the injected client, defaults to platform-owned access when supplied, fails closed on missing platform secret references, maps invalid credentials, quota, rate-limit, timeout, access-denied, and access-unavailable errors to safe categories/codes, handles empty or unknown terminal streams, and emits metadata-only logs.
- [x] M9-T4.7: Focused fake-backed tests cover missing provider access, missing platform secret reference, secret access denial, KMS/secret access unavailability, invalid provider credential/config, quota/rate-limit, timeout, successful stream, empty/unknown terminal stream, optional BYO access, and safe logging without real OpenAI calls.
- [x] M9-T4.9: Run OpenAI adapter unit and compile checks for this M9-T4 slice.
- [x] M9-T4.10: Write fresh review feedback for the current OpenAI adapter diff and resolve or document findings before commit.

## Quality Tasks

- [ ] Raise line coverage to at least 95%.
- [ ] Add a deployment-style CI pipeline that runs install, lint or static checks, unit tests, integration tests, coverage, and package/build verification.
- [ ] Add deployment readiness checks for required OpenAI adapter environment variables, secret references, health checks, and metadata-only log configuration.
- [ ] Add model capability discovery or a curated OpenAI capability table.
- [ ] Add structured output/tool-call normalization if MVP workflows require it.
- [ ] Add provider-specific token usage and cost metadata where available.
- [ ] Add additional OpenAI model or modality support only when product scope requires it.
