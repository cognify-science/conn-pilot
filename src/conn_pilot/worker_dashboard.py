from __future__ import annotations

import argparse
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .mcp_server import REPO_ROOT, build_operation_service


ACTIVE_STATES = {"queued", "preparing", "running"}
SUBJECT_PATTERN = re.compile(r"(sub-[A-Za-z0-9]+)", re.IGNORECASE)


def load_env_file(path: str | Path) -> dict[str, str]:
    """Load the worker's local configuration without exposing its secrets."""
    values: dict[str, str] = {}
    env_path = Path(path)
    if not env_path.is_file():
        return values
    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            values[key] = value.strip()
            os.environ.setdefault(key, value.strip())
    return values


def windows_process_inventory() -> list[dict[str, Any]]:
    """Return process names and command lines using the Windows process provider."""
    if os.name != "nt":
        completed = subprocess.run(
            ["ps", "-eo", "pid=,ppid=,comm=,args="],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        result: list[dict[str, Any]] = []
        for line in completed.stdout.splitlines():
            parts = line.strip().split(None, 3)
            if len(parts) == 4:
                result.append(
                    {
                        "ProcessId": int(parts[0]),
                        "ParentProcessId": int(parts[1]),
                        "Name": parts[2],
                        "CommandLine": parts[3],
                    }
                )
        return result

    script = (
        "$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new();"
        "$items=@(Get-CimInstance Win32_Process | "
        "Select-Object ProcessId,ParentProcessId,Name,CreationDate,CommandLine);"
        "$task=Get-ScheduledTask -TaskName 'CONN Pilot Worker' -ErrorAction SilentlyContinue;"
        "if($task){$items += [pscustomobject]@{ProcessId=0;ParentProcessId=0;"
        "Name='__conn_pilot_worker_task__';CreationDate=$null;CommandLine=[string]$task.State}};"
        "$items | ConvertTo-Json -Compress"
    )
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=15,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "Could not inspect Windows processes")
    value = json.loads(completed.stdout or "[]")
    if isinstance(value, dict):
        return [value]
    return value if isinstance(value, list) else []


def summarize_processes(processes: list[dict[str, Any]]) -> dict[str, Any]:
    command_lines = [str(item.get("CommandLine") or "") for item in processes]
    names = [str(item.get("Name") or "").lower() for item in processes]
    task_running = any(
        name == "__conn_pilot_worker_task__" and command.lower() == "running"
        for name, command in zip(names, command_lines)
    )
    supervisor = task_running or any("run_distributed_worker.ps1" in value for value in command_lines)
    distributed_worker = any("conn_pilot.distributed_worker" in value for value in command_lines)
    if not distributed_worker and supervisor:
        distributed_worker = any(name == "python.exe" for name in names)
    explicit_matlab_engines = [
        item
        for item, name, command in zip(processes, names, command_lines)
        if name == "matlab.exe" and ("\\bin\\win64\\matlab.exe" in command.lower() or "/bin/win64/matlab.exe" in command.lower())
    ]
    matlab_processes = [item for item, name in zip(processes, names) if name == "matlab.exe"]
    matlab_pids = {int(item.get("ProcessId") or 0) for item in matlab_processes}
    child_engines = [
        item
        for item in matlab_processes
        if int(item.get("ParentProcessId") or 0) in matlab_pids
    ]
    matlab_engines = explicit_matlab_engines or child_engines
    matlab_main = [
        item for item in matlab_engines if "-batch" in str(item.get("CommandLine") or "").lower()
    ]
    internal_count = (
        len([item for item in matlab_engines if item not in matlab_main])
        if matlab_main
        else max(0, len(matlab_engines) - 1)
    )
    return {
        "supervisor": supervisor,
        "distributed_worker": distributed_worker,
        "worker_online": supervisor and distributed_worker,
        "matlab_running": bool(matlab_engines),
        "matlab_engine_count": len(matlab_engines),
        "matlab_internal_count": internal_count,
        "matlab_process_ids": [int(item.get("ProcessId") or 0) for item in matlab_engines],
    }


def find_remote_job_id(work_root: Path, local_job_id: str | None) -> str | None:
    if not local_job_id:
        return None
    remote_root = work_root / "remote"
    if not remote_root.is_dir():
        return None
    for state_path in remote_root.glob("*/worker-state.json"):
        try:
            value = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if str(value.get("local_job_id", "")) == local_job_id:
            return str(value.get("remote_job_id") or state_path.parent.name)
    return None


def read_recovery_state(work_root: Path, local_job_id: str | None = None) -> dict[str, Any] | None:
    """Return the newest durable nonterminal recovery record, if one exists."""
    remote_root = work_root / "remote"
    if not remote_root.is_dir():
        return None
    candidates: list[tuple[float, dict[str, Any]]] = []
    for path in remote_root.glob("*/recovery-state.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(value, dict) or value.get("state") not in {"running", "publishing"}:
            continue
        if local_job_id and value.get("local_job_id") not in {None, local_job_id}:
            continue
        value.setdefault("remote_job_id", path.parent.name)
        candidates.append((path.stat().st_mtime, value))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def describe_run_output(relative_path: str) -> str:
    """Translate a recently touched CONN output into a conservative live label."""
    name = Path(relative_path).name.lower()
    if name.endswith(".stdlog"):
        return "Log de nodo CONN"
    if name == "matlab_stdout.log":
        return "Log principal MATLAB"
    if name.endswith(".dmat") or name == "info.mat":
        return "Coordinación paralela"
    if name.startswith("rp_"):
        return "Realineamiento"
    if name.startswith("art_") or "outlier" in name:
        return "Detección de outliers"
    if name.startswith("sw") and "bold" in name:
        return "Suavizado funcional"
    if name.startswith("w") and "bold" in name:
        return "Normalización funcional"
    if name.startswith("u") and "bold" in name:
        return "Realineamiento / unwarp"
    if name.startswith("y_") or (name.startswith("wc") and "t1" in name):
        return "Normalización anatómica"
    if (name.startswith("c") or name.startswith("icentering_")) and "t1" in name:
        return "Centrado anatómico"
    if name.startswith("roi_") or "resultsroi" in name:
        return "Extracción ROI"
    if name.startswith("beta_") or "firstlevel" in relative_path.lower():
        return "Análisis de primer nivel"
    if "secondlevel" in relative_path.lower() or name.startswith("spm"):
        return "Análisis de segundo nivel"
    if "qa_" in name or "qc" in relative_path.lower():
        return "Control de calidad"
    normalized = relative_path.lower().replace("\\", "/")
    if "/func/" in f"/{normalized}" and "bold" in name:
        return "Actualización funcional"
    if "/anat/" in f"/{normalized}" and "t1" in name:
        return "Actualización anatómica"
    return "Escritura de salida"


def scan_run_activity(
    run_dir: str | Path,
    previous_index: dict[str, tuple[int, int]] | None = None,
    *,
    now_ts: float | None = None,
    interval_seconds: float | None = None,
) -> tuple[dict[str, Any], dict[str, tuple[int, int]]]:
    """Read high-frequency filesystem signals without treating them as completed work."""
    root = Path(run_dir)
    current_time = time.time() if now_ts is None else now_ts
    baseline = previous_index is None
    previous = previous_index or {}
    current: dict[str, tuple[int, int]] = {}
    events: list[dict[str, Any]] = []
    total_bytes = 0
    changed_count = 0
    new_count = 0
    bytes_delta = 0
    latest_path: str | None = None
    latest_mtime = 0.0
    node_logs: list[dict[str, Any]] = []

    if not root.is_dir():
        return {
            "available": False,
            "events": [],
            "changed_files": 0,
            "new_files": 0,
            "bytes_delta": 0,
            "total_files": 0,
            "total_bytes": 0,
            "subjects_observed": [],
            "node_logs": [],
        }, current

    for path in root.rglob("*"):
        try:
            if not path.is_file():
                continue
            stat = path.stat()
            relative = path.relative_to(root).as_posix()
        except OSError:
            continue
        signature = (stat.st_mtime_ns, stat.st_size)
        current[relative] = signature
        total_bytes += stat.st_size
        modified = stat.st_mtime
        if modified > latest_mtime:
            latest_mtime = modified
            latest_path = relative

        old = previous.get(relative)
        is_new = old is None
        is_changed = old is not None and old != signature
        initial_recent = baseline and current_time - modified <= 300
        if (not baseline and (is_new or is_changed)) or initial_recent:
            changed_count += 1
            if not baseline and is_new:
                new_count += 1
            if not baseline:
                bytes_delta += abs(stat.st_size - (old[1] if old else 0))
            match = SUBJECT_PATTERN.search(relative)
            events.append(
                {
                    "path": relative,
                    "file_name": path.name,
                    "subject_id": match.group(1).lower() if match else None,
                    "step": describe_run_output(relative),
                    "modified_at": datetime.fromtimestamp(modified).astimezone().isoformat(timespec="seconds"),
                    "age_seconds": max(0, int(current_time - modified)),
                    "size": stat.st_size,
                    "kind": "new" if is_new and not baseline else "updated",
                    "signature": f"{relative}:{stat.st_mtime_ns}:{stat.st_size}",
                }
            )

        if path.suffix.lower() == ".stdlog":
            node_logs.append(
                {
                    "name": path.name,
                    "size": stat.st_size,
                    "age_seconds": max(0, int(current_time - modified)),
                    "active": current_time - modified <= 120,
                }
            )

    events.sort(key=lambda value: str(value["modified_at"]), reverse=True)
    node_logs.sort(key=lambda value: str(value["name"]))
    subjects = sorted({str(value["subject_id"]) for value in events if value.get("subject_id")})
    elapsed = max(0.1, float(interval_seconds or 0))
    files_per_minute = round(changed_count * 60 / elapsed, 1) if not baseline and interval_seconds else None
    return {
        "available": True,
        "events": events[:60],
        "changed_files": changed_count,
        "new_files": new_count,
        "bytes_delta": bytes_delta,
        "total_files": len(current),
        "total_bytes": total_bytes,
        "latest_path": latest_path,
        "latest_step": describe_run_output(latest_path) if latest_path else None,
        "latest_age_seconds": max(0, int(current_time - latest_mtime)) if latest_mtime else None,
        "subjects_observed": subjects,
        "node_logs": node_logs,
        "active_nodes": sum(1 for value in node_logs if value["active"]),
        "scan_interval_seconds": round(elapsed, 1) if interval_seconds else None,
        "files_per_minute": files_per_minute,
        "interpretation": "Live file activity is operational evidence, not a completion percentage.",
    }, current


def classify_health(
    process_summary: dict[str, Any], active_job: dict[str, Any] | None,
    progress: dict[str, Any] | None, recovery: dict[str, Any] | None = None,
) -> tuple[str, str]:
    if not process_summary.get("worker_online"):
        return "error", "Supervisor detenido"
    if active_job is None:
        if recovery and recovery.get("state") in {"running", "publishing"}:
            return "starting", "Recuperando ejecución"
        return "idle", "Worker disponible"
    state = str(active_job.get("state", "unknown"))
    if state == "running" and not process_summary.get("matlab_running"):
        if recovery and recovery.get("state") == "running":
            return "starting", "Recuperando ejecución"
        return "error", "Job activo sin MATLAB"
    activity = dict((progress or {}).get("activity") or {})
    active_subjects = list(((progress or {}).get("subjects") or {}).get("active_subject_ids") or [])
    if state == "running" and activity.get("state") == "stale" and not active_subjects:
        return "error", "Actividad estancada"
    if state in {"queued", "preparing"}:
        return "starting", "Iniciando ejecución"
    if state == "running":
        return "healthy", "Procesando normalmente"
    return "idle", "Worker disponible"


class DashboardReader:
    def __init__(
        self,
        *,
        work_root: str | Path,
        service: Any | None = None,
        process_provider: Callable[[], list[dict[str, Any]]] = windows_process_inventory,
    ) -> None:
        self.work_root = Path(work_root).resolve()
        self.service = service or build_operation_service()
        self.process_provider = process_provider
        self.last_process_summary: dict[str, Any] | None = None
        self.last_run_id: str | None = None
        self.last_file_index: dict[str, tuple[int, int]] | None = None
        self.last_file_scan_at: float | None = None
        self.live_event_history: list[dict[str, Any]] = []

    def snapshot(self) -> dict[str, Any]:
        errors: list[str] = []
        try:
            processes = summarize_processes(self.process_provider())
            self.last_process_summary = processes
        except Exception as error:  # the dashboard must remain usable if CIM is unavailable
            processes = self.last_process_summary or {
                "supervisor": False,
                "distributed_worker": False,
                "worker_online": False,
                "matlab_running": False,
                "matlab_engine_count": 0,
                "matlab_internal_count": 0,
                "matlab_process_ids": [],
            }
            errors.append(f"Process inspection failed: {error}")

        jobs = self.service.store.list()
        active_job = next((item for item in jobs if item.get("state") in ACTIVE_STATES), None)
        status_data: dict[str, Any] = {}
        progress: dict[str, Any] | None = None
        if active_job:
            try:
                status = self.service.get_job_status(str(active_job["id"]))
                status_data = dict(status.get("data") or {})
                progress_response = self.service.get_job_progress(str(active_job["id"]))
                progress = (progress_response.get("data") or {}).get("progress")
                errors.extend(str(value) for value in progress_response.get("errors", []))
            except Exception as error:
                errors.append(f"Local job inspection failed: {error}")

        local_job_id = str(active_job["id"]) if active_job else None
        remote_job_id = find_remote_job_id(self.work_root, local_job_id)
        recovery = read_recovery_state(self.work_root, local_job_id)
        if not remote_job_id and recovery:
            remote_job_id = str(recovery.get("remote_job_id") or "") or None
        live_activity: dict[str, Any] | None = None
        if active_job and active_job.get("run_dir"):
            current_time = time.time()
            if local_job_id != self.last_run_id:
                self.last_run_id = local_job_id
                self.last_file_index = None
                self.last_file_scan_at = None
                self.live_event_history = []
            interval = current_time - self.last_file_scan_at if self.last_file_scan_at else None
            live_activity, self.last_file_index = scan_run_activity(
                str(active_job["run_dir"]),
                self.last_file_index,
                now_ts=current_time,
                interval_seconds=interval,
            )
            self.last_file_scan_at = current_time
            known = {str(value.get("signature")) for value in self.live_event_history}
            additions = [
                value for value in live_activity.get("events", []) if str(value.get("signature")) not in known
            ]
            self.live_event_history = (additions + self.live_event_history)[:100]
            live_activity["events"] = list(self.live_event_history)
        elif self.last_run_id is not None:
            self.last_run_id = None
            self.last_file_index = None
            self.last_file_scan_at = None
            self.live_event_history = []
        health, health_label = classify_health(processes, active_job, progress, recovery)
        snapshot = {
            "schema_version": "conn_pilot_worker_dashboard_v1",
            "reported_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "health": health,
            "health_label": health_label,
            "processes": processes,
            "active_job": active_job,
            "remote_job_id": remote_job_id,
            "recovery": recovery,
            "phase": status_data.get("phase"),
            "terminal": status_data.get("terminal"),
            "progress": progress,
            "live_activity": live_activity,
            "jobs": jobs[:20],
            "errors": errors,
        }
        self._write_snapshot(snapshot)
        return snapshot

    def _write_snapshot(self, snapshot: dict[str, Any]) -> None:
        log_dir = self.work_root / "logs"
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            target = log_dir / "worker-dashboard-state.json"
            temporary = log_dir / "worker-dashboard-state.json.tmp"
            temporary.write_text(
                json.dumps(snapshot, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            temporary.replace(target)
        except OSError:
            pass


def _format_age(seconds: Any) -> str:
    if seconds is None:
        return "sin datos"
    value = max(0, int(seconds))
    if value < 60:
        return f"hace {value} s"
    if value < 3600:
        return f"hace {value // 60} min"
    return f"hace {value // 3600} h {(value % 3600) // 60} min"


def _format_bytes(value: Any) -> str:
    size = max(0, int(value or 0))
    units = ("B", "KB", "MB", "GB", "TB")
    amount = float(size)
    unit = units[0]
    for candidate in units:
        unit = candidate
        if amount < 1024 or candidate == units[-1]:
            break
        amount /= 1024
    return f"{amount:.1f} {unit}" if unit != "B" else f"{size} B"


class WorkerDashboard:
    COLORS = {
        "background": "#0f172a",
        "panel": "#172033",
        "panel_alt": "#1e293b",
        "text": "#e5e7eb",
        "muted": "#94a3b8",
        "healthy": "#22c55e",
        "idle": "#38bdf8",
        "starting": "#f59e0b",
        "error": "#ef4444",
    }

    def __init__(self, reader: DashboardReader, refresh_seconds: int = 5) -> None:
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.ttk = ttk
        self.reader = reader
        self.refresh_ms = max(2, refresh_seconds) * 1000
        self.results: queue.Queue[dict[str, Any] | Exception] = queue.Queue()
        self.refreshing = False
        self.last_snapshot: dict[str, Any] | None = None

        self.root = tk.Tk()
        self.root.title("CONN Pilot · Worker Monitor")
        self.root.geometry("1220x820")
        self.root.minsize(1000, 680)
        self.root.configure(bg=self.COLORS["background"])
        self._configure_style()
        self._build()
        self.root.after(100, self.refresh)

    def _configure_style(self) -> None:
        style = self.ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background=self.COLORS["background"])
        style.configure("Panel.TFrame", background=self.COLORS["panel"])
        style.configure(
            "TLabel", background=self.COLORS["background"], foreground=self.COLORS["text"], font=("Segoe UI", 10)
        )
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 21), foreground="#f8fafc")
        style.configure("Muted.TLabel", foreground=self.COLORS["muted"])
        style.configure("CardTitle.TLabel", background=self.COLORS["panel"], foreground=self.COLORS["muted"], font=("Segoe UI Semibold", 9))
        style.configure("CardValue.TLabel", background=self.COLORS["panel"], foreground=self.COLORS["text"], font=("Segoe UI Semibold", 15))
        style.configure("TButton", font=("Segoe UI Semibold", 9), padding=(12, 7))
        style.configure("TNotebook", background=self.COLORS["panel"], borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background=self.COLORS["panel_alt"],
            foreground=self.COLORS["text"],
            padding=(12, 7),
            font=("Segoe UI Semibold", 9),
        )
        style.map("TNotebook.Tab", background=[("selected", "#334155")])
        style.configure("Treeview", background=self.COLORS["panel"], fieldbackground=self.COLORS["panel"], foreground=self.COLORS["text"], rowheight=27, borderwidth=0)
        style.configure("Treeview.Heading", background=self.COLORS["panel_alt"], foreground=self.COLORS["text"], font=("Segoe UI Semibold", 9))
        style.map("Treeview", background=[("selected", "#334155")])
        style.configure("Horizontal.TProgressbar", troughcolor="#334155", background=self.COLORS["healthy"], borderwidth=0)

    def _build(self) -> None:
        header = self.ttk.Frame(self.root)
        header.pack(fill="x", padx=24, pady=(20, 12))
        self.ttk.Label(header, text="CONN Pilot", style="Title.TLabel").pack(side="left")
        self.status_dot = self.tk.Label(header, text="●", font=("Segoe UI", 18), bg=self.COLORS["background"], fg=self.COLORS["starting"])
        self.status_dot.pack(side="left", padx=(18, 6))
        self.status_label = self.ttk.Label(header, text="Leyendo estado…")
        self.status_label.pack(side="left")
        self.updated_label = self.ttk.Label(header, text="", style="Muted.TLabel")
        self.updated_label.pack(side="right")

        cards = self.ttk.Frame(self.root)
        cards.pack(fill="x", padx=24, pady=(0, 14))
        cards.columnconfigure((0, 1, 2, 3), weight=1)
        self.card_values: dict[str, Any] = {}
        for column, (key, title) in enumerate(
            (("worker", "SUPERVISOR"), ("matlab", "MATLAB"), ("job", "JOB ACTIVO"), ("activity", "ACTIVIDAD"))
        ):
            panel = self.ttk.Frame(cards, style="Panel.TFrame", padding=14)
            panel.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 6, 0 if column == 3 else 6))
            self.ttk.Label(panel, text=title, style="CardTitle.TLabel").pack(anchor="w")
            value = self.ttk.Label(panel, text="—", style="CardValue.TLabel")
            value.pack(anchor="w", pady=(5, 0))
            self.card_values[key] = value

        progress_panel = self.ttk.Frame(self.root, style="Panel.TFrame", padding=16)
        progress_panel.pack(fill="x", padx=24, pady=(0, 14))
        top = self.ttk.Frame(progress_panel, style="Panel.TFrame")
        top.pack(fill="x")
        self.job_title = self.ttk.Label(top, text="Sin job activo", style="CardValue.TLabel")
        self.job_title.pack(side="left")
        self.percent_label = self.ttk.Label(top, text="0%", style="CardValue.TLabel")
        self.percent_label.pack(side="right")
        self.progress_bar = self.ttk.Progressbar(progress_panel, maximum=100)
        self.progress_bar.pack(fill="x", pady=(12, 8))
        self.job_detail = self.ttk.Label(progress_panel, text="", style="CardTitle.TLabel")
        self.job_detail.pack(anchor="w")
        self.live_summary = self.ttk.Label(progress_panel, text="", style="CardTitle.TLabel")
        self.live_summary.pack(anchor="w", pady=(6, 0))

        body = self.ttk.Panedwindow(self.root, orient="horizontal")
        body.pack(fill="both", expand=True, padx=24, pady=(0, 14))
        left = self.ttk.Frame(body, style="Panel.TFrame", padding=12)
        right = self.ttk.Frame(body, style="Panel.TFrame", padding=12)
        body.add(left, weight=2)
        body.add(right, weight=3)

        self.ttk.Label(left, text="ETAPAS · HITOS DURABLES", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 8))
        self.stages = self.ttk.Treeview(left, columns=("done", "status"), show="headings", height=8)
        self.stages.heading("done", text="Completado")
        self.stages.heading("status", text="Estado")
        self.stages.column("done", width=130, anchor="center")
        self.stages.column("status", width=150, anchor="center")
        self.stages.pack(fill="both", expand=True)

        notebook = self.ttk.Notebook(right)
        notebook.pack(fill="both", expand=True)
        live_tab = self.ttk.Frame(notebook, style="Panel.TFrame", padding=8)
        history_tab = self.ttk.Frame(notebook, style="Panel.TFrame", padding=8)
        notebook.add(live_tab, text="Actividad en vivo")
        notebook.add(history_tab, text="Historial local")

        self.live_events = self.ttk.Treeview(
            live_tab,
            columns=("time", "subject", "step", "file"),
            show="headings",
            height=8,
        )
        self.live_events.heading("time", text="Hora")
        self.live_events.heading("subject", text="Sujeto")
        self.live_events.heading("step", text="Paso observado")
        self.live_events.heading("file", text="Archivo actualizado")
        self.live_events.column("time", width=72, anchor="center")
        self.live_events.column("subject", width=82, anchor="center")
        self.live_events.column("step", width=175)
        self.live_events.column("file", width=300)
        self.live_events.pack(fill="both", expand=True)

        self.jobs = self.ttk.Treeview(history_tab, columns=("project", "state", "updated"), show="headings", height=8)
        self.jobs.heading("project", text="Proyecto")
        self.jobs.heading("state", text="Estado")
        self.jobs.heading("updated", text="Actualizado")
        self.jobs.column("project", width=240)
        self.jobs.column("state", width=100, anchor="center")
        self.jobs.column("updated", width=150, anchor="center")
        self.jobs.pack(fill="both", expand=True)

        footer = self.ttk.Frame(self.root)
        footer.pack(fill="x", padx=24, pady=(0, 20))
        self.error_label = self.ttk.Label(footer, text="", foreground=self.COLORS["error"])
        self.error_label.pack(side="left")
        self.ttk.Button(footer, text="Copiar diagnóstico", command=self.copy_diagnostic).pack(side="right")
        self.ttk.Button(footer, text="Abrir ejecución", command=self.open_run_directory).pack(side="right", padx=8)
        self.ttk.Button(footer, text="Actualizar", command=self.refresh).pack(side="right")

    def refresh(self) -> None:
        if self.refreshing:
            return
        self.refreshing = True
        threading.Thread(target=self._read_snapshot, daemon=True).start()
        self.root.after(100, self._poll_snapshot)

    def _read_snapshot(self) -> None:
        try:
            self.results.put(self.reader.snapshot())
        except Exception as error:
            self.results.put(error)

    def _poll_snapshot(self) -> None:
        try:
            value = self.results.get_nowait()
        except queue.Empty:
            self.root.after(100, self._poll_snapshot)
            return
        self.refreshing = False
        try:
            if isinstance(value, Exception):
                self.error_label.configure(text=str(value))
            else:
                self.last_snapshot = value
                self._render(value)
        except Exception as error:
            self.error_label.configure(text=f"No se pudo actualizar la ventana: {error}")
        finally:
            self.root.after(self.refresh_ms, self.refresh)

    def _render(self, snapshot: dict[str, Any]) -> None:
        health = str(snapshot["health"])
        processes = snapshot["processes"]
        active_job = snapshot.get("active_job") or {}
        progress = snapshot.get("progress") or {}
        recovery = snapshot.get("recovery") or progress.get("recovery") or {}
        live_activity = snapshot.get("live_activity") or {}
        activity = progress.get("activity") or {}
        active_subjects = list((progress.get("subjects") or {}).get("active_subject_ids") or [])
        self.status_dot.configure(fg=self.COLORS.get(health, self.COLORS["muted"]))
        self.status_label.configure(text=str(snapshot["health_label"]))
        self.updated_label.configure(text=f"Actualizado {snapshot['reported_at'][11:19]}")
        self.card_values["worker"].configure(text="Online" if processes.get("worker_online") else "Offline")
        matlab_text = "Inactivo"
        if processes.get("matlab_running"):
            matlab_text = f"Activo · {processes.get('matlab_internal_count', 0)} internos"
        self.card_values["matlab"].configure(text=matlab_text)
        self.card_values["job"].configure(text=str(active_job.get("state") or "En espera").upper())
        activity_text = _format_age(activity.get("seconds_since_activity"))
        if activity.get("state") == "active":
            activity_text = f"Activa · {len(active_subjects)} sujetos"
        elif recovery.get("state") in {"running", "publishing"}:
            activity_text = (
                f"Recuperando · {int(recovery.get('recovery_count') or recovery.get('restart_count') or 0)} reinicios"
            )
        self.card_values["activity"].configure(text=activity_text)

        percent = int(progress.get("approximate_percent") or 0)
        units = progress.get("progress_basis") or {}
        remote_id = snapshot.get("remote_job_id") or "—"
        local_id = active_job.get("id") or "—"
        self.progress_bar.configure(value=percent)
        self.percent_label.configure(text=f"{percent}%")
        self.job_title.configure(text=str(active_job.get("project_name") or "Sin job activo"))
        self.job_detail.configure(
            text=(
                f"Fase: {snapshot.get('phase') or '—'}   ·   "
                f"Unidades: {units.get('completed_units', 0)}/{units.get('total_units', 0)}   ·   "
                f"Remoto: {remote_id}   ·   Local: {local_id}"
            )
        )
        live_parts: list[str] = []
        if live_activity.get("available"):
            changed = int(live_activity.get("changed_files") or 0)
            interval = live_activity.get("scan_interval_seconds")
            if interval:
                live_parts.append(f"Señal local: {changed} archivos cambiaron en {float(interval):.0f} s")
            else:
                live_parts.append("Señal local inicializada")
            if int(live_activity.get("bytes_delta") or 0) > 0:
                live_parts.append(f"Δ tamaño {_format_bytes(live_activity.get('bytes_delta'))}")
            live_parts.append(f"nodos con escritura reciente: {int(live_activity.get('active_nodes') or 0)}")
            if live_activity.get("latest_step"):
                live_parts.append(
                    f"último: {live_activity['latest_step']} ({_format_age(live_activity.get('latest_age_seconds'))})"
                )
        self.live_summary.configure(text="   ·   ".join(live_parts))

        for item in self.stages.get_children():
            self.stages.delete(item)
        status_labels = {
            "complete": "Hito completo",
            "in_progress": "Hito en curso",
            "pending": "Sin hito durable aún",
        }
        for stage in progress.get("stages") or []:
            self.stages.insert(
                "",
                "end",
                values=(
                    f"{stage.get('name', '').replace('_', ' ').title()}: {stage.get('completed', 0)}/{stage.get('total', 0)}",
                    status_labels.get(str(stage.get("status")), str(stage.get("status") or "—")),
                ),
            )

        for item in self.live_events.get_children():
            self.live_events.delete(item)
        for event in (live_activity.get("events") or [])[:40]:
            modified = str(event.get("modified_at") or "")
            relative = str(event.get("path") or "")
            self.live_events.insert(
                "",
                "end",
                values=(
                    modified[11:19] if len(modified) >= 19 else "—",
                    event.get("subject_id") or "—",
                    event.get("step") or "—",
                    relative,
                ),
            )

        for item in self.jobs.get_children():
            self.jobs.delete(item)
        for job in snapshot.get("jobs") or []:
            updated = str(job.get("updated_at") or "").replace("T", " ")[:19]
            self.jobs.insert("", "end", values=(job.get("project_name"), job.get("state"), updated))
        self.error_label.configure(text=" · ".join(snapshot.get("errors") or []))

    def open_run_directory(self) -> None:
        if not self.last_snapshot:
            return
        job = self.last_snapshot.get("active_job") or {}
        run_dir = str(job.get("run_dir") or "")
        if run_dir and Path(run_dir).is_dir():
            os.startfile(run_dir)  # type: ignore[attr-defined]

    def copy_diagnostic(self) -> None:
        if not self.last_snapshot:
            return
        payload = json.dumps(self.last_snapshot, ensure_ascii=False, indent=2, default=str)
        self.root.clipboard_clear()
        self.root.clipboard_append(payload)

    def run(self) -> None:
        self.root.mainloop()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CONN Pilot Windows worker monitor")
    parser.add_argument("--json", action="store_true", help="Print one snapshot and exit")
    parser.add_argument("--refresh-seconds", type=int, default=5)
    parser.add_argument("--env-file", default=str(REPO_ROOT / ".env.distributed.local"))
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    load_env_file(arguments.env_file)
    work_root = Path(os.environ.get("CONN_PILOT_WORK_ROOT", REPO_ROOT / "work"))
    reader = DashboardReader(work_root=work_root)
    if arguments.json:
        print(json.dumps(reader.snapshot(), ensure_ascii=False, indent=2, default=str))
        return 0
    WorkerDashboard(reader, refresh_seconds=arguments.refresh_seconds).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
