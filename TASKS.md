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
- [x] PROVIDER-002: Normalize OpenAI streaming deltas into provider-neutral stream output in the bootstrap adapter.
- [x] PROVIDER-002: Return usage metadata without logging raw prompts, context, model responses, or provider keys.
- [ ] PROVIDER-002: Normalize OpenAI quota, auth, model, timeout, context-too-large, policy-blocked, and provider rate-limit failures to the shared error categories.
- [ ] PROVIDER-004: Surface expired or missing `SessionSecrets` as re-enter-key provider errors without attempting provider calls.
- [ ] PROVIDER-004: Return typed provider failures suitable for orchestration to emit through `SessionEvent` errors.
- [ ] AUTH-005: Support safe backend provider-key validation through this adapter without storing raw keys or logging raw provider errors.
- [ ] OPS-003: Verify metadata-only logging against the operations LLD allow-list and forbidden-field list.
- [ ] SAFE-003: Verify this adapter does not retain raw prompts, document context, model responses, screenshots, OCR text, accessibility trees, provider keys, or decrypted action payloads.

## E2E-Owned Validation Support

- [ ] E2E-001: Provide testable OpenAI key-validation behavior for onboarding without raw key leakage in logs.
- [ ] E2E-002: Provide testable OpenAI generate/stream behavior for the read/context/generate path.
- [ ] E2E-005: Provide test hooks or fixtures for provider quota, rate-limit, timeout, expired-secret, and metadata-only logging scenarios.
- [ ] E2E-005: Validate OpenAI outage, quota exhaustion, timeout, invalid model, invalid key, and provider rate-limit failure modes without raw prompt or key logging.

## Quality Tasks

- [ ] Raise line coverage to at least 95%.
- [ ] Add a deployment-style CI pipeline that runs install, lint or static checks, unit tests, integration tests, coverage, and package/build verification.
- [ ] Add deployment readiness checks for required OpenAI adapter environment variables, secret references, health checks, and metadata-only log configuration.
- [ ] Add model capability discovery or a curated OpenAI capability table.
- [ ] Add structured output/tool-call normalization if MVP workflows require it.
- [ ] Add provider-specific token usage and cost metadata where available.
- [ ] Add additional OpenAI model or modality support only when product scope requires it.
