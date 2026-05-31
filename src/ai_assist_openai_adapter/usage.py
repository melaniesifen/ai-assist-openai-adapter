from collections.abc import Mapping


def normalize_usage(raw_usage=None):
    raw = raw_usage if isinstance(raw_usage, Mapping) else {}
    input_tokens = _number_or_zero(
        _first_present(raw, "inputTokens", "prompt_tokens", "promptTokens", "input_tokens")
    )
    output_tokens = _number_or_zero(
        _first_present(raw, "outputTokens", "completion_tokens", "completionTokens", "output_tokens")
    )
    total_tokens = _number_or_zero(
        _first_present(raw, "totalTokens", "total_tokens", default=input_tokens + output_tokens)
    )

    return {
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "totalTokens": total_tokens,
    }


def _first_present(mapping, *keys, default=None):
    for key in keys:
        if key in mapping:
            return mapping[key]
    return default


def _number_or_zero(value):
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)) and value >= 0:
        return value
    return 0
