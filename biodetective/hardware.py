"""Conservative Windows hardware profiling for local model recommendations."""

from __future__ import annotations

import ctypes
import os
import subprocess
from ctypes import wintypes


class _MemoryStatusEx(ctypes.Structure):
    _fields_ = [
        ("dwLength", wintypes.DWORD),
        ("dwMemoryLoad", wintypes.DWORD),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def _memory_info() -> tuple[int, int]:
    """Return (total, available) RAM in bytes, or zeros if unavailable."""
    try:
        status = _MemoryStatusEx()
        status.dwLength = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.ullTotalPhys), int(status.ullAvailPhys)
    except (AttributeError, OSError):
        pass
    return 0, 0


def _display_adapters() -> list[str]:
    """Read display adapter names using the Windows user32 API."""
    if os.name != "nt":
        return []

    class DisplayDevice(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("DeviceName", wintypes.WCHAR * 32),
            ("DeviceString", wintypes.WCHAR * 128),
            ("StateFlags", wintypes.DWORD),
            ("DeviceID", wintypes.WCHAR * 128),
            ("DeviceKey", wintypes.WCHAR * 128),
        ]

    names: list[str] = []
    try:
        index = 0
        while index < 16:
            device = DisplayDevice()
            device.cb = ctypes.sizeof(device)
            if not ctypes.windll.user32.EnumDisplayDevicesW(None, index, ctypes.byref(device), 0):
                break
            if device.DeviceString and device.DeviceString not in names:
                names.append(device.DeviceString)
            index += 1
    except (AttributeError, OSError):
        pass
    return names


def _nvidia_memory() -> tuple[str | None, int | None]:
    """Return NVIDIA GPU name and total VRAM in GiB when nvidia-smi is present."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        row = result.stdout.strip().splitlines()[0]
        name, memory_mib = [part.strip() for part in row.split(",", 1)]
        return name, max(0, int(memory_mib) // 1024)
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None, None


def model_recommendation(total_gib: float, available_gib: float, gpu_vram_gib: int | None) -> tuple[str, str]:
    """Recommend a conservative Qwen3 model tag from available hardware."""
    usable_gib = min(total_gib, max(available_gib, total_gib * 0.55)) if total_gib else 0
    if gpu_vram_gib and gpu_vram_gib >= 16 and usable_gib >= 24:
        return "qwen3:14b", "Best fit: larger local model; Ollama can use a compatible GPU."
    if gpu_vram_gib and gpu_vram_gib >= 10 and usable_gib >= 16:
        return "qwen3:8b", "Recommended: balanced quality and memory use."
    if usable_gib >= 28:
        return "qwen3:14b", "Best fit: larger local model; allow memory for Windows and context."
    if usable_gib >= 18:
        return "qwen3:8b", "Recommended: balanced quality and memory use."
    if usable_gib >= 10:
        return "qwen3:4b", "Recommended: compact model for everyday investigations."
    if usable_gib >= 6:
        return "qwen3:1.7b", "Lightweight model; scientific reasoning may be less reliable."
    return "qwen3:0.6b", "Smallest option; expect limited scientific reasoning quality."


def detect_hardware() -> dict[str, object]:
    total_bytes, available_bytes = _memory_info()
    total_gib = total_bytes / (1024**3)
    available_gib = available_bytes / (1024**3)
    gpu_name, gpu_vram = _nvidia_memory()
    adapters = _display_adapters()
    if gpu_name:
        gpu_label = f"{gpu_name} · {gpu_vram} GB VRAM"
    elif adapters:
        gpu_label = ", ".join(adapters[:2])
    else:
        gpu_label = "GPU details unavailable"
    recommendation, reason = model_recommendation(total_gib, available_gib, gpu_vram)
    return {
        "total_ram_gib": round(total_gib, 1),
        "available_ram_gib": round(available_gib, 1),
        "cpu_threads": os.cpu_count() or 0,
        "gpu": gpu_label,
        "gpu_vram_gib": gpu_vram,
        "recommended_model": recommendation,
        "recommendation_reason": reason,
    }

