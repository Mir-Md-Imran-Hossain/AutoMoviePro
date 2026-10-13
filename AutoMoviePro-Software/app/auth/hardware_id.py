"""AutoMovie Pro — Enterprise Hardware Identification (HWID) Engine.

Features:
1. Multi-Tier Hardware Signal Harvesting:
   - Primary: PowerShell CIM (fast, modern Windows 11/10 compatible, replaces deprecated WMIC).
   - Secondary: Windows Registry Direct Inspection (MachineGuid, CPU Identifier).
   - Tertiary: System Volume Serial Number fallback.
   - Cross-Platform: Full Linux (/etc/machine-id, /sys/class/dmi) and macOS (IOPlatformUUID) extraction.
2. Missing Signals & Virtual Machine Resilience:
   - Identifies generic OEM placeholders ("To be filled by O.E.M.", "00000000-...") and hypervisors.
   - Computes Hardware Confidence Score (0 - 100) based on signal fidelity.
3. Component Change & Similarity Recognition:
   - Differentiates between minor component upgrades (SSD/CPU change) vs. distinct machines.
   - Provides similarity score (0.0 to 1.0) to avoid locking out legitimate hardware upgraders.
4. Device Migration & Re-activation Policy:
   - Enforces single active PC licensing.
   - Governs legitimate PC migration with cooldown limits and admin override capabilities.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

GENERIC_UUIDS = {
    "",
    "none",
    "unknown",
    "to be filled by o.e.m.",
    "default string",
    "03000200-0400-0500-0006-000700080009",
    "ffffffff-ffff-ffff-ffff-ffffffffffff",
    "00000000-0000-0000-0000-000000000000",
}

GENERIC_SERIALS = {
    "",
    "none",
    "unknown",
    "to be filled by o.e.m.",
    "default string",
    "0",
    "00000000",
    "12345678",
    "system serial number",
}

_CACHED_FINGERPRINT: Optional[str] = None
_CACHED_PROFILE: Optional[HardwareProfile] = None


@dataclass
class HardwareProfile:
    """Full architectural fingerprint profile of the host machine."""
    system: str
    motherboard_uuid: str
    cpu_id: str
    disk_serial: str
    machine_guid: str
    node_name: str
    hardware_id: str
    confidence_score: int  # 0 to 100
    signals_present: List[str] = field(default_factory=list)
    missing_signals: List[str] = field(default_factory=list)
    is_virtual_machine: bool = False
    is_fallback_only: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _run_cmd_safe(cmd: List[str], timeout: int = 5) -> str:
    """Executes a subprocess safely with a hidden window on Windows and returns stdout."""
    try:
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            startupinfo=startupinfo,
        )
        if res.returncode == 0:
            lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]
            if lines:
                return lines[0]
    except Exception as exc:
        logger.debug("Command failed %s: %s", cmd, exc)
    return ""


# -----------------------------------------------------------------------------
# 1. Motherboard & BIOS UUID Extractors
# -----------------------------------------------------------------------------

def _get_windows_uuid() -> str:
    """Retrieves BIOS / Motherboard UUID with multi-tier failover (PowerShell CIM -> Baseboard -> Reg -> WMIC)."""
    # Tier 1: Modern PowerShell CIM ComputerSystemProduct UUID
    try:
        ps_cmd = [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "(Get-CimInstance -Class Win32_ComputerSystemProduct).UUID",
        ]
        val = _run_cmd_safe(ps_cmd, timeout=4)
        if val and val.lower() not in GENERIC_UUIDS:
            return val.upper()
    except Exception:
        pass

    # Tier 2: PowerShell CIM BaseBoard Serial Number
    try:
        ps_cmd = [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "(Get-CimInstance -Class Win32_BaseBoard).SerialNumber",
        ]
        val = _run_cmd_safe(ps_cmd, timeout=4)
        if val and val.lower() not in GENERIC_SERIALS:
            return val.upper()
    except Exception:
        pass

    # Tier 3: Direct Registry MachineGuid (always available, immutable per OS install)
    guid = _get_windows_machine_guid()
    if guid and guid.lower() not in GENERIC_UUIDS:
        return guid.upper()

    # Tier 4: Legacy WMIC fallback (if installed on older Windows)
    wmic_val = _run_cmd_safe(["wmic", "csproduct", "get", "uuid"], timeout=3)
    if wmic_val and wmic_val.lower() not in GENERIC_UUIDS and "uuid" not in wmic_val.lower():
        return wmic_val.upper()

    return ""


def _get_windows_machine_guid() -> str:
    """Retrieves Windows OS Cryptography MachineGuid directly from registry."""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        )
        guid, _ = winreg.QueryValueEx(key, "MachineGuid")
        winreg.CloseKey(key)
        if guid:
            return str(guid).strip()
    except Exception:
        pass
    return ""


def _get_linux_machine_id() -> str:
    """Retrieves immutable machine-id or product_uuid on Linux."""
    candidates = [
        Path("/etc/machine-id"),
        Path("/var/lib/dbus/machine-id"),
        Path("/sys/class/dmi/id/product_uuid"),
    ]
    for p in candidates:
        try:
            if p.is_file():
                content = p.read_text(encoding="utf-8").strip()
                if content and content.lower() not in GENERIC_UUIDS:
                    return content
        except Exception:
            continue
    return ""


def _get_darwin_uuid() -> str:
    """Retrieves IOPlatformUUID on macOS."""
    try:
        cmd = ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                if "IOPlatformUUID" in line:
                    parts = line.split("=")
                    if len(parts) > 1:
                        uuid_val = parts[1].replace('"', "").strip()
                        if uuid_val and uuid_val.lower() not in GENERIC_UUIDS:
                            return uuid_val
    except Exception:
        pass
    return ""


# -----------------------------------------------------------------------------
# 2. CPU Processor ID Extractors
# -----------------------------------------------------------------------------

def _get_cpu_id() -> str:
    """Retrieves CPU Processor ID or hardware identifier."""
    sys_name = platform.system()
    if sys_name == "Windows":
        # Tier 1: PowerShell CIM Win32_Processor
        try:
            ps_cmd = [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "(Get-CimInstance -Class Win32_Processor | Where-Object { $_.ProcessorId } | Select-Object -First 1).ProcessorId",
            ]
            val = _run_cmd_safe(ps_cmd, timeout=4)
            if val and val.lower() not in GENERIC_SERIALS:
                return val.upper()
        except Exception:
            pass

        # Tier 2: Registry CPU Identifier
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
                0,
                winreg.KEY_READ,
            )
            ident, _ = winreg.QueryValueEx(key, "Identifier")
            winreg.CloseKey(key)
            if ident:
                return str(ident).strip()
        except Exception:
            pass

        # Tier 3: Legacy WMIC fallback
        wmic_val = _run_cmd_safe(["wmic", "cpu", "get", "processorid"], timeout=3)
        if wmic_val and "processorid" not in wmic_val.lower():
            return wmic_val.upper()

    elif sys_name == "Linux":
        try:
            with open("/proc/cpuinfo", "r", encoding="utf-8") as f:
                for line in f:
                    if "model name" in line or "Hardware" in line or "Serial" in line:
                        parts = line.split(":")
                        if len(parts) > 1 and parts[1].strip():
                            return parts[1].strip()
        except Exception:
            pass

    return platform.processor() or "STANDARD_CPU"


# -----------------------------------------------------------------------------
# 3. System Storage / Disk Serial Extractors
# -----------------------------------------------------------------------------

def _get_disk_serial() -> str:
    """Retrieves physical system drive serial or logical volume serial number."""
    sys_name = platform.system()
    if sys_name == "Windows":
        # Tier 1: PowerShell CIM physical drive serial (skipping empty/removable/SD cards)
        try:
            ps_cmd = [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "(Get-CimInstance -Class Win32_DiskDrive | Where-Object { ! [string]::IsNullOrWhiteSpace($_.SerialNumber) } | Select-Object -First 1).SerialNumber",
            ]
            val = _run_cmd_safe(ps_cmd, timeout=4)
            if val and val.lower() not in GENERIC_SERIALS:
                return val.replace(".", "").replace("_", "").strip().upper()
        except Exception:
            pass

        # Tier 2: Windows System Drive C: Volume Serial Number
        try:
            ps_cmd = [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "(Get-CimInstance -Class Win32_LogicalDisk | Where-Object { $_.DeviceID -eq 'C:' }).VolumeSerialNumber",
            ]
            val = _run_cmd_safe(ps_cmd, timeout=4)
            if val and val.lower() not in GENERIC_SERIALS:
                return f"VOL_{val.upper()}"
        except Exception:
            pass

        # Tier 3: Legacy WMIC diskdrive
        wmic_val = _run_cmd_safe(["wmic", "diskdrive", "get", "serialnumber"], timeout=3)
        if wmic_val and "serialnumber" not in wmic_val.lower() and wmic_val.lower() not in GENERIC_SERIALS:
            return wmic_val.strip().upper()

    elif sys_name == "Linux":
        try:
            by_id = Path("/dev/disk/by-id")
            if by_id.is_dir():
                for p in by_id.iterdir():
                    if "wwn-" not in p.name and "part" not in p.name:
                        return p.name
        except Exception:
            pass

    return ""


# -----------------------------------------------------------------------------
# 4. Comprehensive Hardware Profile & Fingerprint Generation
# -----------------------------------------------------------------------------

def get_hardware_profile() -> HardwareProfile:
    """Inspects host machine and returns structured hardware profile with confidence scoring."""
    global _CACHED_PROFILE
    if _CACHED_PROFILE is not None:
        return _CACHED_PROFILE

    sys_name = platform.system()
    node = platform.node() or "HOST"

    # Gather primary hardware signals
    if sys_name == "Windows":
        mb_uuid = _get_windows_uuid()
        machine_guid = _get_windows_machine_guid()
    elif sys_name == "Linux":
        mb_uuid = _get_linux_machine_id()
        machine_guid = mb_uuid
    elif sys_name == "Darwin":
        mb_uuid = _get_darwin_uuid()
        machine_guid = mb_uuid
    else:
        mb_uuid = ""
        machine_guid = ""

    cpu_id = _get_cpu_id()
    disk_serial = _get_disk_serial()

    signals_present: List[str] = []
    missing_signals: List[str] = []
    confidence = 0

    if mb_uuid and mb_uuid.lower() not in GENERIC_UUIDS:
        signals_present.append("MOTHERBOARD_UUID")
        confidence += 35
    else:
        missing_signals.append("MOTHERBOARD_UUID")

    if cpu_id and cpu_id.lower() not in GENERIC_SERIALS and cpu_id != "STANDARD_CPU":
        signals_present.append("CPU_PROCESSOR_ID")
        confidence += 25
    else:
        missing_signals.append("CPU_PROCESSOR_ID")

    if disk_serial and disk_serial.lower() not in GENERIC_SERIALS:
        signals_present.append("DISK_SERIAL")
        confidence += 25
    else:
        missing_signals.append("DISK_SERIAL")

    if machine_guid and machine_guid.lower() not in GENERIC_UUIDS:
        signals_present.append("MACHINE_GUID")
        confidence += 15
    else:
        missing_signals.append("MACHINE_GUID")

    # Virtual machine / Hypervisor detection
    vm_markers = ("hyper-v", "vmware", "virtualbox", "kvm", "qemu", "vbox", "xen")
    is_vm = any(k in (mb_uuid + cpu_id + node).lower() for k in vm_markers)

    is_fallback = confidence < 40

    # Build deterministic cryptographic signature
    # Note: platform.node() is omitted from primary hash to prevent hostname renames from breaking licensing!
    components = [
        f"SYS:{sys_name}",
        f"UUID:{mb_uuid or 'NONE'}",
        f"CPU:{cpu_id or 'NONE'}",
        f"DISK:{disk_serial or 'NONE'}",
        f"GUID:{machine_guid or 'NONE'}",
    ]
    raw_sig = "|".join(components)
    hw_hash = hashlib.sha256(raw_sig.encode("utf-8")).hexdigest()
    fingerprint = f"AMP-HW-{hw_hash[:32].upper()}"

    profile = HardwareProfile(
        system=sys_name,
        motherboard_uuid=mb_uuid,
        cpu_id=cpu_id,
        disk_serial=disk_serial,
        machine_guid=machine_guid,
        node_name=node,
        hardware_id=fingerprint,
        confidence_score=confidence,
        signals_present=signals_present,
        missing_signals=missing_signals,
        is_virtual_machine=is_vm,
        is_fallback_only=is_fallback,
    )
    _CACHED_PROFILE = profile
    return profile


def get_hardware_fingerprint() -> str:
    """Generates an immutable SHA-256 hardware identifier for this computer."""
    global _CACHED_FINGERPRINT
    if _CACHED_FINGERPRINT is not None:
        return _CACHED_FINGERPRINT
    profile = get_hardware_profile()
    _CACHED_FINGERPRINT = profile.hardware_id
    return _CACHED_FINGERPRINT


# -----------------------------------------------------------------------------
# 5. Component Change Similarity & Device Migration Policy
# -----------------------------------------------------------------------------

def compute_hardware_similarity(
    profile_a: Dict[str, Any],
    profile_b: Dict[str, Any],
) -> float:
    """Calculates weighted similarity ratio (0.0 to 1.0) between two hardware profiles.

    Weights:
    - Motherboard UUID: 0.35
    - CPU ID: 0.25
    - Disk Serial: 0.25
    - Machine GUID: 0.15
    """
    total_score = 0.0

    uuid_a = str(profile_a.get("motherboard_uuid") or "").strip().upper()
    uuid_b = str(profile_b.get("motherboard_uuid") or "").strip().upper()
    if uuid_a and uuid_a == uuid_b and uuid_a.lower() not in GENERIC_UUIDS:
        total_score += 0.35

    cpu_a = str(profile_a.get("cpu_id") or "").strip().upper()
    cpu_b = str(profile_b.get("cpu_id") or "").strip().upper()
    if cpu_a and cpu_a == cpu_b and cpu_a.lower() not in GENERIC_SERIALS:
        total_score += 0.25

    disk_a = str(profile_a.get("disk_serial") or "").strip().upper()
    disk_b = str(profile_b.get("disk_serial") or "").strip().upper()
    if disk_a and disk_a == disk_b and disk_a.lower() not in GENERIC_SERIALS:
        total_score += 0.25

    guid_a = str(profile_a.get("machine_guid") or "").strip().upper()
    guid_b = str(profile_b.get("machine_guid") or "").strip().upper()
    if guid_a and guid_a == guid_b and guid_a.lower() not in GENERIC_UUIDS:
        total_score += 0.15

    return round(total_score, 2)


def evaluate_hardware_match(
    expected_hwid: str,
    current_profile: Optional[HardwareProfile] = None,
    expected_profile: Optional[Dict[str, Any]] = None,
) -> Tuple[str, float, str]:
    """Classifies the relationship between the expected HWID and current device.

    Returns:
        (status, similarity, human_message)
        status is one of:
            - "EXACT_MATCH": Identical HWID, licensed.
            - "HARDWARE_UPGRADE_RECOGNIZED": Legitimate upgrade (e.g. SSD/CPU replaced), similarity >= 0.60.
            - "DEVICE_MIGRATION_REQUIRED": Distinct machine, similarity < 0.60.
    """
    if current_profile is None:
        current_profile = get_hardware_profile()

    curr_hwid = current_profile.hardware_id.strip().upper()
    exp_hwid = expected_hwid.strip().upper()

    # 1. Exact match
    if curr_hwid == exp_hwid:
        return "EXACT_MATCH", 1.0, "Hardware fingerprint perfectly matches registered license."

    # 2. Check backward compatibility with legacy formula (which included NODE and empty disk)
    sys_name = current_profile.system
    legacy_components = [
        f"SYS:{sys_name}",
        f"UUID:{current_profile.motherboard_uuid}",
        f"CPU:{current_profile.cpu_id}",
        f"DISK:",
        f"NODE:{current_profile.node_name}",
    ]
    legacy_sig = "|".join(legacy_components)
    legacy_hwid = f"AMP-HW-{hashlib.sha256(legacy_sig.encode('utf-8')).hexdigest()[:32].upper()}"
    if exp_hwid == legacy_hwid:
        return "EXACT_MATCH", 1.0, "Matched authorized hardware via legacy backward compatibility mapping."

    # 3. Component similarity check (if expected profile metadata is available)
    if expected_profile:
        sim = compute_hardware_similarity(expected_profile, current_profile.to_dict())
        if sim >= 0.60:
            return (
                "HARDWARE_UPGRADE_RECOGNIZED",
                sim,
                f"Legitimate hardware component upgrade recognized (similarity {sim*100:.0f}%). Auto-activation permitted.",
            )
        return (
            "DEVICE_MIGRATION_REQUIRED",
            sim,
            f"Different device detected (similarity {sim*100:.0f}%). Device migration required.",
        )

    # Without expected profile breakdown, report distinct device
    return "DEVICE_MIGRATION_REQUIRED", 0.0, "Hardware ID mismatch. Device migration required."


def can_migrate_device(
    *,
    days_since_last_migration: Optional[int] = None,
    total_migrations_this_year: int = 0,
    max_migrations_per_year: int = 3,
    cooldown_days: int = 7,
    admin_override: bool = False,
) -> Tuple[bool, str]:
    """Evaluates whether this customer is eligible to migrate their license to a new PC.

    Rules:
    - Cooldown period: At least `cooldown_days` (default 7 days) must have passed since last PC migration.
    - Max quota: Customer can migrate at most `max_migrations_per_year` (default 3) per 365-day period.
    - Admin override: Bypasses all cooldown/quota constraints.
    """
    if admin_override:
        return True, "Migration authorized via Admin Override."

    if total_migrations_this_year >= max_migrations_per_year:
        return (
            False,
            f"Device migration limit exceeded ({total_migrations_this_year}/{max_migrations_per_year} this year). Contact support.",
        )

    if days_since_last_migration is not None and days_since_last_migration < cooldown_days:
        wait_days = cooldown_days - days_since_last_migration
        return (
            False,
            f"Device migration cooldown active. Please wait {wait_days} day(s) before binding a new PC.",
        )

    return True, "Device migration authorized within quota."


def verify_hardware_fingerprint(expected_hwid: Optional[str]) -> bool:
    """Validates if current machine matches an authorized HWID, supporting legacy signatures."""
    if not expected_hwid:
        return False
    status, _, _ = evaluate_hardware_match(expected_hwid)
    return status in ("EXACT_MATCH", "HARDWARE_UPGRADE_RECOGNIZED")

