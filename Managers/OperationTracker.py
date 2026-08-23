"""Persistent, thread-safe lifecycle tracking for long-running application jobs."""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Iterable

from PySide6.QtCore import QObject, Signal


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class OperationStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    STOPPING = "stopping"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class OperationKind(str, Enum):
    UPLOAD = "upload"
    BATCH_VARIANTS = "batch_variants"
    FOLDER_JOB = "folder_job"
    SPEC_SCANNER = "spec_scanner"
    NAME_SCANNER = "name_scanner"
    CODE_SCANNER = "code_scanner"
    URL_SCANNER = "url_scanner"
    IMAGE_TOOL = "image_tool"
    ORBEA = "orbea"
    OTHER = "other"


TERMINAL_STATUSES = frozenset(
    {
        OperationStatus.SUCCEEDED,
        OperationStatus.PARTIAL,
        OperationStatus.FAILED,
        OperationStatus.CANCELLED,
        OperationStatus.INTERRUPTED,
    }
)


@dataclass(frozen=True)
class OperationRecord:
    id: str
    kind: OperationKind
    source_route: str
    status: OperationStatus
    current: int = 0
    total: int = 0
    stage: str = ""
    message: str = ""
    summary: dict[str, Any] | None = None
    error_summary: str = ""
    output_path: str = ""
    resume_kind: str = ""
    resume_ref: str = ""
    batch_id: str = ""
    started_at: str = ""
    updated_at: str = ""
    finished_at: str = ""

    @property
    def progress_percent(self) -> int:
        if self.total <= 0:
            return 0
        return max(0, min(100, round(self.current * 100 / self.total)))


class OperationTracker(QObject):
    """Serialize operation writes and relay changes to the GUI via Qt signals."""

    operationChanged = Signal(str)
    runningCountChanged = Signal(int)

    def __init__(self, database, parent: QObject | None = None):
        super().__init__(parent)
        self.database = database
        self._lock = getattr(database, "write_lock", threading.RLock())
        self._cancel_callbacks: dict[str, Callable[[], None]] = {}
        self.mark_abandoned_interrupted()

    @staticmethod
    def _status(value: OperationStatus | str) -> OperationStatus:
        return value if isinstance(value, OperationStatus) else OperationStatus(value)

    @staticmethod
    def _kind(value: OperationKind | str) -> OperationKind:
        try:
            return value if isinstance(value, OperationKind) else OperationKind(value)
        except ValueError:
            return OperationKind.OTHER

    @staticmethod
    def _from_row(row) -> OperationRecord:
        try:
            summary = json.loads(row[8]) if row[8] else {}
        except (TypeError, json.JSONDecodeError):
            summary = {}
        return OperationRecord(
            id=row[0], kind=OperationTracker._kind(row[1]), source_route=row[2],
            status=OperationStatus(row[3]), current=int(row[4] or 0),
            total=int(row[5] or 0), stage=row[6] or "", message=row[7] or "",
            summary=summary, error_summary=row[9] or "", output_path=row[10] or "",
            resume_kind=row[11] or "", resume_ref=row[12] or "", batch_id=row[13] or "",
            started_at=row[14] or "", updated_at=row[15] or "", finished_at=row[16] or "",
        )

    @staticmethod
    def _columns() -> str:
        return (
            "id, kind, source_route, status, current, total, stage, message, "
            "summary_json, error_summary, output_path, resume_kind, resume_ref, "
            "batch_id, started_at, updated_at, finished_at"
        )

    def create(
        self, kind: OperationKind | str, source_route: str, *, stage: str = "Queued",
        message: str = "", total: int = 0, output_path: str = "",
        resume_kind: str = "", resume_ref: str = "", batch_id: str = "",
        summary: dict[str, Any] | None = None, cancel: Callable[[], None] | None = None,
    ) -> OperationRecord:
        stamp = _utc_now()
        record = OperationRecord(
            id=uuid.uuid4().hex, kind=self._kind(kind), source_route=str(source_route or ""),
            status=OperationStatus.QUEUED, total=max(0, int(total or 0)), stage=stage,
            message=message, summary=dict(summary or {}), output_path=str(output_path or ""),
            resume_kind=str(resume_kind or ""), resume_ref=str(resume_ref or ""),
            batch_id=str(batch_id or ""), started_at=stamp, updated_at=stamp,
        )
        with self._lock, self.database.conn:
            self.database.conn.execute(
                """
                INSERT INTO operation_runs (
                    id, kind, source_route, status, current, total, stage, message,
                    summary_json, error_summary, output_path, resume_kind, resume_ref,
                    batch_id, started_at, updated_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id, record.kind.value, record.source_route, record.status.value,
                    record.current, record.total, record.stage, record.message,
                    json.dumps(record.summary, ensure_ascii=False, sort_keys=True), "",
                    record.output_path, record.resume_kind, record.resume_ref,
                    record.batch_id, record.started_at, record.updated_at, None,
                ),
            )
            if cancel is not None:
                self._cancel_callbacks[record.id] = cancel
        self._emit_changed(record.id)
        return record

    def get(self, operation_id: str) -> OperationRecord | None:
        with self._lock:
            row = self.database.conn.execute(
                f"SELECT {self._columns()} FROM operation_runs WHERE id=?", (operation_id,)
            ).fetchone()
        return self._from_row(row) if row else None

    def list(self, *, limit: int = 250, statuses: Iterable[OperationStatus | str] | None = None) -> list[OperationRecord]:
        params: list[Any] = []
        where = ""
        if statuses:
            values = [self._status(value).value for value in statuses]
            where = " WHERE status IN ({})".format(",".join("?" for _ in values))
            params.extend(values)
        params.append(max(1, min(5000, int(limit))))
        with self._lock:
            rows = self.database.conn.execute(
                f"SELECT {self._columns()} FROM operation_runs{where} ORDER BY updated_at DESC LIMIT ?",
                params,
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def update(
        self, operation_id: str, *, status: OperationStatus | str | None = None,
        current: int | None = None, total: int | None = None, stage: str | None = None,
        message: str | None = None, error_summary: str | None = None,
        output_path: str | None = None, resume_kind: str | None = None,
        resume_ref: str | None = None, summary: dict[str, Any] | None = None,
    ) -> OperationRecord:
        with self._lock, self.database.conn:
            existing = self.get(operation_id)
            if existing is None:
                raise KeyError(f"Unknown operation: {operation_id}")
            new_status = self._status(status) if status is not None else existing.status
            if existing.status in TERMINAL_STATUSES and new_status != existing.status:
                return existing
            merged_summary = dict(existing.summary or {})
            if summary:
                merged_summary.update(summary)
            stamp = _utc_now()
            finished_at = existing.finished_at
            if new_status in TERMINAL_STATUSES and not finished_at:
                finished_at = stamp
            updated = replace(
                existing, status=new_status,
                current=max(0, int(current)) if current is not None else existing.current,
                total=max(0, int(total)) if total is not None else existing.total,
                stage=str(stage) if stage is not None else existing.stage,
                message=str(message) if message is not None else existing.message,
                error_summary=str(error_summary) if error_summary is not None else existing.error_summary,
                output_path=str(output_path) if output_path is not None else existing.output_path,
                resume_kind=str(resume_kind) if resume_kind is not None else existing.resume_kind,
                resume_ref=str(resume_ref) if resume_ref is not None else existing.resume_ref,
                summary=merged_summary, updated_at=stamp, finished_at=finished_at,
            )
            self.database.conn.execute(
                """
                UPDATE operation_runs SET status=?, current=?, total=?, stage=?, message=?,
                    summary_json=?, error_summary=?, output_path=?, resume_kind=?, resume_ref=?,
                    updated_at=?, finished_at=? WHERE id=?
                """,
                (
                    updated.status.value, updated.current, updated.total, updated.stage,
                    updated.message, json.dumps(updated.summary, ensure_ascii=False, sort_keys=True),
                    updated.error_summary, updated.output_path, updated.resume_kind,
                    updated.resume_ref, updated.updated_at, updated.finished_at or None, operation_id,
                ),
            )
            if updated.status in TERMINAL_STATUSES:
                self._cancel_callbacks.pop(operation_id, None)
        self._emit_changed(operation_id)
        return updated

    def start(self, operation_id: str, *, stage: str = "Running") -> OperationRecord:
        return self.update(operation_id, status=OperationStatus.RUNNING, stage=stage)

    def progress(self, operation_id: str, current: int, total: int = 0, *, stage: str | None = None, message: str | None = None) -> OperationRecord:
        return self.update(operation_id, status=OperationStatus.RUNNING, current=current, total=total, stage=stage, message=message)

    def finish(
        self, operation_id: str, status: OperationStatus | str = OperationStatus.SUCCEEDED,
        *, message: str | None = None, error_summary: str | None = None,
        output_path: str | None = None, summary: dict[str, Any] | None = None,
    ) -> OperationRecord:
        terminal = self._status(status)
        if terminal not in TERMINAL_STATUSES:
            raise ValueError("finish() requires a terminal operation status")
        return self.update(operation_id, status=terminal, message=message,
                           error_summary=error_summary, output_path=output_path, summary=summary)

    def request_cancel(self, operation_id: str) -> bool:
        record = self.get(operation_id)
        if record is None or record.status in TERMINAL_STATUSES:
            return False
        self.update(operation_id, status=OperationStatus.STOPPING, stage="Stopping")
        callback = self._cancel_callbacks.get(operation_id)
        if callback is not None:
            try:
                callback()
            except Exception as error:
                self.finish(operation_id, OperationStatus.FAILED, error_summary=str(error))
                return False
        return True

    def mark_abandoned_interrupted(self) -> int:
        stamp = _utc_now()
        with self._lock, self.database.conn:
            cursor = self.database.conn.execute(
                """
                UPDATE operation_runs SET status='interrupted', stage='Interrupted',
                    updated_at=?, finished_at=? WHERE status IN ('queued', 'running', 'stopping')
                """,
                (stamp, stamp),
            )
            count = int(cursor.rowcount or 0)
        if count:
            self._emit_changed("")
        return count

    def running_count(self) -> int:
        with self._lock:
            row = self.database.conn.execute(
                "SELECT COUNT(*) FROM operation_runs WHERE status IN ('queued','running','stopping')"
            ).fetchone()
        return int(row[0] if row else 0)

    def track_qthread(self, worker, kind: OperationKind | str, source_route: str, **metadata) -> OperationRecord:
        """Track a retained QThread using its common lifecycle/progress signals."""
        if not metadata.get("batch_id"):
            uploader = getattr(worker, "uploader", None)
            metadata["batch_id"] = str(
                getattr(worker, "batch_id", "")
                or getattr(worker, "_batch_id", "")
                or getattr(uploader, "batch_id", "")
                or ""
            )
        def cancel_worker() -> None:
            for method_name in ("request_stop", "stop", "cancel"):
                method = getattr(worker, method_name, None)
                if callable(method):
                    method()
                    return
            worker.requestInterruption()

        record = self.create(kind, source_route, cancel=cancel_worker, **metadata)
        operation_id = record.id
        started_signal = getattr(worker, "started", None)
        if hasattr(started_signal, "connect"):
            started_signal.connect(lambda: self.start(operation_id))

        def on_progress(*args) -> None:
            numbers = [value for value in args if isinstance(value, int) and not isinstance(value, bool)]
            text = next((value for value in args if isinstance(value, str)), None)
            latest = self.get(operation_id) or record
            payload = args[0] if len(args) == 1 else None
            if payload is not None and not numbers and not isinstance(payload, (str, bytes)):
                getter = payload.get if isinstance(payload, dict) else lambda key, default=None: getattr(payload, key, default)
                current_value = getter("current", getter("done", latest.current))
                total_value = getter("total", latest.total)
                if isinstance(current_value, int):
                    numbers.append(current_value)
                if isinstance(total_value, int):
                    numbers.append(total_value)
                text = getter("message", getter("detail", text))
                stage = getter("stage", getter("phase", None))
            else:
                stage = None
            current = numbers[0] if numbers else latest.current
            total = numbers[1] if len(numbers) > 1 else latest.total
            self.progress(operation_id, current, total, stage=stage, message=text)

        for signal_name in ("progress", "progress_update", "progress_changed", "progressChanged"):
            signal = getattr(worker, signal_name, None)
            if hasattr(signal, "connect"):
                try:
                    signal.connect(on_progress)
                except (TypeError, RuntimeError):
                    pass

        def on_error(*args) -> None:
            error = next((str(value) for value in args if value), "Operation failed")
            self.finish(operation_id, OperationStatus.FAILED, error_summary=error)

        for signal_name in ("error", "failed"):
            signal = getattr(worker, signal_name, None)
            if hasattr(signal, "connect"):
                try:
                    signal.connect(on_error)
                except (TypeError, RuntimeError):
                    pass

        def on_result(*args) -> None:
            latest = self.get(operation_id)
            if latest is None or latest.status in TERMINAL_STATUSES:
                return
            payload = args[0] if len(args) == 1 else None
            payload_status = ""
            payload_error = ""
            payload_output = ""
            if payload is not None and not isinstance(payload, (str, bytes, bool, int)):
                getter = payload.get if isinstance(payload, dict) else lambda key, default=None: getattr(payload, key, default)
                raw_status = getter("status", "")
                payload_status = str(getattr(raw_status, "value", raw_status) or "").lower()
                payload_error = str(getter("error", getter("error_summary", "")) or "")
                payload_output = str(
                    getter("output_path", getter("run_dir", getter("workbook_path", ""))) or ""
                )
            if args and isinstance(args[0], bool) and not args[0]:
                terminal = OperationStatus.FAILED
            elif any(word in payload_status for word in ("fail", "error")):
                terminal = OperationStatus.FAILED
            elif any(word in payload_status for word in ("cancel", "discard", "stop")):
                terminal = OperationStatus.CANCELLED
            elif "partial" in payload_status or "incomplete" in payload_status:
                terminal = OperationStatus.PARTIAL
            elif latest.kind == OperationKind.BATCH_VARIANTS and len(args) >= 2:
                succeeded, total = int(args[0]), int(args[1])
                terminal = (
                    OperationStatus.SUCCEEDED
                    if total == 0 or succeeded >= total
                    else OperationStatus.PARTIAL
                    if succeeded > 0
                    else OperationStatus.FAILED
                )
            elif latest.kind == OperationKind.SPEC_SCANNER and len(args) >= 3:
                handled, errors = int(args[0]) + int(args[1]), int(args[2])
                terminal = (
                    OperationStatus.SUCCEEDED
                    if errors == 0
                    else OperationStatus.PARTIAL
                    if handled > 0
                    else OperationStatus.FAILED
                )
            elif len(args) >= 2 and all(
                isinstance(value, int) and not isinstance(value, bool) for value in args[:2]
            ):
                succeeded, errors = int(args[0]), int(args[1])
                terminal = (
                    OperationStatus.SUCCEEDED
                    if errors == 0
                    else OperationStatus.PARTIAL
                    if succeeded > 0
                    else OperationStatus.FAILED
                )
            else:
                terminal = OperationStatus.SUCCEEDED
            text = next((value for value in args if isinstance(value, str)), None)
            self.finish(
                operation_id,
                terminal,
                message=text if terminal != OperationStatus.FAILED else None,
                error_summary=(payload_error or text) if terminal == OperationStatus.FAILED else None,
                output_path=payload_output or None,
            )

        for signal_name in ("completed", "done", "succeeded"):
            signal = getattr(worker, signal_name, None)
            if hasattr(signal, "connect"):
                try:
                    signal.connect(on_result)
                except (TypeError, RuntimeError):
                    pass

        cancelled_signal = getattr(worker, "cancelled", None)
        if hasattr(cancelled_signal, "connect"):
            try:
                cancelled_signal.connect(
                    lambda *args: self.finish(operation_id, OperationStatus.CANCELLED)
                )
            except (TypeError, RuntimeError):
                pass

        def on_finished(*args) -> None:
            latest = self.get(operation_id)
            if latest is None or latest.status in TERMINAL_STATUSES:
                return
            if latest.status == OperationStatus.STOPPING:
                terminal = OperationStatus.CANCELLED
            elif args and isinstance(args[0], bool) and not args[0]:
                terminal = OperationStatus.FAILED
            else:
                terminal = OperationStatus.SUCCEEDED
            text = next((value for value in args if isinstance(value, str)), None)
            self.finish(operation_id, terminal,
                        message=text if terminal == OperationStatus.SUCCEEDED else None,
                        error_summary=text if terminal == OperationStatus.FAILED else None)

        finished_signal = getattr(worker, "finished", None)
        if hasattr(finished_signal, "connect"):
            try:
                finished_signal.connect(on_finished)
            except (TypeError, RuntimeError):
                pass
        return record

    def diagnostics(self, operation_id: str) -> str:
        record = self.get(operation_id)
        if record is None:
            raise KeyError(f"Unknown operation: {operation_id}")
        payload = {
            "id": record.id, "kind": record.kind.value, "source_route": record.source_route,
            "status": record.status.value,
            "progress": {"current": record.current, "total": record.total},
            "stage": record.stage, "message": record.message, "error": record.error_summary,
            "output_path": record.output_path,
            "resume": {"kind": record.resume_kind, "reference": record.resume_ref},
            "batch_id": record.batch_id, "started_at": record.started_at,
            "updated_at": record.updated_at, "finished_at": record.finished_at,
            "summary": record.summary or {},
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)

    def _emit_changed(self, operation_id: str) -> None:
        self.operationChanged.emit(operation_id)
        self.runningCountChanged.emit(self.running_count())
