"""Async job queue for CV parsing with progress tracking."""

import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable

from cv_parser.schemas import CVParseResult

_WORKER_THREAD_NAMES: set[str] = set()


class _MutedStream:
    """Stream that discards output from job worker threads."""

    def __init__(self, real):
        self._real = real

    def write(self, s: str) -> int:
        if threading.current_thread().name in _WORKER_THREAD_NAMES:
            return len(s)
        return self._real.write(s)

    def flush(self) -> None:
        if threading.current_thread().name not in _WORKER_THREAD_NAMES:
            self._real.flush()

    def __getattr__(self, name):
        return getattr(self._real, name)


class JobStatus(str, Enum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"


def _now() -> datetime:
    return datetime.now().astimezone()


def _format_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _format_runtime(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    m, s = divmod(int(seconds), 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m {s}s"


@dataclass
class Job:
    path: Path
    bytes: int
    status: JobStatus = JobStatus.QUEUED
    progress: float = 0.0
    result: CVParseResult | None = None
    error: str | None = None
    phase: str = ""
    batch_id: int = 0
    start_time: datetime | None = None
    end_time: datetime | None = None

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def runtime_seconds(self) -> float | None:
        if self.start_time is None:
            return None
        end = self.end_time or _now()
        return (end - self.start_time).total_seconds()


class JobQueue:
    """Thread-safe job queue with worker pool."""

    _streams_muted = False

    def __init__(self, num_threads: int = 2):
        self._jobs: list[Job] = []
        self._lock = threading.Lock()
        self._num_threads = num_threads
        self._workers: list[threading.Thread] = []
        self._stop = threading.Event()
        self._queue: list[Job] = []
        self._output_dir: Path | None = None
        self._provider: str | None = None
        self._model: str | None = None
        self._model_extraction: str | None = None
        self._model_classification: str | None = None
        self._api_key: str | None = None
        self._retry_on_validation_error = True
        self._max_retries = 1
        self._two_pass = True
        self._layout = "individual"
        self._format = "JSON"
        self._temp_dir: Path | None = None
        self._use_extracted_text = False

    def configure(
        self,
        output_dir: Path,
        provider: str,
        model: str | None,
        api_key: str | None,
        retry_on_validation_error: bool = True,
        max_retries: int = 1,
        two_pass: bool = True,
        layout: str = "individual",
        format: str = "JSON",
        temp_dir: Path | None = None,
        use_extracted_text: bool = False,
        model_extraction: str | None = None,
        model_classification: str | None = None,
    ) -> None:
        with self._lock:
            self._output_dir = output_dir
            self._temp_dir = temp_dir
            self._use_extracted_text = use_extracted_text
            self._provider = provider
            self._model = model
            self._model_extraction = model_extraction
            self._model_classification = model_classification
            self._api_key = api_key
            self._retry_on_validation_error = retry_on_validation_error
            self._max_retries = max_retries
            self._two_pass = two_pass
            self._layout = layout
            self._format = format.upper()

    _next_batch_id = 0

    def enqueue(self, paths: list[Path]) -> list[Job]:
        """Add paths to queue. Returns created jobs."""
        jobs = []
        with self._lock:
            JobQueue._next_batch_id += 1
            batch_id = JobQueue._next_batch_id
            for p in paths:
                if not p.exists():
                    continue
                job = Job(path=p, bytes=p.stat().st_size, batch_id=batch_id)
                self._jobs.append(job)
                self._queue.append(job)
                jobs.append(job)
        return jobs

    def get_all(self) -> list[Job]:
        with self._lock:
            return list(self._jobs)

    def get_queued(self) -> list[Job]:
        with self._lock:
            return [j for j in self._jobs if j.status == JobStatus.QUEUED]

    def get_in_progress(self) -> list[Job]:
        with self._lock:
            return [j for j in self._jobs if j.status == JobStatus.IN_PROGRESS]

    def get_done(self) -> list[Job]:
        with self._lock:
            return [j for j in self._jobs if j.status == JobStatus.DONE]

    def get_failed(self) -> list[Job]:
        with self._lock:
            return [j for j in self._jobs if j.status == JobStatus.FAILED]

    def _worker(self) -> None:
        _WORKER_THREAD_NAMES.add(threading.current_thread().name)
        try:
            self._worker_loop()
        finally:
            _WORKER_THREAD_NAMES.discard(threading.current_thread().name)

    def _worker_loop(self) -> None:
        from cv_parser.line_parser import parse_cv_from_lines

        while not self._stop.is_set():
            job = None
            with self._lock:
                if self._queue and self._output_dir:
                    job = self._queue.pop(0)
                    job.status = JobStatus.IN_PROGRESS
                    job.start_time = _now()
                    job.phase = "augment"
                    job.progress = 0.0

            if job is None:
                self._stop.wait(timeout=0.5)
                continue

            try:
                with self._lock:
                    job.progress = 10.0
                result = parse_cv_from_lines(
                    job.path,
                    provider=self._provider,
                    model=self._model,
                    api_key=self._api_key,
                )

                with self._lock:
                    job.status = JobStatus.DONE
                    job.end_time = _now()
                    job.progress = 100.0
                    job.phase = ""
                    job.result = result

                from cv_parser.combiner import combine_to_flat
                from cv_parser.export import export_csv, export_json
                layout = self._layout
                fmt = self._format
                out_dir = self._output_dir

                if layout and "combined" in layout.lower():
                    done = [j for j in self._jobs if j.batch_id == job.batch_id and j.status == JobStatus.DONE]
                    in_progress = [j for j in self._jobs if j.batch_id == job.batch_id and j.status == JobStatus.IN_PROGRESS]
                    queued = [j for j in self._jobs if j.batch_id == job.batch_id and j.status == JobStatus.QUEUED]
                    if not in_progress and not queued:
                        all_results = [j.result for j in done if j.result is not None]
                        if all_results:
                            ext = ".csv" if fmt == "CSV" else ".json"
                            out_path = out_dir / f"combined{ext}"
                            if fmt == "CSV":
                                export_csv(combine_to_flat(all_results), out_path)
                            else:
                                export_json(all_results, out_path)
                else:
                    ext = ".csv" if fmt == "CSV" else ".json"
                    out_path = out_dir / f"{job.path.stem}{ext}"
                    if fmt == "CSV":
                        export_csv(combine_to_flat([result]), out_path)
                    else:
                        export_json(result, out_path)

            except Exception as e:
                with self._lock:
                    job.status = JobStatus.FAILED
                    job.end_time = _now()
                    job.error = str(e)

    def start(self) -> None:
        """Start worker threads."""
        with self._lock:
            if self._workers:
                return
            self._stop.clear()
            self._install_muted_streams()
            for i in range(self._num_threads):
                t = threading.Thread(target=self._worker, daemon=True, name=f"cv_parser_worker_{i}")
                t.start()
                self._workers.append(t)

    def _install_muted_streams(self) -> None:
        """Replace stdout/stderr with thread-aware mutes (once)."""
        if JobQueue._streams_muted:
            return
        JobQueue._streams_muted = True
        sys.stdout = _MutedStream(sys.stdout)
        sys.stderr = _MutedStream(sys.stderr)

    def stop(self) -> None:
        self._stop.set()
        for t in self._workers:
            t.join(timeout=2.0)
        self._workers.clear()

    def set_threads(self, n: int) -> None:
        with self._lock:
            self._num_threads = max(1, n)


# Global singleton for interactive use
_queue: JobQueue | None = None


def get_queue(threads: int | None = None) -> JobQueue:
    global _queue
    if _queue is None:
        from cv_parser.config import get_threads
        n = threads if threads is not None else get_threads()
        _queue = JobQueue(num_threads=n)
        _queue.start()
    return _queue
