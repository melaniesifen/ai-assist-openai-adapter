import json
import contextlib
import io
import unittest

from ai_assist_openai_adapter import ERROR_CODES, PROVIDER, create_openai_adapter, sanitize_log_fields

TEST_CREDENTIAL = "sk-test-redacted"
TEST_MODEL = "test-openai-model"
TEST_MESSAGES = [{"role": "user", "content": "raw prompt stays out of logs"}]


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

    async def test_stream_normalizes_openai_delta_and_final_events(self):
        async def stream(_request):
            yield {"type": "response.output_text.delta", "delta": "hel"}
            yield {"choices": [{"delta": {"content": "lo"}}]}
            yield {"type": "response.completed", "response": {"usage": {"input_tokens": 2, "output_tokens": 1}}}

        adapter = create_openai_adapter(client=FakeClient(stream=stream), logger=CaptureLogger())

        events = [
            event
            async for event in adapter.stream(
                {"credential": TEST_CREDENTIAL, "model": TEST_MODEL, "messages": TEST_MESSAGES}
            )
        ]

        self.assertEqual([event["type"] for event in events], ["assistant.delta", "assistant.delta", "assistant.final"])
        self.assertEqual(events[0]["delta"], "hel")
        self.assertEqual(events[2]["usage"], {"inputTokens": 2, "outputTokens": 1, "totalTokens": 3})

    async def test_stream_returns_safe_error_event_for_provider_failure(self):
        async def stream(_request):
            raise ProviderFailure(statusCode=503, code="server_error")
            yield

        adapter = create_openai_adapter(client=FakeClient(stream=stream), logger=CaptureLogger())

        events = [
            event
            async for event in adapter.stream(
                {"credential": TEST_CREDENTIAL, "model": TEST_MODEL, "messages": TEST_MESSAGES}
            )
        ]

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "error")
        self.assertEqual(events[0]["error"]["code"], ERROR_CODES["PROVIDER_UNAVAILABLE"])
        self.assertTrue(events[0]["error"]["retryable"])

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


class FakeClient:
    def __init__(self, *, validate_credential=None, generate=None, stream=None):
        self._validate_credential = validate_credential
        self._generate = generate
        self._stream = stream
        self.validate_credential_calls = 0
        self.generate_calls = 0
        self.stream_calls = 0

    async def validate_credential(self, request):
        self.validate_credential_calls += 1
        if self._validate_credential:
            return await self._validate_credential(request)
        return {"valid": True, "status": "valid", "fingerprint": "fp-test"}

    async def generate(self, request):
        self.generate_calls += 1
        if self._generate:
            return await self._generate(request)
        return {"output_text": "ok", "usage": {}}

    def stream(self, request):
        self.stream_calls += 1
        if self._stream:
            return self._stream(request)
        return _empty_async_iter()


class ProviderFailure(Exception):
    def __init__(self, **attrs):
        super().__init__(attrs.get("message", "provider failure"))
        for key, value in attrs.items():
            setattr(self, key, value)


class CaptureLogger:
    def __init__(self):
        self.entries = []

    def info(self, fields):
        self.entries.append(fields)

    def warn(self, fields):
        self.entries.append(fields)

    def error(self, fields):
        self.entries.append(fields)


async def _empty_async_iter():
    if False:
        yield None


def assert_no_forbidden_log_material(test_case, entries):
    serialized = json.dumps(entries)
    test_case.assertNotIn(TEST_CREDENTIAL, serialized)
    test_case.assertNotIn("raw prompt stays out of logs", serialized)
    test_case.assertNotIn("normalized answer", serialized)


if __name__ == "__main__":
    unittest.main()
