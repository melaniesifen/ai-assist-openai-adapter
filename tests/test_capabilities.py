import unittest

from ai_assist_openai_adapter import PROVIDER, create_openai_adapter
from common import FakeClient


class OpenAiCapabilitiesTest(unittest.TestCase):
    def test_exposes_provider_capability_metadata_without_default_model(self):
        adapter = create_openai_adapter(client=FakeClient())

        self.assertEqual(adapter.provider, PROVIDER)
        self.assertEqual(adapter.get_capabilities()["provider"], PROVIDER)
        self.assertTrue(adapter.get_capabilities()["supportsStreaming"])
        self.assertFalse(adapter.get_capabilities()["supportsToolCalls"])
        self.assertFalse(adapter.get_capabilities()["supportsStructuredOutput"])
        self.assertIsNone(adapter.get_capabilities()["defaultModel"])


if __name__ == "__main__":
    unittest.main()
