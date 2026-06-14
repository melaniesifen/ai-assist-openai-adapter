import contextlib
import io
import unittest

from ai_assist_openai_adapter import ERROR_CODES, create_openai_adapter
from tests.common import (
    CaptureLogger,
    FakeClient,
    ProviderFailure,
    TEST_CREDENTIAL,
    TEST_MESSAGES,
    TEST_MODEL,
    assert_no_forbidden_log_material,
)


class OpenAiGenerateTest(unittest.IsolatedAsyncioTestCase):
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


if __name__ == "__main__":
    unittest.main()
