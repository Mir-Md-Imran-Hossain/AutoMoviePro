"""AMP-owned visual retrieval (CLIP + FAISS) — observation/candidate only."""
from pipeline.retrieval.bridge import (
    apply_retrieval_to_materialization_unit,
    attach_retrieval_evidence,
)
from pipeline.retrieval.common import (
    STATUS_NO_SUITABLE,
    STATUS_RETRIEVAL_AVAILABLE,
    STATUS_RETRIEVAL_UNAVAILABLE,
)
from pipeline.retrieval.query import build_retrieval_query
from pipeline.retrieval.retrieve import index_local_assets, retrieve_for_beat

__all__ = [
    "STATUS_RETRIEVAL_AVAILABLE",
    "STATUS_RETRIEVAL_UNAVAILABLE",
    "STATUS_NO_SUITABLE",
    "build_retrieval_query",
    "retrieve_for_beat",
    "index_local_assets",
    "attach_retrieval_evidence",
    "apply_retrieval_to_materialization_unit",
]
