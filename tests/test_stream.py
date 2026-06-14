import unittest

from ai_assist_openai_adapter import ERROR_CATEGORIES, ERROR_CODES, PROVIDER, create_openai_adapter
from tests.common import (
    CaptureLogger,
    FakeClient,
    PROVIDER_NEUTRAL_DELTA_FIELDS,
    PROVIDER_NEUTRAL_ERROR_FIELDS,
    PROVIDER_NEUTRAL_FINAL_FIELDS,
    ProviderFailure,
    TEST_CREDENTIAL,
    TEST_MESSAGES,
    TEST_MODEL,
    assert_no_forbidden_log_material,
)


class OpenAiStreamTest(unittest.IsolatedAsyncioTestCase):
    async def test_stream_normalizes_openai_delta_and_final_events_to_provider_neutral_contract(self):
        logger = CaptureLogger()

        async def stream(_request):
            yield {"type": "response.output_text.delta", "delta": "hel"}
            yield {"choices": [{"delta": {"content": "lo"}}]}
            yield {
                "type": "response.completed",
                "response": {
                    "model": TEST_MODEL,
                    "finish_reason": "stop",
                    "usage": {"input_tokens": 2, "output_tokens": 1},
                    "output_text": "final body must not be returned by stream final",
                },
            }

        adapter = create_openai_adapter(client=FakeClient(stream=stream), logger=logger)

        events = [
            event
            async for event in adapter.stream(
                {"credential": TEST_CREDENTIAL, "model": TEST_MODEL, "messages": TEST_MESSAGES}
            )
        ]

        self.assertEqual([event["type"] for event in events], ["assistant.delta", "assistant.delta", "assistant.final"])
        self.assertEqual([set(event.keys()) for event in events], [PROVIDER_NEUTRAL_DELTA_FIELDS, PROVIDER_NEUTRAL_DELTA_FIELDS, PROVIDER_NEUTRAL_FINAL_FIELDS])
        self.assertEqual([event["provider"] for event in events], [PROVIDER, PROVIDER, PROVIDER])
        self.assertEqual(events[0]["delta"], "hel")
        self.assertEqual(events[1]["delta"], "lo")
        self.assertEqual(events[2]["finishReason"], "stop")
        self.assertEqual(events[2]["usage"], {"inputTokens": 2, "outputTokens": 1, "totalTokens": 3})
        self.assertNotIn("message", events[2])
        self.assertNotIn("content", events[2])
        assert_no_forbidden_log_material(self, logger.entries)

    async def test_stream_returns_safe_error_event_for_provider_failure_with_contract_message(self):
        logger = CaptureLogger()

        async def stream(_request):
            raise ProviderFailure(statusCode=503, code="server_error")
            yield

        adapter = create_openai_adapter(client=FakeClient(stream=stream), logger=logger)

        events = [
            event
            async for event in adapter.stream(
                {"credential": TEST_CREDENTIAL, "model": TEST_MODEL, "messages": TEST_MESSAGES}
            )
        ]

        self.assertEqual(len(events), 1)
        self.assertEqual(set(events[0].keys()), PROVIDER_NEUTRAL_ERROR_FIELDS)
        self.assertEqual(events[0]["type"], "error")
        self.assertEqual(events[0]["provider"], PROVIDER)
        self.assertEqual(events[0]["error"]["category"], ERROR_CATEGORIES["DEPENDENCY"])
        self.assertEqual(events[0]["error"]["code"], ERROR_CODES["PROVIDER_UNAVAILABLE"])
        self.assertEqual(events[0]["error"]["message"], "Provider is temporarily unavailable.")
        self.assertEqual(events[0]["error"]["dependencyStatus"], "failed")
        self.assertNotIn("safeMessage", events[0]["error"])
        self.assertNotIn("retryable", events[0]["error"])
        self.assertNotIn("providerStatusCode", events[0]["error"])
        self.assertNotIn("providerErrorSignal", events[0]["error"])
        assert_no_forbidden_log_material(self, logger.entries)

    async def test_stream_error_categories_match_platform_safe_contract(self):
        cases = [
            (ProviderFailure(statusCode=401, code="invalid_api_key"), ERROR_CATEGORIES["AUTHENTICATION"], ERROR_CODES["INVALID_CREDENTIAL"]),
            (ProviderFailure(statusCode=429, code="rate_limit_exceeded"), ERROR_CATEGORIES["RATE_LIMITED"], ERROR_CODES["PROVIDER_RATE_LIMITED"]),
            (ProviderFailure(statusCode=429, code="insufficient_quota"), ERROR_CATEGORIES["PROVIDER_QUOTA"], ERROR_CODES["PROVIDER_QUOTA_EXCEEDED"]),
            (ProviderFailure(statusCode=400, code="context_length_exceeded"), ERROR_CATEGORIES["VALIDATION"], ERROR_CODES["CONTEXT_TOO_LARGE"]),
            (ProviderFailure(statusCode=400, code="content_policy_violation"), ERROR_CATEGORIES["POLICY"], ERROR_CODES["POLICY_BLOCKED"]),
            (ProviderFailure(statusCode=404, code="model_not_found"), ERROR_CATEGORIES["MODEL_UNAVAILABLE"], ERROR_CODES["PROVIDER_VALIDATION_ERROR"]),
            (ProviderFailure(code="request_timeout"), ERROR_CATEGORIES["TIMEOUT"], ERROR_CODES["PROVIDER_UNAVAILABLE"]),
        ]

        for provider_error, expected_category, expected_code in cases:
            async def stream(_request, error=provider_error):
                raise error
                yield

            with self.subTest(provider_error=provider_error.code):
                adapter = create_openai_adapter(client=FakeClient(stream=stream), logger=CaptureLogger())

                events = [
                    event
                    async for event in adapter.stream(
                        {"credential": TEST_CREDENTIAL, "model": TEST_MODEL, "messages": TEST_MESSAGES}
                    )
                ]

                self.assertEqual(len(events), 1)
                self.assertEqual(events[0]["type"], "error")
                self.assertEqual(events[0]["error"]["category"], expected_category)
                self.assertEqual(events[0]["error"]["code"], expected_code)
                self.assertIsInstance(events[0]["error"]["message"], str)
                self.assertEqual(set(events[0]["error"].keys()), {"category", "code", "message", "dependencyStatus"})

    async def test_stream_returns_error_when_provider_stream_has_no_terminal_event(self):
        adapter = create_openai_adapter(client=FakeClient(stream=lambda _request: iter(())), logger=CaptureLogger())

        events = [
            event
            async for event in adapter.stream(
                {"credential": TEST_CREDENTIAL, "model": TEST_MODEL, "messages": TEST_MESSAGES}
            )
        ]

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "error")
        self.assertEqual(events[0]["error"]["code"], ERROR_CODES["UNKNOWN_PROVIDER_ERROR"])

    async def test_stream_returns_error_when_provider_stream_events_are_unknown(self):
        async def stream(_request):
            yield {"type": "provider.event.without_delta_or_finish"}

        adapter = create_openai_adapter(client=FakeClient(stream=stream), logger=CaptureLogger())

        events = [
            event
            async for event in adapter.stream(
                {"credential": TEST_CREDENTIAL, "model": TEST_MODEL, "messages": TEST_MESSAGES}
            )
        ]

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "error")
        self.assertEqual(events[0]["error"]["code"], ERROR_CODES["UNKNOWN_PROVIDER_ERROR"])


if __name__ == "__main__":
    unittest.main()
