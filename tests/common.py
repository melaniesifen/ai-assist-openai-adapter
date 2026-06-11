import json


TEST_CREDENTIAL = "sk-test-redacted"
TEST_MODEL = "test-openai-model"
TEST_MESSAGES = [{"role": "user", "content": "raw prompt stays out of logs"}]

PROVIDER_NEUTRAL_DELTA_FIELDS = {"type", "provider", "model", "delta"}
PROVIDER_NEUTRAL_FINAL_FIELDS = {"type", "provider", "model", "finishReason", "usage"}
PROVIDER_NEUTRAL_ERROR_FIELDS = {"type", "provider", "model", "error"}


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
