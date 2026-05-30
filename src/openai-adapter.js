import { CAPABILITIES, ERROR_CODES, PROVIDER, STREAM_EVENT_TYPES } from "./constants.js";
import { clientConfigurationError, invalidCredentialError, mapProviderError, validationError } from "./errors.js";
import { createSafeLogger } from "./logging.js";
import { normalizeUsage } from "./usage.js";

export function createOpenAiAdapter({ client, logger = createSafeLogger() } = {}) {
  assertClient(client);

  return Object.freeze({
    provider: PROVIDER,

    getCapabilities() {
      return CAPABILITIES;
    },

    async validateCredential(request = {}) {
      const metadata = buildLogMetadata("validateCredential", request);
      const credentialError = validateCredentialValue(request.credential);
      if (credentialError) {
        logger.warn({ ...metadata, errorCategory: credentialError.category, errorCode: credentialError.code });
        return credentialValidationResult(false, "invalid", credentialError);
      }

      logger.info({ ...metadata, dependencyStatus: "attempt" });
      try {
        const result = await client.validateCredential({
          provider: PROVIDER,
          credential: request.credential
        });
        if (result?.valid !== true) {
          const normalizedError = result?.error ? mapProviderError(result.error) : invalidCredentialError();
          logger.warn({ ...metadata, errorCategory: normalizedError.category, errorCode: normalizedError.code });
          return credentialValidationResult(false, result?.status ?? "rejected", normalizedError, result);
        }
        return credentialValidationResult(true, result.status ?? "valid", null, result);
      } catch (error) {
        const normalizedError = mapProviderError(error);
        logger.warn({ ...metadata, errorCategory: normalizedError.category, errorCode: normalizedError.code });
        return credentialValidationResult(false, "rejected", normalizedError);
      }
    },

    async generate(request = {}) {
      const metadata = buildLogMetadata("generate", request);
      const requestError = validateGenerateRequest(request);
      if (requestError) {
        logger.warn({ ...metadata, errorCategory: requestError.category, errorCode: requestError.code });
        return generateErrorResult(request.model, requestError);
      }

      logger.info({ ...metadata, dependencyStatus: "attempt" });
      try {
        const raw = await client.generate(toOpenAiRequest(request, false));
        const result = normalizeGenerateResult(raw, request.model);
        logger.info({ ...metadata, dependencyStatus: "ok", tokenUsage: result.usage });
        return result;
      } catch (error) {
        const normalizedError = mapProviderError(error);
        logger.warn({ ...metadata, errorCategory: normalizedError.category, errorCode: normalizedError.code });
        return generateErrorResult(request.model, normalizedError);
      }
    },

    async *stream(request = {}) {
      const metadata = buildLogMetadata("stream", request);
      const requestError = validateGenerateRequest(request);
      if (requestError) {
        logger.warn({ ...metadata, errorCategory: requestError.category, errorCode: requestError.code });
        yield streamErrorEvent(request.model, requestError);
        return;
      }

      logger.info({ ...metadata, dependencyStatus: "attempt" });
      try {
        for await (const rawEvent of client.stream(toOpenAiRequest(request, true))) {
          const normalized = normalizeStreamEvent(rawEvent, request.model);
          if (normalized) {
            yield normalized;
          }
        }
      } catch (error) {
        const normalizedError = mapProviderError(error);
        logger.warn({ ...metadata, errorCategory: normalizedError.category, errorCode: normalizedError.code });
        yield streamErrorEvent(request.model, normalizedError);
      }
    }
  });
}

function assertClient(client) {
  if (!client || typeof client.validateCredential !== "function" || typeof client.generate !== "function" || typeof client.stream !== "function") {
    throw new TypeError(clientConfigurationError().safeMessage);
  }
}

function validateCredentialValue(credential) {
  if (typeof credential !== "string" || credential.trim().length === 0) {
    return validationError(ERROR_CODES.MISSING_CREDENTIAL, "Provider credential is required.");
  }
  return null;
}

function validateGenerateRequest(request) {
  return validateCredentialValue(request.credential)
    ?? (typeof request.model !== "string" || request.model.trim().length === 0
      ? validationError(ERROR_CODES.MISSING_MODEL, "Provider model is required.")
      : null)
    ?? validateMessages(request.messages)
    ?? validateGenerationParameters(request);
}

const SUPPORTED_MESSAGE_ROLES = new Set(["system", "user", "assistant"]);

function validateMessages(messages) {
  if (!Array.isArray(messages) || messages.length === 0) {
    return validationError(ERROR_CODES.MISSING_MESSAGES, "At least one message is required.");
  }

  for (const message of messages) {
    if (!message || typeof message !== "object" || !SUPPORTED_MESSAGE_ROLES.has(message.role)) {
      return validationError(ERROR_CODES.INVALID_MESSAGES, "Messages must use supported roles.");
    }

    if (!isSupportedContent(message.content)) {
      return validationError(ERROR_CODES.INVALID_MESSAGES, "Message content is required.");
    }
  }

  return null;
}

function isSupportedContent(content) {
  if (typeof content === "string") {
    return content.trim().length > 0;
  }

  return Array.isArray(content)
    && content.length > 0
    && content.every((part) => part
      && typeof part === "object"
      && part.type === "text"
      && typeof part.text === "string"
      && part.text.trim().length > 0);
}

function validateGenerationParameters(request) {
  if (request.maxOutputTokens !== undefined && (!Number.isInteger(request.maxOutputTokens) || request.maxOutputTokens <= 0)) {
    return validationError(ERROR_CODES.PROVIDER_VALIDATION_ERROR, "maxOutputTokens must be a positive integer.");
  }

  if (request.temperature !== undefined && (typeof request.temperature !== "number" || request.temperature < 0 || request.temperature > 2)) {
    return validationError(ERROR_CODES.PROVIDER_VALIDATION_ERROR, "temperature must be a number between 0 and 2.");
  }

  return null;
}

function buildLogMetadata(operation, request) {
  return {
    service: "ai-assist-openai-adapter",
    operation,
    requestId: request.requestId,
    correlationId: request.correlationId,
    tenantId: request.tenantId,
    userId: request.userId,
    sessionId: request.sessionId,
    provider: PROVIDER,
    model: request.model
  };
}

function toOpenAiRequest(request, stream) {
  return {
    provider: PROVIDER,
    credential: request.credential,
    model: request.model,
    messages: request.messages,
    temperature: request.temperature,
    max_output_tokens: request.maxOutputTokens,
    stream,
    requestId: request.requestId,
    correlationId: request.correlationId
  };
}

function credentialValidationResult(valid, status, error, raw = {}) {
  return Object.freeze({
    provider: PROVIDER,
    valid,
    status,
    fingerprint: raw?.fingerprint ?? null,
    checkedAt: raw?.checkedAt ?? null,
    error
  });
}

function normalizeGenerateResult(raw, requestedModel) {
  const text = raw?.output_text
    ?? raw?.choices?.[0]?.message?.content
    ?? raw?.message?.content
    ?? raw?.content
    ?? "";

  return Object.freeze({
    provider: PROVIDER,
    ok: true,
    model: raw?.model ?? requestedModel,
    message: Object.freeze({
      role: "assistant",
      content: String(text)
    }),
    finishReason: raw?.finish_reason ?? raw?.choices?.[0]?.finish_reason ?? null,
    usage: normalizeUsage(raw?.usage)
  });
}

function generateErrorResult(model, error) {
  return Object.freeze({
    provider: PROVIDER,
    ok: false,
    model: model ?? null,
    error
  });
}

function normalizeStreamEvent(rawEvent, requestedModel) {
  const delta = rawEvent?.delta
    ?? rawEvent?.text
    ?? rawEvent?.choices?.[0]?.delta?.content
    ?? rawEvent?.choices?.[0]?.text;

  if (typeof delta === "string" && delta.length > 0) {
    return Object.freeze({
      type: STREAM_EVENT_TYPES.DELTA,
      provider: PROVIDER,
      model: rawEvent?.model ?? requestedModel,
      delta
    });
  }

  const completed = rawEvent?.type === "response.completed" || rawEvent?.done === true || rawEvent?.choices?.[0]?.finish_reason;
  if (completed) {
    const response = rawEvent?.response ?? rawEvent;
    return Object.freeze({
      type: STREAM_EVENT_TYPES.FINAL,
      provider: PROVIDER,
      model: response?.model ?? requestedModel,
      finishReason: response?.finish_reason ?? response?.choices?.[0]?.finish_reason ?? null,
      usage: normalizeUsage(response?.usage)
    });
  }

  return null;
}

function streamErrorEvent(model, error) {
  return Object.freeze({
    type: STREAM_EVENT_TYPES.ERROR,
    provider: PROVIDER,
    model: model ?? null,
    error
  });
}
