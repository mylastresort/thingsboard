import threading
from typing import Dict

from src.logger import logger

# Global job registry: {model_id: {status, thread, start_time, etc}}
active_jobs: Dict[str, dict] = {}
job_lock = threading.Lock()


def get_job_status(model_id: str | None = None, rand_id: int | None = None) -> dict | None:
    """Get status of jobs"""
    logger.info(
        f"{rand_id} - Acquiring job_lock for model_id={model_id}", extra={"rand_id": rand_id}
    )
    with job_lock:
        logger.info(f"{rand_id} - Acquired job_lock", extra={"rand_id": rand_id})
        if model_id and model_id in active_jobs:
            return active_jobs[model_id]
    return None


def get_or_create_job_status(
    model_id: str,
    merge_object=None,
    rand_id: int | str | None = None,
) -> dict:
    """Get or create job status entry"""
    logger.info(
        f"{rand_id} - Acquiring job_lock for model_id={model_id}", extra={"rand_id": rand_id}
    )
    with job_lock:
        logger.info(f"{rand_id} - Acquired job_lock", extra={"rand_id": rand_id})
        if model_id not in active_jobs:
            active_jobs[model_id] = {
                "status": "initialized",
                "start_time": None,
                "thread": None,
                "model_id": model_id,
                "read_lock": threading.Lock(),
                "job_status_subscribers": set(),
            }
        if merge_object and isinstance(merge_object, dict):
            active_jobs[model_id].update(merge_object)
        return active_jobs[model_id]
