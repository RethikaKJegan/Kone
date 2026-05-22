from __future__ import annotations

import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any


class ResourceMonitor:
    def __init__(self, out_path: str | Path, interval_s: float = 1.0) -> None:
        self.out_path = Path(out_path)
        self.interval_s = max(0.25, float(interval_s))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._start = 0.0
        self._samples: list[dict[str, Any]] = []

    def __enter__(self) -> "ResourceMonitor":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    def start(self) -> None:
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        self._start = time.time()
        self._samples.clear()
        self._thread = threading.Thread(target=self._run, name="pipeline-resource-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval_s * 2)
        self._write_summary()

    def mark(self, label: str) -> None:
        self._samples.append({"t": time.time() - self._start, "event": label})

    def _run(self) -> None:
        while not self._stop.is_set():
            sample = {"t": round(time.time() - self._start, 3)}
            sample.update(_system_usage())
            self._samples.append(sample)
            self._stop.wait(self.interval_s)

    def _write_summary(self) -> None:
        usage = [s for s in self._samples if "event" not in s]
        events = [s for s in self._samples if "event" in s]
        lines = [
            "Elevator mod pipeline resource log",
            f"pid={os.getpid()}",
            f"duration_s={time.time() - self._start:.2f}",
            f"samples={len(usage)}",
            "",
            "Summary",
        ]
        for key, label in [
            ("cpu_percent", "CPU %"),
            ("ram_used_gb", "RAM used GB"),
            ("process_ram_gb", "Process RAM GB"),
            ("vram_used_gb", "VRAM used GB"),
            ("gpu_util_percent", "GPU util %"),
        ]:
            values = [float(s[key]) for s in usage if s.get(key) is not None]
            if values:
                lines.append(f"{label}: min={min(values):.2f} avg={sum(values) / len(values):.2f} max={max(values):.2f}")
        if events:
            lines.extend(["", "Events"])
            lines.extend(f"{event['t']:.2f}s {event['event']}" for event in events)
        lines.extend(["", "Samples CSV", "t_s,cpu_percent,ram_used_gb,ram_total_gb,process_ram_gb,vram_used_gb,vram_total_gb,gpu_util_percent"])
        for s in usage:
            lines.append(",".join(str(s.get(k, "")) for k in ["t", "cpu_percent", "ram_used_gb", "ram_total_gb", "process_ram_gb", "vram_used_gb", "vram_total_gb", "gpu_util_percent"]))
        self.out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _system_usage() -> dict[str, Any]:
    data: dict[str, Any] = {
        "cpu_percent": None,
        "ram_used_gb": None,
        "ram_total_gb": None,
        "process_ram_gb": None,
        "vram_used_gb": None,
        "vram_total_gb": None,
        "gpu_util_percent": None,
    }
    try:
        import psutil

        vm = psutil.virtual_memory()
        proc = psutil.Process(os.getpid())
        data.update(
            {
                "cpu_percent": round(psutil.cpu_percent(interval=None), 2),
                "ram_used_gb": round((vm.total - vm.available) / (1024**3), 3),
                "ram_total_gb": round(vm.total / (1024**3), 3),
                "process_ram_gb": round(proc.memory_info().rss / (1024**3), 3),
            }
        )
    except Exception:
        pass
    data.update(_gpu_usage())
    return data


def _gpu_usage() -> dict[str, Any]:
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=memory.used,memory.total,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
        first = out.strip().splitlines()[0]
        used, total, util = [float(part.strip()) for part in first.split(",")]
        return {
            "vram_used_gb": round(used / 1024, 3),
            "vram_total_gb": round(total / 1024, 3),
            "gpu_util_percent": round(util, 2),
        }
    except Exception:
        pass
    try:
        import torch

        if torch.cuda.is_available():
            free, total = torch.cuda.mem_get_info()
            used = total - free
            return {
                "vram_used_gb": round(used / (1024**3), 3),
                "vram_total_gb": round(total / (1024**3), 3),
                "gpu_util_percent": None,
            }
    except Exception:
        pass
    return {"vram_used_gb": None, "vram_total_gb": None, "gpu_util_percent": None}
