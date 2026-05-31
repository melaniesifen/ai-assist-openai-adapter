import inspect
from collections.abc import AsyncIterable, Iterable, Mapping

from .constants import CAPABILITIES, ERROR_CODES, PROVIDER, STREAM_EVENT_TYPES
from .errors import client_configuration_error, invalid_credential_error, map_provider_error, validation_error
from .logging import create_safe_logger
from .usage import normalize_usage

SUPPORTED_MESSAGE_ROLES = frozenset({"system", "user", "assistant"})


class OpenAiAdapter:
    provider = PROVIDER

    def __init__(self, *, client, logger=None):
        _assert_client(client)
        self._client = client
        self._logger = logger or create_safe_logger()

    def get_capabilities(self):
        return CAPABILITIES

    async def validate_credential(self, request=None):
        request = _request_or_empty(request)
        metadata = _build_log_metadata("validateCredential", request)
        credential_error = _validate_credential_value(request.get("credential"))
        if credential_error:
            self._logger.warn({**metadata, "errorCategory": credential_error["category"], "errorCode": credential_error["code"]})
            return _credential_validation_result(False, "invalid", credential_error)

        self._logger.info({**metadata, "dependencyStatus": "attempt"})
        try:
            result = await _maybe_await(
                self._client.validate_credential(
                    {
                        "provider": PROVIDER,
                        "credential": request["credential"],
                    }
                )
            )
            if not isinstance(result, Mapping) or result.get("valid") is not True:
                normalized_error = map_provider_error(result.get("error")) if isinstance(result, Mapping) and result.get("error") else invalid_credential_error()
                self._logger.warn({**metadata, "errorCategory": normalized_error["category"], "errorCode": normalized_error["code"]})
                status = result.get("status", "rejected") if isinstance(result, Mapping) else "rejected"
                raw = result if isinstance(result, Mapping) else {}
                return _credential_validation_result(False, status, normalized_error, raw)
            return _credential_validation_result(True, result.get("status", "valid"), None, result)
        except Exception as error:
            normalized_error = map_provider_error(error)
            self._logger.warn({**metadata, "errorCategory": normalized_error["category"], "errorCode": normalized_error["code"]})
            return _credential_validation_result(False, "rejected", normalized_error)

    async def generate(self, request=None):
        request = _request_or_empty(request)
        metadata = _build_log_metadata("generate", request)
        request_error = _validate_generate_request(request)
        if request_error:
            self._logger.warn({**metadata, "errorCategory": request_error["category"], "errorCode": request_error["code"]})
            return _generate_error_result(request.get("model"), request_error)

        self._logger.info({**metadata, "dependencyStatus": "attempt"})
        try:
            raw = await _maybe_await(self._client.generate(_to_openai_request(request, stream=False)))
            result = _normalize_generate_result(raw, request["model"])
        except Exception as error:
            normalized_error = map_provider_error(error)
            self._logger.warn({**metadata, "errorCategory": normalized_error["category"], "errorCode": normalized_error["code"]})
            return _generate_error_result(request.get("model"), normalized_error)

        self._logger.info({**metadata, "dependencyStatus": "ok", "tokenUsage": result["usage"]})
        return result

    async def stream(self, request=None):
        request = _request_or_empty(request)
        metadata = _build_log_metadata("stream", request)
        request_error = _validate_generate_request(request)
        if request_error:
            self._logger.warn({**metadata, "errorCategory": request_error["category"], "errorCode": request_error["code"]})
            yield _stream_error_event(request.get("model"), request_error)
            return

        self._logger.info({**metadata, "dependencyStatus": "attempt"})
        try:
            terminal_seen = False
            raw_events = await _maybe_await(self._client.stream(_to_openai_request(request, stream=True)))
            async for raw_event in _aiter(raw_events):
                normalized = _normalize_stream_event(raw_event, request["model"])
                if normalized:
                    terminal_seen = normalized["type"] in {STREAM_EVENT_TYPES["FINAL"], STREAM_EVENT_TYPES["ERROR"]}
                    yield normalized
            if not terminal_seen:
                normalized_error = map_provider_error(None)
                self._logger.warn({**metadata, "errorCategory": normalized_error["category"], "errorCode": normalized_error["code"]})
                yield _stream_error_event(request["model"], normalized_error)
        except Exception as error:
            normalized_error = map_provider_error(error)
            self._logger.warn({**metadata, "errorCategory": normalized_error["category"], "errorCode": normalized_error["code"]})
            yield _stream_error_event(request.get("model"), normalized_error)


def create_openai_adapter(*, client, logger=None):
    return OpenAiAdapter(client=client, logger=logger)


def _assert_client(client):
    if not client or not all(callable(getattr(client, name, None)) for name in ("validate_credential", "generate", "stream")):
        raise TypeError(client_configuration_error()["safeMessage"])


def _request_or_empty(request):
    if request is None:
        return {}
    if not isinstance(request, Mapping):
        return {}
    return dict(request)


def _validate_credential_value(credential):
    if not isinstance(credential, str) or len(credential.strip()) == 0:
        return validation_error(ERROR_CODES["MISSING_CREDENTIAL"], "Provider credential is required.")
    return None


def _validate_generate_request(request):
    return (
        _validate_credential_value(request.get("credential"))
        or (
            validation_error(ERROR_CODES["MISSING_MODEL"], "Provider model is required.")
            if not isinstance(request.get("model"), str) or len(request["model"].strip()) == 0
            else None
        )
        or _validate_messages(request.get("messages"))
        or _validate_generation_parameters(request)
    )


def _validate_messages(messages):
    if not isinstance(messages, list) or len(messages) == 0:
        return validation_error(ERROR_CODES["MISSING_MESSAGES"], "At least one message is required.")

    for message in messages:
        if not isinstance(message, Mapping) or message.get("role") not in SUPPORTED_MESSAGE_ROLES:
            return validation_error(ERROR_CODES["INVALID_MESSAGES"], "Messages must use supported roles.")

        if not _is_supported_content(message.get("content")):
            return validation_error(ERROR_CODES["INVALID_MESSAGES"], "Message content is required.")

    return None


def _is_supported_content(content):
    if isinstance(content, str):
        return len(content.strip()) > 0

    return (
        isinstance(content, list)
        and len(content) > 0
        and all(
            isinstance(part, Mapping)
            and part.get("type") == "text"
            and isinstance(part.get("text"), str)
            and len(part["text"].strip()) > 0
            for part in content
        )
    )


def _validate_generation_parameters(request):
    max_output_tokens = request.get("maxOutputTokens")
    if max_output_tokens is not None and (isinstance(max_output_tokens, bool) or not isinstance(max_output_tokens, int) or max_output_tokens <= 0):
        return validation_error(ERROR_CODES["PROVIDER_VALIDATION_ERROR"], "maxOutputTokens must be a positive integer.")

    temperature = request.get("temperature")
    if temperature is not None and (isinstance(temperature, bool) or not isinstance(temperature, (int, float)) or temperature < 0 or temperature > 2):
        return validation_error(ERROR_CODES["PROVIDER_VALIDATION_ERROR"], "temperature must be a number between 0 and 2.")

    return None


def _build_log_metadata(operation, request):
    return {
        "service": "ai-assist-openai-adapter",
        "operation": operation,
        "requestId": request.get("requestId"),
        "correlationId": request.get("correlationId"),
        "tenantId": request.get("tenantId"),
        "userId": request.get("userId"),
        "sessionId": request.get("sessionId"),
        "provider": PROVIDER,
        "model": request.get("model"),
    }


def _to_openai_request(request, stream):
    return {
        "provider": PROVIDER,
        "credential": request["credential"],
        "model": request["model"],
        "messages": request["messages"],
        "temperature": request.get("temperature"),
        "max_output_tokens": request.get("maxOutputTokens"),
        "stream": stream,
        "requestId": request.get("requestId"),
        "correlationId": request.get("correlationId"),
    }


def _credential_validation_result(valid, status, error, raw=None):
    raw = raw if isinstance(raw, Mapping) else {}
    return {
        "provider": PROVIDER,
        "valid": valid,
        "status": status,
        "fingerprint": raw.get("fingerprint"),
        "checkedAt": raw.get("checkedAt"),
        "error": error,
    }


def _normalize_generate_result(raw, requested_model):
    raw = raw if isinstance(raw, Mapping) else {}
    text = (
        raw.get("output_text")
        or _dig(raw, "choices", 0, "message", "content")
        or _dig(raw, "message", "content")
        or raw.get("content")
        or ""
    )

    return {
        "provider": PROVIDER,
        "ok": True,
        "model": raw.get("model") or requested_model,
        "message": {
            "role": "assistant",
            "content": str(text),
        },
        "finishReason": raw.get("finish_reason") or _dig(raw, "choices", 0, "finish_reason"),
        "usage": normalize_usage(raw.get("usage")),
    }


def _generate_error_result(model, error):
    return {
        "provider": PROVIDER,
        "ok": False,
        "model": model,
        "error": error,
    }


def _normalize_stream_event(raw_event, requested_model):
    raw = raw_event if isinstance(raw_event, Mapping) else {}
    delta = raw.get("delta") or raw.get("text") or _dig(raw, "choices", 0, "delta", "content") or _dig(raw, "choices", 0, "text")

    if isinstance(delta, str) and len(delta) > 0:
        return {
            "type": STREAM_EVENT_TYPES["DELTA"],
            "provider": PROVIDER,
            "model": raw.get("model") or requested_model,
            "delta": delta,
        }

    completed = raw.get("type") == "response.completed" or raw.get("done") is True or _dig(raw, "choices", 0, "finish_reason")
    if completed:
        response = raw.get("response") if isinstance(raw.get("response"), Mapping) else raw
        return {
            "type": STREAM_EVENT_TYPES["FINAL"],
            "provider": PROVIDER,
            "model": response.get("model") or requested_model,
            "finishReason": response.get("finish_reason") or _dig(response, "choices", 0, "finish_reason"),
            "usage": normalize_usage(response.get("usage")),
        }

    return None


def _stream_error_event(model, error):
    return {
        "type": STREAM_EVENT_TYPES["ERROR"],
        "provider": PROVIDER,
        "model": model,
        "error": error,
    }


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


async def _aiter(value):
    if isinstance(value, AsyncIterable) or hasattr(value, "__aiter__"):
        async for item in value:
            yield item
        return
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, Mapping)):
        for item in value:
            yield item
        return
    raise TypeError("OpenAI client stream must return an iterable.")


def _dig(value, *path):
    current = value
    for key in path:
        if isinstance(current, Mapping):
            current = current.get(key)
        elif isinstance(current, list) and isinstance(key, int) and 0 <= key < len(current):
            current = current[key]
        else:
            return None
        if current is None:
            return None
    return current
