import contextlib
import io
import unittest

from ai_assist_openai_adapter import ERROR_CATEGORIES, ERROR_CODES, PROVIDER, create_openai_adapter, sanitize_log_fields
from common import (
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


class OpenAiAdapterTest(unittest.IsolatedAsyncioTestCase):
    def test_exposes_provider_capability_metadata_without_default_model(self):
        adapter = create_openai_adapter(client=FakeClient())

        self.assertEqual(adapter.provider, PROVIDER)
        self.assertEqual(adapter.get_capabilities()["provider"], PROVIDER)
        self.assertTrue(adapter.get_capabilities()["supportsStreaming"])
        self.assertFalse(adapter.get_capabilities()["supportsToolCalls"])
        self.assertFalse(adapter.get_capabilities()["supportsStructuredOutput"])
        self.assertIsNone(adapter.get_capabilities()["defaultModel"])

    async def test_validate_credential_rejects_missing_credentials_without_calling_client(self):
        client = FakeClient()
        logger = CaptureLogger()
        adapter = create_openai_adapter(client=client, logger=logger)

        result = await adapter.validate_credential({"credential": "   ", "requestId": "req-1"})

        self.assertEqual(client.validate_credential_calls, 0)
        self.assertFalse(result["valid"])
        self.assertEqual(result["error"]["code"], ERROR_CODES["MISSING_CREDENTIAL"])

    async def test_validate_credential_normalizes_injected_provider_auth_failure(self):
        async def validate_credential(_request):
            raise ProviderFailure(statusCode=401, code="invalid_api_key")

        adapter = create_openai_adapter(
            client=FakeClient(validate_credential=validate_credential),
            logger=CaptureLogger(),
        )

        result = await adapter.validate_credential({"credential": TEST_CREDENTIAL})

        self.assertFalse(result["valid"])
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["error"]["code"], ERROR_CODES["INVALID_CREDENTIAL"])

    async def test_validate_credential_fails_closed_for_ambiguous_client_results(self):
        async def validate_credential(_request):
            return {}

        adapter = create_openai_adapter(
            client=FakeClient(validate_credential=validate_credential),
            logger=CaptureLogger(),
        )

        result = await adapter.validate_credential({"credential": TEST_CREDENTIAL})

        self.assertFalse(result["valid"])
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["error"]["code"], ERROR_CODES["INVALID_CREDENTIAL"])

    async def test_generate_maps_provider_neutral_request_to_openai_style_client_request(self):
        observed = {}
        logger = CaptureLogger()

        async def generate(request):
            observed.update(request)
            return {
                "model": request["model"],
                "output_text": "normalized answer",
                "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
                "finish_reason": "stop",
            }

        adapter = create_openai_adapter(client=FakeClient(generate=generate), logger=logger)

        result = await adapter.generate(
            {
                "credential": TEST_CREDENTIAL,
                "model": TEST_MODEL,
                "messages": TEST_MESSAGES,
                "maxOutputTokens": 128,
                "requestId": "req-2",
                "correlationId": "corr-2",
            }
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"]["content"], "normalized answer")
        self.assertEqual(result["usage"], {"inputTokens": 7, "outputTokens": 3, "totalTokens": 10})
        self.assertEqual(observed["max_output_tokens"], 128)
        self.assertFalse(observed["stream"])
        self.assertIs(observed["messages"], TEST_MESSAGES)
        assert_no_forbidden_log_material(self, logger.entries)

    async def test_generate_succeeds_with_default_safe_logger_and_usage_metadata(self):
        async def generate(_request):
            return {
                "output_text": "normalized answer",
                "usage": {"inputTokens": 1, "outputTokens": 2, "totalTokens": 3},
            }

        adapter = create_openai_adapter(client=FakeClient(generate=generate))

        with contextlib.redirect_stdout(io.StringIO()):
            result = await adapter.generate(
                {
                    "credential": TEST_CREDENTIAL,
                    "model": TEST_MODEL,
                    "messages": TEST_MESSAGES,
                }
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["usage"], {"inputTokens": 1, "outputTokens": 2, "totalTokens": 3})

    async def test_logger_failures_are_not_mapped_to_provider_errors(self):
        class FailingLogger:
            def info(self, _fields):
                raise TypeError("logger failed")

            def warn(self, _fields):
                raise TypeError("logger failed")

        async def generate(_request):
            return {"output_text": "normalized answer", "usage": {}}

        adapter = create_openai_adapter(client=FakeClient(generate=generate), logger=FailingLogger())

        with self.assertRaisesRegex(TypeError, "logger failed"):
            await adapter.generate(
                {
                    "credential": TEST_CREDENTIAL,
                    "model": TEST_MODEL,
                    "messages": TEST_MESSAGES,
                }
            )

    async def test_generate_returns_stable_quota_error_mapping(self):
        async def generate(_request):
            raise ProviderFailure(statusCode=429, code="insufficient_quota", message="raw provider message")

        adapter = create_openai_adapter(
            client=FakeClient(generate=generate),
            logger=CaptureLogger(),
        )

        result = await adapter.generate(
            {
                "credential": TEST_CREDENTIAL,
                "model": TEST_MODEL,
                "messages": TEST_MESSAGES,
            }
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], ERROR_CODES["PROVIDER_QUOTA_EXCEEDED"])
        self.assertEqual(result["error"]["safeMessage"], "Provider quota is exhausted.")

    async def test_generate_rejects_malformed_messages_and_parameters_before_calling_client(self):
        client = FakeClient()
        adapter = create_openai_adapter(client=client, logger=CaptureLogger())

        invalid_message = await adapter.generate(
            {
                "credential": TEST_CREDENTIAL,
                "model": TEST_MODEL,
                "messages": [{"role": "bogus", "content": "   "}],
            }
        )
        invalid_tokens = await adapter.generate(
            {
                "credential": TEST_CREDENTIAL,
                "model": TEST_MODEL,
                "messages": TEST_MESSAGES,
                "maxOutputTokens": -1,
            }
        )
        invalid_temperature = await adapter.generate(
            {
                "credential": TEST_CREDENTIAL,
                "model": TEST_MODEL,
                "messages": TEST_MESSAGES,
                "temperature": "hot",
            }
        )

        self.assertEqual(client.generate_calls, 0)
        self.assertEqual(invalid_message["error"]["code"], ERROR_CODES["INVALID_MESSAGES"])
        self.assertEqual(invalid_tokens["error"]["code"], ERROR_CODES["PROVIDER_VALIDATION_ERROR"])
        self.assertEqual(invalid_temperature["error"]["code"], ERROR_CODES["PROVIDER_VALIDATION_ERROR"])

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

    def test_sanitize_log_fields_rejects_secret_and_prompt_bearing_fields(self):
        with self.assertRaisesRegex(TypeError, "Forbidden log field"):
            sanitize_log_fields({"requestId": "req", "credential": TEST_CREDENTIAL})
        with self.assertRaisesRegex(TypeError, "Forbidden log field"):
            sanitize_log_fields({"requestId": "req", "nested": {"prompt": "do not log"}})

        self.assertEqual(
            sanitize_log_fields({"requestId": "req", "ignored": "value", "provider": PROVIDER}),
            {"requestId": "req", "provider": PROVIDER},
        )

    def test_sanitize_log_fields_allows_normalized_token_usage(self):
        self.assertEqual(
            sanitize_log_fields(
                {
                    "requestId": "req",
                    "tokenUsage": {"inputTokens": 1, "outputTokens": 2, "totalTokens": 3},
                }
            ),
            {
                "requestId": "req",
                "tokenUsage": {"inputTokens": 1, "outputTokens": 2, "totalTokens": 3},
            },
        )


if __name__ == "__main__":
    unittest.main()
