import unittest

from ai_assist_openai_adapter import ERROR_CODES, create_openai_adapter
from tests.common import CaptureLogger, FakeClient, ProviderFailure, TEST_CREDENTIAL


class OpenAiCredentialValidationTest(unittest.IsolatedAsyncioTestCase):
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


if __name__ == "__main__":
    unittest.main()
