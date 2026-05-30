import assert from "node:assert/strict";
import test from "node:test";

import { createOpenAiAdapter, ERROR_CODES, PROVIDER, sanitizeLogFields } from "../src/index.js";

const TEST_CREDENTIAL = "sk-test-redacted";
const TEST_MODEL = "test-openai-model";
const TEST_MESSAGES = Object.freeze([{ role: "user", content: "raw prompt stays out of logs" }]);

test("exposes provider capability metadata without requiring a default model", () => {
  const adapter = createOpenAiAdapter({ client: fakeClient() });

  assert.equal(adapter.provider, PROVIDER);
  assert.equal(adapter.getCapabilities().provider, PROVIDER);
  assert.equal(adapter.getCapabilities().supportsStreaming, true);
  assert.equal(adapter.getCapabilities().supportsToolCalls, false);
  assert.equal(adapter.getCapabilities().supportsStructuredOutput, false);
  assert.equal(adapter.getCapabilities().defaultModel, null);
});

test("validateCredential rejects missing credentials without calling injected client", async () => {
  let called = false;
  const adapter = createOpenAiAdapter({
    client: fakeClient({
      async validateCredential() {
        called = true;
      }
    }),
    logger: captureLogger()
  });

  const result = await adapter.validateCredential({ credential: "   ", requestId: "req-1" });

  assert.equal(called, false);
  assert.equal(result.valid, false);
  assert.equal(result.error.code, ERROR_CODES.MISSING_CREDENTIAL);
});

test("validateCredential normalizes injected provider auth failure", async () => {
  const adapter = createOpenAiAdapter({
    client: fakeClient({
      async validateCredential() {
        throw { statusCode: 401, code: "invalid_api_key" };
      }
    }),
    logger: captureLogger()
  });

  const result = await adapter.validateCredential({ credential: TEST_CREDENTIAL });

  assert.equal(result.valid, false);
  assert.equal(result.status, "rejected");
  assert.equal(result.error.code, ERROR_CODES.INVALID_CREDENTIAL);
});

test("validateCredential fails closed for ambiguous injected client results", async () => {
  const adapter = createOpenAiAdapter({
    client: fakeClient({
      async validateCredential() {
        return {};
      }
    }),
    logger: captureLogger()
  });

  const result = await adapter.validateCredential({ credential: TEST_CREDENTIAL });

  assert.equal(result.valid, false);
  assert.equal(result.status, "rejected");
  assert.equal(result.error.code, ERROR_CODES.INVALID_CREDENTIAL);
});

test("generate maps provider-neutral request to OpenAI-style injected client request", async () => {
  let observedRequest;
  const logger = captureLogger();
  const adapter = createOpenAiAdapter({
    client: fakeClient({
      async generate(request) {
        observedRequest = request;
        return {
          model: request.model,
          output_text: "normalized answer",
          usage: { prompt_tokens: 7, completion_tokens: 3, total_tokens: 10 },
          finish_reason: "stop"
        };
      }
    }),
    logger
  });

  const result = await adapter.generate({
    credential: TEST_CREDENTIAL,
    model: TEST_MODEL,
    messages: TEST_MESSAGES,
    maxOutputTokens: 128,
    requestId: "req-2",
    correlationId: "corr-2"
  });

  assert.equal(result.ok, true);
  assert.equal(result.message.content, "normalized answer");
  assert.deepEqual(result.usage, { inputTokens: 7, outputTokens: 3, totalTokens: 10 });
  assert.equal(observedRequest.max_output_tokens, 128);
  assert.equal(observedRequest.stream, false);
  assert.equal(observedRequest.messages, TEST_MESSAGES);
  assertNoForbiddenLogMaterial(logger.entries);
});

test("generate returns stable quota error mapping", async () => {
  const adapter = createOpenAiAdapter({
    client: fakeClient({
      async generate() {
        throw { statusCode: 429, code: "insufficient_quota", message: "raw provider message" };
      }
    }),
    logger: captureLogger()
  });

  const result = await adapter.generate({
    credential: TEST_CREDENTIAL,
    model: TEST_MODEL,
    messages: TEST_MESSAGES
  });

  assert.equal(result.ok, false);
  assert.equal(result.error.code, ERROR_CODES.PROVIDER_QUOTA_EXCEEDED);
  assert.equal(result.error.safeMessage, "Provider quota is exhausted.");
});

test("generate rejects malformed messages and parameters before calling injected client", async () => {
  let called = false;
  const adapter = createOpenAiAdapter({
    client: fakeClient({
      async generate() {
        called = true;
      }
    }),
    logger: captureLogger()
  });

  const invalidMessage = await adapter.generate({
    credential: TEST_CREDENTIAL,
    model: TEST_MODEL,
    messages: [{ role: "bogus", content: "   " }]
  });
  const invalidTokens = await adapter.generate({
    credential: TEST_CREDENTIAL,
    model: TEST_MODEL,
    messages: TEST_MESSAGES,
    maxOutputTokens: -1
  });
  const invalidTemperature = await adapter.generate({
    credential: TEST_CREDENTIAL,
    model: TEST_MODEL,
    messages: TEST_MESSAGES,
    temperature: "hot"
  });

  assert.equal(called, false);
  assert.equal(invalidMessage.error.code, ERROR_CODES.INVALID_MESSAGES);
  assert.equal(invalidTokens.error.code, ERROR_CODES.PROVIDER_VALIDATION_ERROR);
  assert.equal(invalidTemperature.error.code, ERROR_CODES.PROVIDER_VALIDATION_ERROR);
});

test("stream normalizes OpenAI delta and final events", async () => {
  const adapter = createOpenAiAdapter({
    client: fakeClient({
      async *stream() {
        yield { type: "response.output_text.delta", delta: "hel" };
        yield { choices: [{ delta: { content: "lo" } }] };
        yield { type: "response.completed", response: { usage: { input_tokens: 2, output_tokens: 1 } } };
      }
    }),
    logger: captureLogger()
  });

  const events = [];
  for await (const event of adapter.stream({ credential: TEST_CREDENTIAL, model: TEST_MODEL, messages: TEST_MESSAGES })) {
    events.push(event);
  }

  assert.deepEqual(events.map((event) => event.type), ["assistant.delta", "assistant.delta", "assistant.final"]);
  assert.equal(events[0].delta, "hel");
  assert.deepEqual(events[2].usage, { inputTokens: 2, outputTokens: 1, totalTokens: 3 });
});

test("sanitizeLogFields rejects secret and prompt-bearing fields", () => {
  assert.throws(() => sanitizeLogFields({ requestId: "req", credential: TEST_CREDENTIAL }), /Forbidden log field/);
  assert.throws(() => sanitizeLogFields({ requestId: "req", nested: { prompt: "do not log" } }), /Forbidden log field/);

  assert.deepEqual(sanitizeLogFields({ requestId: "req", ignored: "value", provider: PROVIDER }), {
    requestId: "req",
    provider: PROVIDER
  });
});

function fakeClient(overrides = {}) {
  return {
    async validateCredential() {
      return { valid: true, status: "valid", fingerprint: "fp-test" };
    },
    async generate() {
      return { output_text: "ok", usage: {} };
    },
    async *stream() {},
    ...overrides
  };
}

function captureLogger() {
  const entries = [];
  return {
    entries,
    info(fields) {
      entries.push(fields);
    },
    warn(fields) {
      entries.push(fields);
    },
    error(fields) {
      entries.push(fields);
    }
  };
}

function assertNoForbiddenLogMaterial(entries) {
  const serialized = JSON.stringify(entries);
  assert.equal(serialized.includes(TEST_CREDENTIAL), false);
  assert.equal(serialized.includes("raw prompt stays out of logs"), false);
  assert.equal(serialized.includes("normalized answer"), false);
}
