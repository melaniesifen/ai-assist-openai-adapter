import unittest

from ai_assist_openai_adapter import ERROR_CATEGORIES, ERROR_CODES, provider_status, create_openai_adapter
from tests.common import CaptureLogger, FakeClient, ProviderFailure, TEST_MESSAGES, TEST_MODEL, assert_no_forbidden_log_material


class OpenAiProviderAccessTest(unittest.IsolatedAsyncioTestCase):
    async def test_generate_uses_platform_provider_access_without_user_credential(self):
        observed = {}
        logger = CaptureLogger()

        async def generate(request):
            observed.update(request)
            return {"output_text": "normalized answer", "usage": {}}

        adapter = create_openai_adapter(client=FakeClient(generate=generate), logger=logger)

        result = await adapter.generate(
            {
                "providerAccess": {"source": "platform", "reference": "secret-ref:openai-default"},
                "model": TEST_MODEL,
                "messages": TEST_MESSAGES,
            }
        )

        self.assertTrue(result["ok"])
        self.assertNotIn("credential", observed)
        self.assertEqual(observed["providerAccess"], {"source": "platform", "reference": "secret-ref:openai-default"})
        assert_no_forbidden_log_material(self, logger.entries)

    async def test_stream_uses_optional_byo_access_when_explicitly_configured(self):
        observed = {}

        async def stream(request):
            observed.update(request)
            yield {"type": "response.completed", "response": {"finish_reason": "stop", "usage": {}}}

        adapter = create_openai_adapter(client=FakeClient(stream=stream), logger=CaptureLogger())

        events = [
            event
            async for event in adapter.stream(
                {
                    "providerAccess": {"source": "byo", "credential": "sk-test-redacted", "secretRef": "secret_001"},
                    "model": TEST_MODEL,
                    "messages": TEST_MESSAGES,
                }
            )
        ]

        self.assertEqual(events[-1]["type"], "assistant.final")
        self.assertEqual(observed["credential"], "sk-test-redacted")
        self.assertEqual(observed["providerAccess"], {"source": "byo", "secretRef": "secret_001"})

    async def test_generate_rejects_missing_provider_access_without_calling_client(self):
        client = FakeClient()
        adapter = create_openai_adapter(client=client, logger=CaptureLogger())

        result = await adapter.generate({"model": TEST_MODEL, "messages": TEST_MESSAGES})

        self.assertFalse(result["ok"])
        self.assertEqual(client.generate_calls, 0)
        self.assertEqual(result["error"]["code"], ERROR_CODES["MISSING_CREDENTIAL"])

    async def test_generate_rejects_platform_access_without_secret_reference(self):
        client = FakeClient()
        logger = CaptureLogger()
        adapter = create_openai_adapter(client=client, logger=logger)

        result = await adapter.generate(
            {
                "providerAccess": {"source": "platform", "reference": "   "},
                "model": TEST_MODEL,
                "messages": TEST_MESSAGES,
                "requestId": "req-platform-missing-ref",
            }
        )

        self.assertFalse(result["ok"])
        self.assertEqual(client.generate_calls, 0)
        self.assertEqual(result["error"]["code"], ERROR_CODES["MISSING_CREDENTIAL"])
        self.assertEqual(result["error"]["safeMessage"], "Platform provider access is not configured.")
        assert_no_forbidden_log_material(self, logger.entries)

    async def test_stream_rejects_platform_access_without_secret_reference(self):
        client = FakeClient()
        adapter = create_openai_adapter(client=client, logger=CaptureLogger())

        events = [
            event
            async for event in adapter.stream(
                {
                    "providerAccess": {"source": "platform"},
                    "model": TEST_MODEL,
                    "messages": TEST_MESSAGES,
                }
            )
        ]

        self.assertEqual(client.stream_calls, 0)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "error")
        self.assertEqual(events[0]["error"]["code"], ERROR_CODES["MISSING_CREDENTIAL"])

    async def test_generate_maps_provider_access_denial_without_secret_leakage(self):
        logger = CaptureLogger()

        async def generate(_request):
            raise ProviderFailure(statusCode=403, code="secret_access_denied", message="raw provider message")

        adapter = create_openai_adapter(client=FakeClient(generate=generate), logger=logger)

        result = await adapter.generate(
            {
                "providerAccess": {"source": "platform", "reference": "secret-ref:openai-default"},
                "model": TEST_MODEL,
                "messages": TEST_MESSAGES,
            }
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["category"], ERROR_CATEGORIES["AUTHORIZATION"])
        self.assertEqual(result["error"]["code"], ERROR_CODES["PROVIDER_ACCESS_DENIED"])
        self.assertEqual(result["error"]["safeMessage"], "Provider access is not authorized.")
        assert_no_forbidden_log_material(self, logger.entries)

    async def test_stream_maps_secret_access_unavailable_without_secret_leakage(self):
        logger = CaptureLogger()

        async def stream(_request):
            raise ProviderFailure(statusCode=500, code="kms_decrypt_failed")
            yield

        adapter = create_openai_adapter(client=FakeClient(stream=stream), logger=logger)

        events = [
            event
            async for event in adapter.stream(
                {
                    "providerAccess": {"source": "platform", "reference": "secret-ref:openai-default"},
                    "model": TEST_MODEL,
                    "messages": TEST_MESSAGES,
                }
            )
        ]

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "error")
        self.assertEqual(events[0]["error"]["category"], ERROR_CATEGORIES["DEPENDENCY"])
        self.assertEqual(events[0]["error"]["code"], ERROR_CODES["PROVIDER_ACCESS_UNAVAILABLE"])
        self.assertEqual(events[0]["error"]["message"], "Provider access is temporarily unavailable.")
        assert_no_forbidden_log_material(self, logger.entries)

    def test_provider_status_is_metadata_only(self):
        status = provider_status(
            status="available",
            access_source="platform",
            configured=True,
            reason_code="CONFIGURED",
            checked_at="2026-06-14T00:00:00Z",
        )

        self.assertEqual(
            status,
            {
                "provider": "openai",
                "status": "available",
                "accessSource": "platform",
                "configured": True,
                "reasonCode": "CONFIGURED",
                "checkedAt": "2026-06-14T00:00:00Z",
            },
        )
        self.assertNotIn("credential", status)
        self.assertNotIn("secret", status)


if __name__ == "__main__":
    unittest.main()
