from datetime import datetime, timezone
from threading import RLock
from typing import Optional
from uuid import uuid4

from app.models.domain import FailedJob
from app.repositories.interfaces.failed_job_repository import (
    CreateFailedJobInput,
    FailedJobRepository,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class InMemoryFailedJobRepository(FailedJobRepository):
    def __init__(self, initial: Optional[list[FailedJob]] = None) -> None:
        self._lock = RLock()
        self._jobs: list[FailedJob] = [
            j.model_copy(deep=True) for j in (initial or [])
        ]

    def create(self, data: CreateFailedJobInput) -> FailedJob:
        job = FailedJob(
            id=str(uuid4()),
            task_name=data.task_name,
            args_json=data.args_json,
            error_message=data.error_message,
            traceback=data.traceback[:4096],
            attempts=data.attempts,
            queue=data.queue,
            created_at=_now_iso(),
            resolved_at=None,
        )
        with self._lock:
            self._jobs.insert(0, job.model_copy(deep=True))
        return job

    def list_all(self, limit: int = 50) -> list[FailedJob]:
        with self._lock:
            return [j.model_copy(deep=True) for j in self._jobs[:limit]]

    def find_by_id(self, job_id: str) -> Optional[FailedJob]:
        with self._lock:
            for j in self._jobs:
                if j.id == job_id:
                    return j.model_copy(deep=True)
            return None

    def mark_resolved(self, job_id: str) -> Optional[FailedJob]:
        with self._lock:
            for j in self._jobs:
                if j.id == job_id:
                    j.resolved_at = _now_iso()
                    return j.model_copy(deep=True)
            return None
