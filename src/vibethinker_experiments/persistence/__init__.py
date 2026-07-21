"""结果持久化与发布合同。"""

from .core import (
    CallbackPublisher,
    PublicationResult,
    PublishAdapter,
    build_artifact_manifest,
    canonical_json,
    publish_results,
    verify_artifact_manifest,
    write_artifact_manifest,
)

__all__ = [
    "CallbackPublisher",
    "PublicationResult",
    "PublishAdapter",
    "build_artifact_manifest",
    "canonical_json",
    "publish_results",
    "verify_artifact_manifest",
    "write_artifact_manifest",
]
