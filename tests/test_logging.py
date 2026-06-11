import unittest

from ai_assist_openai_adapter import PROVIDER, sanitize_log_fields
from common import TEST_CREDENTIAL


class OpenAiLoggingTest(unittest.TestCase):
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
