"""interface estressador de cpu e gpu"""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import subprocess
import time
import psutil
import shutil
import platform
from typing import Optional
import math
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

try:
    from gpu_stressor import GPUStressor, get_gpu_temp, get_gpu_util
    GPU_BACKEND_AVAILABLE = True
except Exception:
    GPUStressor = None
    GPU_BACKEND_AVAILABLE = False

    def get_gpu_temp() -> Optional[int]:
        return None

    def get_gpu_util() -> Optional[int]:
        return None


class StressGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("StressLab - CPU/GPU Stress Tester")

        self.mode = tk.StringVar(value="cpu")
        self.cpu_cores_var = tk.IntVar(value=max(1, psutil.cpu_count(logical=True) or 1))
        self.duration_var = tk.IntVar(value=30)
        self.temp_limit_var = tk.IntVar(value=85)
        self.progress_var = tk.IntVar(value=0)
        self.profile_var = tk.StringVar(value="medio")

        self.process: Optional[subprocess.Popen] = None
        self.gpu_stressor: Optional[GPUStressor] = GPUStressor() if GPU_BACKEND_AVAILABLE else None

        self.running = False
        self.start_time: float = 0.0
        self.current_duration: int = 0

        self._build_ui()
        self._on_mode_change()
        self._update_system_info()

        self.sample_history: list[dict] = []


    def _build_ui(self) -> None:
        mode_frame = ttk.LabelFrame(self.root, text="Modo de estresse")
        mode_frame.pack(fill="x", padx=10, pady=5)

        ttk.Radiobutton(
            mode_frame, text="CPU", variable=self.mode, value="cpu",
            command=self._on_mode_change
        ).pack(side="left", padx=5, pady=5)

        self.gpu_radio = ttk.Radiobutton(
            mode_frame, text="GPU", variable=self.mode, value="gpu",
            command=self._on_mode_change
        )
        self.gpu_radio.pack(side="left", padx=5, pady=5)
        if not GPU_BACKEND_AVAILABLE:
            self.gpu_radio.config(state="disabled")

        params_frame = ttk.LabelFrame(self.root, text="Parâmetros")
        params_frame.pack(fill="x", padx=10, pady=5)

        self.cores_label = ttk.Label(params_frame, text="Núcleos CPU a estressar:")
        self.cores_label.grid(row=0, column=0, sticky="w", padx=5, pady=2)

        max_cores = psutil.cpu_count(logical=True) or 1
        self.cores_spin = ttk.Spinbox(
            params_frame, from_=1, to=max_cores,
            textvariable=self.cpu_cores_var, width=5
        )
        self.cores_spin.grid(row=0, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(params_frame, text="Tempo limite (s):").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.duration_entry = ttk.Entry(params_frame, textvariable=self.duration_var, width=7)
        self.duration_entry.grid(row=1, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(params_frame, text="Temperatura limite (°C):").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        self.temp_entry = ttk.Entry(params_frame, textvariable=self.temp_limit_var, width=7)
        self.temp_entry.grid(row=2, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(params_frame, text="Perfil de estresse:").grid(row=3, column=0, sticky="w", padx=5, pady=2)
        self.profile_combo = ttk.Combobox(
            params_frame,
            textvariable=self.profile_var,
            values=("leve", "medio", "pesado"),
            state="readonly",
            width=10,
        )
        self.profile_combo.grid(row=3, column=1, sticky="w", padx=5, pady=2)
        self.profile_combo.current(1)

        info_frame = ttk.LabelFrame(self.root, text="Informações do sistema")
        info_frame.pack(fill="x", padx=10, pady=5)

        self.cpu_info_label = ttk.Label(info_frame, text="CPU: -")
        self.cpu_info_label.pack(anchor="w", padx=5, pady=2)

        self.gpu_info_label = ttk.Label(info_frame, text="GPU: -")
        self.gpu_info_label.pack(anchor="w", padx=5, pady=2)

        self.runtime_label = ttk.Label(
            info_frame,
            text="Uso CPU: - | Temp CPU: - | GPU Util: - | Temp GPU: -",
        )
        self.runtime_label.pack(anchor="w", padx=5, pady=2)

        progress_frame = ttk.LabelFrame(self.root, text="Execução")
        progress_frame.pack(fill="x", padx=10, pady=5)

        self.progress = ttk.Progressbar(
            progress_frame, orient="horizontal", mode="determinate",
            variable=self.progress_var, maximum=self.duration_var.get()
        )
        self.progress.pack(fill="x", padx=5, pady=5)

        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill="x", padx=10, pady=5)

        self.start_btn = ttk.Button(btn_frame, text="Iniciar estresse", command=self.start_stress)
        self.start_btn.pack(side="left", padx=5)

        self.stop_btn = ttk.Button(btn_frame, text="Parar", command=self.stop_stress, state="disabled")
        self.stop_btn.pack(side="left", padx=5)

        self.benchmark_btn = ttk.Button(btn_frame, text="Benchmark GPU", command=self.run_gpu_benchmark)
        self.benchmark_btn.pack(side="left", padx=5)
        if not GPU_BACKEND_AVAILABLE:
            self.benchmark_btn.config(state="disabled")

        self.show_graph_btn = ttk.Button(btn_frame, text="Mostrar gráfico", command=self.show_graph)
        self.show_graph_btn.pack(side="left", padx=5)

    def show_graph(self) -> None:
        if not self.sample_history:
            messagebox.showinfo("Sem dados", "Nenhuma amostra disponível para plotar.")
            return

        win = tk.Toplevel(self.root)
        win.title("Gráfico de comparação - uso e temperatura")
        win.geometry("900x600")

        fig = Figure(figsize=(9, 6), dpi=100)

        ts = [s["t"] for s in self.sample_history]
        cpu_vals = [s["cpu"] for s in self.sample_history]
        gpu_vals = [s["gpu"] for s in self.sample_history]
        cpu_temps = [s["cpu_temp"] for s in self.sample_history]
        gpu_temps = [s["gpu_temp"] for s in self.sample_history]

        ax1 = fig.add_subplot(211)
        ax1.plot(ts, cpu_vals, label="CPU %", marker=None)
        ax1.plot(ts, gpu_vals, label="GPU %", marker=None)
        ax1.set_ylabel("Uso (%)")
        ax1.set_xlabel("Tempo (s)")
        ax1.grid(True, linestyle="--", alpha=0.4)
        ax1.legend(loc="upper right")

        ax2 = fig.add_subplot(212)
        def sanitize(xs):
            return [x if (x is not None and not math.isnan(x)) else float("nan") for x in xs]

        ax2.plot(ts, sanitize(cpu_temps), label="Temp CPU (°C)")
        ax2.plot(ts, sanitize(gpu_temps), label="Temp GPU (°C)")
        ax2.set_ylabel("Temperatura (°C)")
        ax2.set_xlabel("Tempo (s)")
        ax2.grid(True, linestyle="--", alpha=0.4)
        ax2.legend(loc="upper right")

        canvas = FigureCanvasTkAgg(fig, master=win)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=1)

        toolbar = NavigationToolbar2Tk(canvas, win)
        toolbar.update()
        canvas._tkcanvas.pack(fill="both", expand=1)
        
    def _update_system_info(self) -> None:
        try:
            cpu_name = platform.processor() or "Desconhecida"
        except Exception:
            cpu_name = "Desconhecida"

        cores_physical = psutil.cpu_count(logical=False) or "?"
        cores_logical = psutil.cpu_count(logical=True) or "?"
        freq = psutil.cpu_freq()
        if freq:
            freq_str = f"{freq.current/1000:.2f} GHz"
        else:
            freq_str = "N/D"

        self.cpu_info_label.config(
            text=f"CPU: {cpu_name} | Físicos: {cores_physical} | "
                 f"Lógicos: {cores_logical} | Freq: {freq_str}"
        )

        gpu_text = "GPU: não encontrada / nvidia-smi indisponível"
        if shutil.which("nvidia-smi"):
            try:
                out = subprocess.check_output(
                    ["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
                     "--format=csv,noheader"],
                    stderr=subprocess.STDOUT,
                    text=True
                ).strip()
                if out:
                    name, mem, driver = [x.strip() for x in out.split(",")]
                    gpu_text = f"GPU: {name} | Mem: {mem} | Driver: {driver}"
            except Exception as e:
                gpu_text = f"GPU: erro ao consultar ({e})"

        self.gpu_info_label.config(text=gpu_text)


    def _on_mode_change(self) -> None:
        """Ajusta campos dependendo se é CPU ou GPU"""
        mode = self.mode.get()
        if mode == "cpu":
            self.cores_label.config(text="Núcleos CPU a estressar:")
            max_cores = psutil.cpu_count(logical=True) or 1
            self.cores_spin.config(state="normal", from_=1, to=max_cores)
            if self.cpu_cores_var.get() > max_cores:
                self.cpu_cores_var.set(max_cores)
            self.temp_entry.config(state="normal")
        else:
            self.cores_label.config(text="Compute units da GPU a usar:")
            if self.gpu_stressor is not None:
                cu = self.gpu_stressor.info["compute_units"]
                self.cores_spin.config(state="normal", from_=1, to=cu)
                if self.cpu_cores_var.get() > cu:
                    self.cpu_cores_var.set(cu)
            else:
                self.cores_spin.config(state="disabled")
            self.temp_entry.config(state="normal")


    def start_stress(self) -> None:
        if self.running:
            return

        self.sample_history.clear()
        duration = self.duration_var.get()
        if duration <= 0:
            messagebox.showerror("Erro", "Tempo limite deve ser maior que 0.")
            return

        temp_limit = self.temp_limit_var.get()
        if temp_limit <= 0:
            messagebox.showerror("Erro", "Temperatura limite deve ser maior que 0.")
            return

        mode = self.mode.get()
        self.process = None

        if mode == "cpu":
            cores = self.cpu_cores_var.get()
            if cores <= 0:
                messagebox.showerror("Erro", "Número de núcleos inválido.")
                return

            base_dir = Path(__file__).resolve().parent
            cpu_exe = base_dir / "cpu_stress.exe"

            if not cpu_exe.exists():
                messagebox.showerror(
                    "Erro",
                    f"Binário {cpu_exe.name} não encontrado na mesma pasta do stress_gui.py."
                )
                return

            cmd = [str(cpu_exe), str(duration), str(cores)]
            self.process = subprocess.Popen(cmd)

        else:
            if self.gpu_stressor is None:
                messagebox.showerror(
                    "GPU indisponível",
                    "Backend de GPU não está disponível (pyopencl/gpu_stressor ausente).",
                )
                return
            units = self.cpu_cores_var.get()
            if units <= 0:
                units = None

            profile = self.profile_var.get()

            self.gpu_stressor.start(
                duration_s=float(duration),
                max_temp=temp_limit,
                active_units=units,
                profile=profile
            )

        self.running = True
        self.start_time = time.time()
        self.current_duration = duration
        self.progress.config(maximum=duration)
        self.progress_var.set(0)

        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")

        t = threading.Thread(target=self._monitor_loop, daemon=True)
        t.start()

    def stop_stress(self) -> None:
        if not self.running:
            return

        mode = self.mode.get()
        self.running = False

        if mode == "cpu":
            if self.process and self.process.poll() is None:
                try:
                    self.process.terminate()
                    self.process.wait(timeout=3)
                except Exception:
                    try:
                        self.process.kill()
                    except Exception:
                        pass
        else:  
            if self.gpu_stressor is not None:
                self.gpu_stressor.stop()

        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.progress_var.set(0)
        self.runtime_label.config(
            text="Uso CPU: - | Temp CPU: - | GPU Util: - | Temp GPU: -"
        )

    def run_gpu_benchmark(self) -> None:
            """Roda um benchmark rápido na GPU e mostra GFLOPs estimados."""
            if self.gpu_stressor is None:
                messagebox.showerror(
                    "GPU indisponível",
                    "Backend de GPU não está disponível (pyopencl/gpu_stressor ausente).",
                )
                return

            try:
                profile = self.profile_var.get()
                active_units = self.cpu_cores_var.get()
                result = self.gpu_stressor.benchmark_once(profile=profile, active_units=active_units)
            except Exception as e:
                messagebox.showerror(
                    "Erro no benchmark",
                    f"Ocorreu um erro ao executar o benchmark da GPU:\n{e}",
                )
                return

            name = self.gpu_stressor.info.get("name", "Desconhecida")
            msg = (
                f"GPU: {name}\n"
                f"Work-items: {result['work_items']}\n"
                f"Iterações: {result['iterations']}\n"
                f"Tempo: {result['elapsed_s']:.4f} s\n"
                f"Throughput estimado: {result['gflops']:.2f} GFLOPs"
            )
            messagebox.showinfo("Benchmark GPU", msg)


    def _monitor_loop(self) -> None:
        """Roda em thread separada: atualiza progresso, uso CPU, GPU e limites."""
        duration = self.current_duration
        temp_limit = self.temp_limit_var.get()
        mode = self.mode.get()

        while self.running:
            elapsed = int(time.time() - self.start_time)
            self.root.after(0, self.progress_var.set, min(elapsed, duration))

            cpu_usage = psutil.cpu_percent(interval=1)

            temp_str = "N/D"
            max_cpu_temp = None
            try:
                temps = psutil.sensors_temperatures()
                if temps:
                    all_temps = [t.current for arr in temps.values() for t in arr]
                    if all_temps:
                        max_cpu_temp = max(all_temps)
                        temp_str = f"{max_cpu_temp:.1f} °C"
            except Exception:
                pass

            gpu_temp = get_gpu_temp()
            gpu_util = get_gpu_util()
            gpu_temp_str = f"{gpu_temp} °C" if gpu_temp is not None else "N/D"
            gpu_util_str = f"{gpu_util} %" if gpu_util is not None else "N/D"
            
            self.sample_history.append({
                "t": elapsed,
                "cpu": float(cpu_usage),
                "cpu_temp": float(max_cpu_temp) if max_cpu_temp is not None else float("nan"),
                "gpu": float(gpu_util) if gpu_util is not None else float("nan"),
                "gpu_temp": float(gpu_temp) if gpu_temp is not None else float("nan"),
            })

            txt = (
                f"Uso CPU: {cpu_usage:.1f}% | Temp CPU: {temp_str} | "
                f"GPU Util: {gpu_util_str} | Temp GPU: {gpu_temp_str}"
            )
            self.root.after(0, self.runtime_label.config, {"text": txt})

            if elapsed >= duration:
                self.root.after(0, self._finish_due_to_limit, "Tempo limite alcançado.")
                return

            if mode == "cpu":
                if max_cpu_temp is not None and max_cpu_temp >= temp_limit:
                    reason = f"Temperatura CPU limite atingida ({max_cpu_temp:.1f} °C)."
                    self.root.after(0, self._finish_due_to_limit, reason)
                    return
            else:
                if gpu_temp is not None and gpu_temp >= temp_limit:
                    reason = f"Temperatura GPU limite atingida ({gpu_temp:.1f} °C)."
                    self.root.after(0, self._finish_due_to_limit, reason)
                    return

            if mode == "cpu":
                if self.process and self.process.poll() is not None:
                    self.root.after(
                        0, self._finish_due_to_limit,
                        "Processo CPU terminou antes do tempo."
                    )
                    return
            else:
                if self.gpu_stressor is not None and not self.gpu_stressor.running:
                    self.root.after(
                        0, self._finish_due_to_limit,
                        "Stressor GPU parou antes do tempo."
                    )
                    return

    def _finish_due_to_limit(self, reason: str) -> None:
        if not self.running:
            return
        
        if self.mode.get() == "gpu" and self.gpu_stressor is not None:
            try:
                summary = self.gpu_stressor.summary()
                if summary:
                    t_stat = summary["temp"]
                    u_stat = summary["util"]
                    extra = (
                        "\n\nResumo GPU:\n"
                        f"Temp média: {t_stat['avg']:.1f} °C "
                        f"(min {t_stat['min']:.1f}, max {t_stat['max']:.1f})\n"
                        f"Utilização média: {u_stat['avg']:.1f}% "
                        f"(min {u_stat['min']:.1f}%, max {u_stat['max']:.1f}%)\n"
                        f"Duração: {summary['duration_s']:.1f} s"
                    )
            except Exception:
                pass

        self.stop_stress()
        messagebox.showinfo("Estresse finalizado", reason)


def main() -> None:
    root = tk.Tk()
    gui = StressGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
