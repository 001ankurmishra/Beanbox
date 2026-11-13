from abc import ABC, abstractmethod
from typing import Any, Optional

from app.models.domain import CamelModel, FailedJob


class CreateFailedJobInput(CamelModel):
    task_name: str
    args_json: Any
    error_message: str
    traceback: str
    attempts: int = 1
    queue: str = "default"


class FailedJobRepository(ABC):
    @abstractmethod
    def create(self, data: CreateFailedJobInput) -> FailedJob: ...

    @abstractmethod
    def list_all(self, limit: int = 50) -> list[FailedJob]: ...

    @abstractmethod
    def find_by_id(self, job_id: str) -> Optional[FailedJob]: ...

    @abstractmethod
    def mark_resolved(self, job_id: str) -> Optional[FailedJob]: ...
