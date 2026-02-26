"""Async job queue for CV parsing with progress tracking."""

import threading
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable

from cv_parser.schemas import CVParseResult


class JobStatus(str, Enum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"


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

    @property
    def name(self) -> str:
        return self.path.name


class JobQueue:
    """Thread-safe job queue with worker pool."""

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
        self._api_key: str | None = None
        self._retry_on_validation_error = True
        self._max_retries = 1
        self._two_pass = True
        self._layout = "individual"
        self._format = "JSON"

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
    ) -> None:
        with self._lock:
            self._output_dir = output_dir
            self._provider = provider
            self._model = model
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
        from cv_parser.parser import parse_two_pass
        from cv_parser.providers import get_provider

        MIME = {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".doc": "application/msword",
        }

        while not self._stop.is_set():
            job = None
            with self._lock:
                if self._queue and self._output_dir:
                    job = self._queue.pop(0)
                    job.status = JobStatus.IN_PROGRESS
                    job.phase = "extraction"
                    job.progress = 0.0

            if job is None:
                self._stop.wait(timeout=0.5)
                continue

            try:
                document = job.path.read_bytes()
                suffix = job.path.suffix.lower()
                mime = MIME.get(suffix, "application/pdf")
                prov = get_provider(
                    provider=self._provider,
                    model=self._model,
                    api_key=self._api_key,
                )

                from cv_parser.parser import estimate_tokens_from_bytes, estimate_tokens_from_text

                total_est = 2 * estimate_tokens_from_bytes(len(document))
                phase_tokens = total_est // 2
                tokens_streamed = [0]
                phase = ["extraction"]

                def on_progress(pct: float, ph: str = ""):
                    with self._lock:
                        job.progress = min(100.0, pct)
                        job.phase = ph

                def stream_cb(chunk: str) -> None:
                    tokens_streamed[0] += estimate_tokens_from_text(chunk)
                    if phase[0] == "extraction":
                        pct = 50.0 * min(1.0, tokens_streamed[0] / phase_tokens)
                        on_progress(pct, "extraction")
                    else:
                        pct = 50.0 + 50.0 * min(1.0, tokens_streamed[0] / phase_tokens)
                        on_progress(pct, "classification")

                def on_classification_start() -> None:
                    phase[0] = "classification"
                    tokens_streamed[0] = 0
                    on_progress(50.0, "classification")

                result, _ = parse_two_pass(
                    prov,
                    document,
                    mime,
                    retry_on_validation_error=self._retry_on_validation_error,
                    max_retries=self._max_retries,
                    stream_callback=stream_cb,
                    on_classification_start=on_classification_start,
                )

                with self._lock:
                    job.status = JobStatus.DONE
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
                    job.error = str(e)

    def start(self) -> None:
        """Start worker threads."""
        with self._lock:
            if self._workers:
                return
            self._stop.clear()
            for _ in range(self._num_threads):
                t = threading.Thread(target=self._worker, daemon=True)
                t.start()
                self._workers.append(t)

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
