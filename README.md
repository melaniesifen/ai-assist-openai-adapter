# ai-assist-openai-adapter

OpenAI provider adapter bootstrap for the AI Assist Platform.

This package owns OpenAI-specific credential validation, generation request mapping, streaming event normalization, usage normalization, capability metadata, and safe provider error mapping. It does not own provider key storage, prompt construction, context retrieval, proposed actions, document mutation, or session transport.

## Current Boundary

- Runtime: dependency-light Node.js ESM.
- Tests: built-in `node:test`.
- Network: no direct provider calls in this bootstrap.
- Provider access: injected client only.
- Logging: metadata allow-list only; raw prompts, message content, provider keys, tokens, model outputs, and raw provider errors are rejected from adapter logs.

The orchestration service should pass a decrypted short-lived session secret to this adapter only for the duration of a provider call. The adapter never stores the credential and never returns it.

## Public Shape

```js
import { createOpenAiAdapter } from "./src/index.js";

const adapter = createOpenAiAdapter({
  client: {
    async validateCredential(request) {},
    async generate(request) {},
    stream(request) {}
  }
});
```

Adapter methods:

- `validateCredential({ credential, requestId, correlationId })`
- `generate({ credential, model, messages, temperature, maxOutputTokens, requestId, correlationId })`
- `stream({ credential, model, messages, temperature, maxOutputTokens, requestId, correlationId })`
- `getCapabilities()`

All provider responses are normalized to platform-facing shapes. Provider errors are mapped to stable categories and safe codes before being returned or logged.

## Future SDK/HTTP Adapter

A future production client can wrap the OpenAI SDK or a minimal HTTP client behind the injected interface:

- `validateCredential` should make a low-cost server-side validation request and return metadata only.
- `generate` should return raw OpenAI response metadata needed for normalization.
- `stream` should return an async iterable of raw OpenAI stream events.

The client wrapper, not this adapter contract, owns SDK initialization, HTTP timeouts, retries, and provider endpoint details.

## Service Boundary

This repo is an internal provider-adapter service boundary. Orchestration owns workflow decisions, prompt assembly, context consent enforcement, and proposed-action creation. This adapter owns only OpenAI-specific provider translation and returns no raw prompt or output content in logs.

## Commands

```sh
node --test
```
