"""AutoMovie Pro Authentication & Licensing Module."""
from app.auth.hardware_id import (
    HardwareProfile,
    can_migrate_device,
    compute_hardware_similarity,
    evaluate_hardware_match,
    get_hardware_fingerprint,
    get_hardware_profile,
    verify_hardware_fingerprint,
)

__all__ = [
    "HardwareProfile",
    "can_migrate_device",
    "compute_hardware_similarity",
    "evaluate_hardware_match",
    "get_hardware_fingerprint",
    "get_hardware_profile",
    "verify_hardware_fingerprint",
]

