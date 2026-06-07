from collections.abc import Mapping

from .constants import ERROR_CATEGORIES, ERROR_CODES, PROVIDER

QUOTA_CODES = frozenset({"insufficient_quota", "quota_exceeded", "billing_hard_limit_reached"})
INVALID_CREDENTIAL_CODES = frozenset({"invalid_api_key", "invalid_credential", "authentication_error"})
POLICY_CODES = frozenset({"content_policy_violation", "policy_violation", "safety_violation"})
CONTEXT_CODES = frozenset({"context_length_exceeded", "context_too_large", "maximum_context_length_exceeded"})
MODEL_VALIDATION_CODES = frozenset({"model_not_found", "model_unavailable", "invalid_model", "model_not_supported"})
TIMEOUT_CODES = frozenset({"timeout", "request_timeout", "rate_limit_timeout"})
UNAVAILABLE_STATUS_CODES = frozenset({408, 500, 502, 503, 504, 529})


class ProviderAdapterError(Exception):
    def __init__(self, normalized_error):
        super().__init__(normalized_error["safeMessage"])
        self.normalized_error = normalized_error


def validation_error(code, safe_message):
    return {
        "provider": PROVIDER,
        "category": ERROR_CATEGORIES["VALIDATION"],
        "code": code,
        "retryable": False,
        "message": safe_message,
        "safeMessage": safe_message,
    }


def invalid_credential_error():
    return {
        "provider": PROVIDER,
        "category": ERROR_CATEGORIES["AUTHENTICATION"],
        "code": ERROR_CODES["INVALID_CREDENTIAL"],
        "retryable": False,
        "message": "Provider credential is invalid or expired.",
        "safeMessage": "Provider credential is invalid or expired.",
    }


def client_configuration_error():
    return {
        "provider": PROVIDER,
        "category": ERROR_CATEGORIES["INTERNAL"],
        "code": ERROR_CODES["ADAPTER_CLIENT_INVALID"],
        "retryable": False,
        "message": "Provider adapter client is not configured correctly.",
        "safeMessage": "Provider adapter client is not configured correctly.",
    }


def map_provider_error(error):
    status_code = _status_code(error)
    provider_code = _lower_text(_dig(error, "code") or _dig(error, "type") or _dig(error, "error", "code") or _dig(error, "error", "type"))
    provider_type = _lower_text(_dig(error, "type") or _dig(error, "error", "type"))
    provider_signal = provider_code or provider_type

    if status_code in {401, 403} or provider_signal in INVALID_CREDENTIAL_CODES:
        return _normalized(
            ERROR_CATEGORIES["AUTHENTICATION"],
            ERROR_CODES["INVALID_CREDENTIAL"],
            False,
            "Provider credential is invalid or expired.",
            status_code,
            provider_signal,
        )

    if status_code == 429 and provider_signal in QUOTA_CODES:
        return _normalized(
            ERROR_CATEGORIES["PROVIDER_QUOTA"],
            ERROR_CODES["PROVIDER_QUOTA_EXCEEDED"],
            False,
            "Provider quota is exhausted.",
            status_code,
            provider_signal,
        )

    if status_code == 429:
        return _normalized(
            ERROR_CATEGORIES["RATE_LIMITED"],
            ERROR_CODES["PROVIDER_RATE_LIMITED"],
            True,
            "Provider rate limit was reached.",
            status_code,
            provider_signal,
        )

    if provider_signal in POLICY_CODES:
        return _normalized(
            ERROR_CATEGORIES["POLICY"],
            ERROR_CODES["POLICY_BLOCKED"],
            False,
            "Provider policy blocked the request.",
            status_code,
            provider_signal,
        )

    if provider_signal in CONTEXT_CODES:
        return _normalized(
            ERROR_CATEGORIES["VALIDATION"],
            ERROR_CODES["CONTEXT_TOO_LARGE"],
            False,
            "Request context is too large for the provider.",
            status_code,
            provider_signal,
        )

    if provider_signal in MODEL_VALIDATION_CODES or status_code == 404:
        return _normalized(
            ERROR_CATEGORIES["MODEL_UNAVAILABLE"],
            ERROR_CODES["PROVIDER_VALIDATION_ERROR"],
            False,
            "Provider rejected the request shape.",
            status_code,
            provider_signal,
        )

    if status_code == 400:
        return _normalized(
            ERROR_CATEGORIES["VALIDATION"],
            ERROR_CODES["PROVIDER_VALIDATION_ERROR"],
            False,
            "Provider rejected the request shape.",
            status_code,
            provider_signal,
        )

    if provider_signal in TIMEOUT_CODES:
        return _normalized(
            ERROR_CATEGORIES["TIMEOUT"],
            ERROR_CODES["PROVIDER_UNAVAILABLE"],
            True,
            "Provider is temporarily unavailable.",
            status_code,
            provider_signal,
        )

    if status_code in UNAVAILABLE_STATUS_CODES:
        return _normalized(
            ERROR_CATEGORIES["DEPENDENCY"],
            ERROR_CODES["PROVIDER_UNAVAILABLE"],
            True,
            "Provider is temporarily unavailable.",
            status_code,
            provider_signal,
        )

    return _normalized(
        ERROR_CATEGORIES["DEPENDENCY"],
        ERROR_CODES["UNKNOWN_PROVIDER_ERROR"],
        False,
        "Provider request failed.",
        status_code,
        provider_signal,
    )


def _normalized(category, code, retryable, safe_message, status_code, provider_signal):
    return {
        "provider": PROVIDER,
        "category": category,
        "code": code,
        "retryable": retryable,
        "message": safe_message,
        "safeMessage": safe_message,
        "providerStatusCode": status_code if isinstance(status_code, int) else None,
        "providerErrorSignal": provider_signal or None,
    }


def _status_code(error):
    value = _dig(error, "statusCode") or _dig(error, "status") or _dig(error, "response", "status")
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _dig(value, *path):
    current = value
    for key in path:
        if isinstance(current, Mapping):
            current = current.get(key)
        else:
            current = getattr(current, key, None)
        if current is None:
            return None
    return current


def _lower_text(value):
    return str(value).lower() if value is not None else ""
