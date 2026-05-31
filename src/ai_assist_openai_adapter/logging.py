import re

from .usage import normalize_usage

ALLOWED_FIELDS = frozenset(
    {
        "timestamp",
        "service",
        "environment",
        "tenantId",
        "userId",
        "sessionId",
        "requestId",
        "correlationId",
        "route",
        "operation",
        "statusCode",
        "durationMs",
        "errorCategory",
        "errorCode",
        "provider",
        "connector",
        "model",
        "tokenUsage",
        "rateLimitDecision",
        "dependencyStatus",
    }
)

FORBIDDEN_FIELD_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"prompt",
        r"message",
        r"content",
        r"response",
        r"output",
        r"completion",
        r"selected.*text",
        r"document.*text",
        r"api.*key",
        r"credential",
        r"secret",
        r"authorization",
        r"cookie",
        r"bearer",
        r"oauth",
        r"access.*token",
        r"refresh.*token",
    )
)


def sanitize_log_fields(fields):
    if not isinstance(fields, dict):
        raise TypeError("Log fields must be an object.")

    _assert_no_forbidden_fields(fields, exempt_top_level_fields=frozenset({"tokenUsage"}))

    safe = {}
    for key, value in fields.items():
        if key not in ALLOWED_FIELDS or value is None:
            continue
        if key == "tokenUsage":
            safe[key] = normalize_usage(value)
            continue
        safe[key] = value
    return safe


class SafeLogger:
    def __init__(self, sink=None):
        self._sink = sink or _PrintSink()

    def info(self, fields):
        self._write("info", fields)

    def warn(self, fields):
        self._write("warn", fields)

    def error(self, fields):
        self._write("error", fields)

    def _write(self, level, fields):
        safe_fields = sanitize_log_fields(fields)
        writer = getattr(self._sink, level, None) or getattr(self._sink, "log", None)
        if writer is None:
            raise TypeError("Log sink must expose info/warn/error or log.")
        writer(safe_fields)


def create_safe_logger(sink=None):
    return SafeLogger(sink)


def _assert_no_forbidden_fields(value, path=(), exempt_top_level_fields=frozenset()):
    if not isinstance(value, dict):
        return

    for key, nested in value.items():
        next_path = (*path, key)
        if len(next_path) == 1 and key in exempt_top_level_fields:
            continue
        if any(pattern.search(key) for pattern in FORBIDDEN_FIELD_PATTERNS):
            raise TypeError(f"Forbidden log field: {'.'.join(next_path)}")
        _assert_no_forbidden_fields(nested, next_path, exempt_top_level_fields)


class _PrintSink:
    def log(self, fields):
        print(fields)
