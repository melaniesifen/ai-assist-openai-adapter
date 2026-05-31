# ai-assist-openai-adapter

OpenAI provider adapter package for the AI Assist Platform.

This package owns OpenAI-specific credential validation, generation request mapping, streaming event normalization, usage normalization, capability metadata, and safe provider error mapping. It does not own provider key storage, prompt construction, context retrieval, proposed actions, document mutation, or session transport.

## Current Boundary

- Runtime: Python 3 stdlib package layout under `src/ai_assist_openai_adapter`.
- Tests: stdlib `unittest`.
- Network: no direct provider calls in this bootstrap.
- Provider access: injected client only.
- Logging: metadata allow-list only; raw prompts, message content, provider keys, tokens, model outputs, and raw provider errors are rejected from adapter logs.

The orchestration service should pass a decrypted short-lived session secret to this adapter only for the duration of a provider call. The adapter never stores the credential and never returns it.

## Public Shape

```python
from ai_assist_openai_adapter import create_openai_adapter

adapter = create_openai_adapter(
    client=client_with_validate_credential_generate_and_stream
)
```

Adapter methods:

- `await validate_credential({ "credential": credential, "requestId": request_id, "correlationId": correlation_id })`
- `await generate({ "credential": credential, "model": model, "messages": messages, "temperature": temperature, "maxOutputTokens": max_output_tokens, "requestId": request_id, "correlationId": correlation_id })`
- `stream({ "credential": credential, "model": model, "messages": messages, "temperature": temperature, "maxOutputTokens": max_output_tokens, "requestId": request_id, "correlationId": correlation_id })`
- `get_capabilities()`

All provider responses are normalized to platform-facing shapes. Provider errors are mapped to stable categories and safe codes before being returned or logged.

## Future SDK/HTTP Adapter

A future production client can wrap the OpenAI SDK or a minimal HTTP client behind the injected interface:

- `validateCredential` should make a low-cost server-side validation request and return metadata only.
- `generate` should return raw OpenAI response metadata needed for normalization.
- `stream` should return an async iterable of raw OpenAI stream events.

The client wrapper, not this adapter contract, owns SDK initialization, HTTP timeouts, retries, and provider endpoint details.

## Service Boundary

This repo is an internal provider-adapter service boundary. Orchestration owns workflow decisions, prompt assembly, context consent enforcement, and proposed-action creation. This adapter owns only OpenAI-specific provider translation and returns no raw prompt or output content in logs.

## Task Breakdown

Implementation tasks are tracked in [TASKS.md](TASKS.md). Update the checkboxes there in the same change that implements or verifies a task.

## Testing And Coverage

Run the unit tests with either command:

```sh
PYTHONPATH=src python3 -m unittest discover -s test
```

No repo-local third-party dependencies are required for the current tests. If later tooling writes HTML, LCOV, TAP, JUnit, or build output, those generated paths are ignored by `.gitignore`.
