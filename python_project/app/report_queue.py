import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

from .context import ReportContext


@dataclass
class ReportJob:
    id: str
    context: ReportContext
    status: str = "submitted"
    result_path: Optional[str] = None
    error: Optional[str] = None
    future: Optional[Future] = field(default=None, repr=False)


class ReportQueue:
    """
    Simple threaded queue so multiple PDFs can be generated without blocking the UI.
    Replace with a real task runner later if needed.
    """

    def __init__(self, max_workers: int = 2):
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="report")
        self.jobs: Dict[str, ReportJob] = {}
        self.lock = threading.Lock()

    def submit(self, ctx: ReportContext, builder: Callable[[ReportContext], str]) -> str:
        job_id = uuid.uuid4().hex[:12]
        job = ReportJob(id=job_id, context=ctx, status="queued")
        with self.lock:
            self.jobs[job_id] = job
        future = self.executor.submit(self._run_job, job_id, builder)
        job.future = future
        return job_id

    def _run_job(self, job_id: str, builder: Callable[[ReportContext], str]) -> None:
        with self.lock:
            job = self.jobs[job_id]
            job.status = "running"
        try:
            path = builder(job.context)
            with self.lock:
                job.status = "completed"
                job.result_path = str(path)
        except Exception as exc:  # pragma: no cover - runtime error handling
            with self.lock:
                job.status = "failed"
                job.error = str(exc)

    def get(self, job_id: str) -> Optional[ReportJob]:
        with self.lock:
            return self.jobs.get(job_id)
