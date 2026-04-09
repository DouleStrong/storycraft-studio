from __future__ import annotations

from typing import Callable


class TaskQueue:
    def enqueue(self, job_id: int) -> None:
        raise NotImplementedError


class InlineTaskQueue(TaskQueue):
    def __init__(self, runner: Callable[[int], None]):
        self.runner = runner

    def enqueue(self, job_id: int) -> None:
        self.runner(job_id)


class RQTaskQueue(TaskQueue):
    def __init__(self, *, redis_url: str, queue_name: str):
        self.redis_url = redis_url
        self.queue_name = queue_name

    def enqueue(self, job_id: int) -> None:
        from redis import Redis
        from rq import Queue

        connection = Redis.from_url(self.redis_url)
        queue = Queue(self.queue_name, connection=connection)
        queue.enqueue("app.worker.run_generation_job", job_id)
