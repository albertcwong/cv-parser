"""Tests for job queue."""

from pathlib import Path

import pytest

from cv_parser.jobs import Job, JobQueue, JobStatus


def test_job_name():
    """Job.name returns path stem."""
    j = Job(path=Path("/foo/bar.pdf"), bytes=1000)
    assert j.name == "bar.pdf"


def test_job_queue_enqueue(tmp_path):
    """enqueue creates jobs and adds to queue."""
    (tmp_path / "a.pdf").write_bytes(b"x")
    (tmp_path / "b.pdf").write_bytes(b"y")
    q = JobQueue(num_threads=1)
    q.configure(
        output_dir=tmp_path,
        provider="openai",
        model=None,
        api_key=None,
    )
    jobs = q.enqueue([tmp_path / "a.pdf", tmp_path / "b.pdf"])
    assert len(jobs) == 2
    assert all(j.status == JobStatus.QUEUED for j in jobs)
    assert q.get_queued() == jobs
    assert q.get_all() == jobs
