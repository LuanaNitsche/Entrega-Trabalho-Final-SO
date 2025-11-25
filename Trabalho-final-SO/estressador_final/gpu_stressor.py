from __future__ import annotations

"""
Módulo de estresse de GPU para o StressLab.

Usa OpenCL (pyopencl) para gerar carga na GPU e nvidia-smi
para limitar por temperatura, se disponível.
"""

import threading
import time
import subprocess
from typing import Optional, Dict, Any

try:
    import pyopencl as cl
    import numpy as np
except ImportError as e:
    raise ImportError(
        "Este módulo requer pyopencl e numpy instalados. "
        "Instale com: pip install pyopencl numpy"
    ) from e

KERNEL_SOURCE = """
__kernel void burn(__global float *a, int iterations) {
    int gid = get_global_id(0);
    float x = (float)(gid + 1);
    for (int i = 0; i < iterations; i++) {
        x = x * 1.000001f + 0.000001f;
        x = x * x + 1.0f;
    }
    a[gid] = x;
}
"""

WORK_ITEMS_PER_CU = 65536
STRESS_PROFILES: dict[str, dict[str, int]] = {
    "leve": {
        "iterations": 50_000,
        "work_items_factor": 1,
    },
    "medio": {
        "iterations": 200_000,
        "work_items_factor": 1,
    },
    "pesado": {
        "iterations": 400_000,
        "work_items_factor": 2,
    },
}


def get_gpu_specs() -> tuple[Dict[str, Any], "cl.Device"]:
    """Descobre a primeira GPU OpenCL disponível e retorna infos + device."""
    platforms = cl.get_platforms()
    if not platforms:
        raise RuntimeError("Nenhuma plataforma OpenCL encontrada.")

    device: Optional["cl.Device"] = None
    for plat in platforms:
        devices = plat.get_devices(device_type=cl.device_type.GPU)
        if devices:
            device = devices[0]
            break

    if device is None:
        raise RuntimeError("Nenhuma GPU OpenCL encontrada.")

    info: Dict[str, Any] = {
        "name": device.name.strip(),
        "vendor": device.vendor.strip(),
        "compute_units": device.max_compute_units,
        "max_clock_mhz": device.max_clock_frequency,
        "global_mem_mb": device.global_mem_size // (1024 * 1024),
    }
    return info, device


def get_gpu_temp() -> Optional[int]:
    """Temperatura da GPU via nvidia-smi (em °C), ou None se indisponível."""
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            encoding="utf-8",
            stderr=subprocess.DEVNULL,
        )
        line = out.splitlines()[0].strip()
        return int(line)
    except Exception:
        return None


def get_gpu_util() -> Optional[int]:
    """Utilização da GPU (%) via nvidia-smi, ou None se indisponível."""
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu",
            "--format=csv,noheader,nounits",
            ],
            encoding="utf-8",
            stderr=subprocess.DEVNULL,
        )
        line = out.splitlines()[0].strip()
        return int(line)
    except Exception:
        return None


class GPUStressor:
    """Classe que gera carga na GPU usando OpenCL em um thread separado."""

    def __init__(self) -> None:
        info, device = get_gpu_specs()
        self.info = info
        self.device = device

        self.ctx = cl.Context(devices=[device])
        self.queue = cl.CommandQueue(
            self.ctx,
            properties=cl.command_queue_properties.PROFILING_ENABLE
        )
        self.program = cl.Program(self.ctx, KERNEL_SOURCE).build()

        self.running: bool = False
        self._thread: Optional[threading.Thread] = None
        self.history: list[dict[str, float]] = []
        self.profile: str = "medio"


    def start(
        self,
        duration_s: float,
        max_temp: Optional[int],
        active_units: Optional[int] = None,
        profile: str = "medio",
    ) -> None:
        """Inicia o estresse de GPU.

        duration_s: tempo máximo de execução (maior que 0)
        max_temp: temperatura máxima em °C (None = ignora)
        active_units: número de compute units lógicos a usar
        """
        if self.running:
            return

        if active_units is None or active_units <= 0:
            active_units = self.info["compute_units"]

        active_units = max(1, min(active_units, self.info["compute_units"]))

        profile = profile.lower()
        if profile not in STRESS_PROFILES:
            profile = "medio"
        
        self.profile = profile
        
        self.running = True
        self._thread = threading.Thread(
            target=self._stress_loop,
            args=(float(duration_s), max_temp, active_units, profile),
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Pede para parar o estresse."""
        self.running = False

    def _stress_loop(
        self,
        duration_s: float,
        max_temp: Optional[int],
        active_units: int,
        profile:str
    ) -> None:
        
        preset = STRESS_PROFILES.get(profile, STRESS_PROFILES["medio"])
        work_items_factor = preset["work_items_factor"]
        iterations_value = preset["iterations"]

        work_items = active_units * WORK_ITEMS_PER_CU * work_items_factor
        iterations = np.int32(iterations_value)

        a = np.empty(work_items, dtype=np.float32)
        buf = cl.Buffer(self.ctx, cl.mem_flags.WRITE_ONLY, a.nbytes)

        self.history.clear()
        start = time.time()

        try:
            while self.running:
                now = time.time()
                if duration_s > 0 and (now - start) >= duration_s:
                    break

                if max_temp is not None:
                    t = get_gpu_temp()
                    if t is not None and t >= max_temp:
                        print(f"[GPUStressor] Parando: temperatura {t}°C >= {max_temp}°C")
                        break

                evt = self.program.burn(
                    self.queue,
                    (work_items,),
                    None,
                    buf,
                    iterations,
                )
                evt.wait()

                elapsed = time.time() - start
                temp = get_gpu_temp()
                util = get_gpu_util()

                self.history.append({
                    "t": elapsed,
                    "temp": float(temp) if temp is not None else float("nan"),
                    "util": float(util) if util is not None else float("nan"),
                })

        except Exception as e:
            print("[GPUStressor] Erro no loop:", e)
        finally:
            self.running = False
            print("[GPUStressor] Loop de estresse finalizado.")
    
    def benchmark_once(
        self,
        profile: str = "medio",
        active_units: Optional[int] = None,
    ) -> dict[str, float]:
        """Roda o kernel uma vez e calcula throughput em GFLOPs baseado no perfil."""

        profile = profile.lower()
        if profile not in STRESS_PROFILES:
            profile = "medio"

        preset = STRESS_PROFILES[profile]
        iterations = preset["iterations"]
        work_items_factor = preset["work_items_factor"]

        if active_units is None or active_units <= 0:
            active_units = self.info["compute_units"]

        active_units = max(1, min(active_units, self.info["compute_units"]))

        work_items = active_units * WORK_ITEMS_PER_CU * work_items_factor

        iterations32 = np.int32(iterations)

        a = np.empty(work_items, dtype=np.float32)
        buf = cl.Buffer(self.ctx, cl.mem_flags.WRITE_ONLY, a.nbytes)

        evt = self.program.burn(
            self.queue,
            (work_items,),
            None,
            buf,
            iterations32,
        )
        evt.wait()

        elapsed_ns = evt.profile.end - evt.profile.start
        elapsed_s = elapsed_ns / 1e9

        flops_per_iter = 4
        total_flops = work_items * iterations * flops_per_iter
        gflops = (total_flops / 1e9) / elapsed_s

        return {
            "elapsed_s": elapsed_s,
            "gflops": gflops,
            "work_items": float(work_items),
            "iterations": float(iterations),
        }


    def summary(self) -> dict[str, Any]:
        """Resumo simples da última execução."""
        if not self.history:
            return {}

        temps = [h["temp"] for h in self.history if not np.isnan(h["temp"])]
        utils = [h["util"] for h in self.history if not np.isnan(h["util"])]

        def _stats(xs):
            if not xs:
                return {"min": float("nan"), "max": float("nan"), "avg": float("nan")}
            return {
                "min": float(np.min(xs)),
                "max": float(np.max(xs)),
                "avg": float(np.mean(xs)),
            }

        return {
            "temp": _stats(temps),
            "util": _stats(utils),
            "duration_s": self.history[-1]["t"],
        }
