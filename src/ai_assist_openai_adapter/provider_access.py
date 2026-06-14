from collections.abc import Mapping

from .constants import ERROR_CATEGORIES, ERROR_CODES, PROVIDER
from .errors import validation_error

ACCESS_SOURCE_PLATFORM = "platform"
ACCESS_SOURCE_BYO = "byo"
ACCESS_SOURCE_UNAVAILABLE = "unavailable"
ACCESS_SOURCE_VALUES = frozenset({ACCESS_SOURCE_PLATFORM, ACCESS_SOURCE_BYO})

STATUS_AVAILABLE = "available"
STATUS_UNAVAILABLE = "unavailable"
STATUS_MISCONFIGURED = "misconfigured"
STATUS_QUOTA_LIMITED = "quota_limited"
STATUS_OPTIONAL_BYO_CONFIGURED = "optional_byo_configured"
STATUS_DEFERRED = "deferred"
STATUS_VALUES = frozenset(
    {
        STATUS_AVAILABLE,
        STATUS_UNAVAILABLE,
        STATUS_MISCONFIGURED,
        STATUS_QUOTA_LIMITED,
        STATUS_OPTIONAL_BYO_CONFIGURED,
        STATUS_DEFERRED,
    }
)


def provider_access_from_request(request):
    access = request.get("providerAccess")
    if isinstance(access, Mapping):
        source = access.get("source")
        if source == ACCESS_SOURCE_PLATFORM:
            return {"source": ACCESS_SOURCE_PLATFORM, "reference": access.get("reference")}
        if source == ACCESS_SOURCE_BYO:
            credential = access.get("credential") or request.get("credential")
            if isinstance(credential, str) and credential.strip():
                return {
                    "source": ACCESS_SOURCE_BYO,
                    "credential": credential,
                    "secretRef": access.get("secretRef") or request.get("secretRef"),
                }
            return {"source": ACCESS_SOURCE_BYO, "error": validation_error(ERROR_CODES["MISSING_CREDENTIAL"], "Provider credential is required.")}
        return {"source": ACCESS_SOURCE_UNAVAILABLE, "error": _invalid_access_source_error()}

    credential = request.get("credential")
    if isinstance(credential, str) and credential.strip():
        return {"source": ACCESS_SOURCE_BYO, "credential": credential, "secretRef": request.get("secretRef")}

    return {"source": ACCESS_SOURCE_UNAVAILABLE, "error": validation_error(ERROR_CODES["MISSING_CREDENTIAL"], "Provider access is required.")}


def provider_access_error(access):
    error = access.get("error") if isinstance(access, Mapping) else None
    return error if isinstance(error, Mapping) else None


def to_client_access_fields(access):
    source = access.get("source") if isinstance(access, Mapping) else None
    if source == ACCESS_SOURCE_PLATFORM:
        return {
            "providerAccess": {
                "source": ACCESS_SOURCE_PLATFORM,
                "reference": access.get("reference"),
            }
        }
    if source == ACCESS_SOURCE_BYO:
        return {
            "credential": access.get("credential"),
            "providerAccess": {
                "source": ACCESS_SOURCE_BYO,
                "secretRef": access.get("secretRef"),
            },
        }
    return {}


def provider_status(*, status=STATUS_UNAVAILABLE, access_source=ACCESS_SOURCE_PLATFORM, configured=False, reason_code=None, checked_at=None):
    if status not in STATUS_VALUES:
        raise ValueError("Unsupported provider status.")
    if access_source not in ACCESS_SOURCE_VALUES and access_source != ACCESS_SOURCE_UNAVAILABLE:
        raise ValueError("Unsupported provider access source.")
    return {
        "provider": PROVIDER,
        "status": status,
        "accessSource": access_source,
        "configured": bool(configured),
        "reasonCode": reason_code,
        "checkedAt": checked_at,
    }


def _invalid_access_source_error():
    return {
        "provider": PROVIDER,
        "category": ERROR_CATEGORIES["VALIDATION"],
        "code": ERROR_CODES["PROVIDER_VALIDATION_ERROR"],
        "retryable": False,
        "message": "Provider access source is not supported.",
        "safeMessage": "Provider access source is not supported.",
    }
