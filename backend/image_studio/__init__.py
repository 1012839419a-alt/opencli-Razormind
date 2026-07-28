"""Private image-generation integration boundaries.

This package is server-only.  Public Studio APIs must expose platform asset and
job identifiers, never the InvokeAI connection details represented here.
"""

from backend.image_studio.adapter import (
    InvokeAIAdapter,
    InvokeJobBinding,
    InvokeQueueState,
)
from backend.image_studio.invoke_client import (
    ALLOWED_INVOKE_OPERATIONS,
    InvokeAIClient,
    InvokeAIClientError,
    InvokeAIConnection,
)

__all__ = [
    "ALLOWED_INVOKE_OPERATIONS",
    "InvokeAIAdapter",
    "InvokeAIClient",
    "InvokeAIClientError",
    "InvokeAIConnection",
    "InvokeJobBinding",
    "InvokeQueueState",
]
