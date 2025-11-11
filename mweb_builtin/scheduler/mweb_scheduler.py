import threading
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
from redis import Redis
from mw_common import Console
from mweb import MWebBase
from ..common.mweb_builtin_config import MWebBuiltinConfig


class MWebScheduler:
    config: MWebBuiltinConfig = None
    _instance = None
    _lock = threading.Lock()
    _started: bool = False
    _initialized: bool = False

    def __new__(cls, config: MWebBuiltinConfig):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, config):
        if self._initialized:
            return
        self.config = config
        self._scheduler = self._create_scheduler()
        self._redis_client = self._create_redis_client()
        self._started = False
        self._initialized = True

    def _create_scheduler(self):
        job_store = self._create_job_store()
        job_defaults = {
            "coalesce": self.config.SCHEDULER_JOB_COALESCE,
            "max_instances": self.config.SCHEDULER_JOB_MAX_INSTANCES,
        }

        scheduler = AsyncIOScheduler(
            jobstores=job_store,
            job_defaults=job_defaults,
            timezone=self.config.SCHEDULER_TIMEZONE,
        )
        scheduler.add_listener(self._listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
        return scheduler

    def _create_job_store(self):
        storage = self.config.SCHEDULER_STORAGE.lower()
        if storage == "redis":
            return {"default": RedisJobStore(host=self.config.SCHEDULER_STORAGE_CONNECTION_URI)}
        elif storage == "sqlalchemy":
            return {"default": SQLAlchemyJobStore(url=self.config.SCHEDULER_STORAGE_CONNECTION_URI)}
        else:
            return {"default": MemoryJobStore()}

    def _create_redis_client(self):
        if "redis" in self.config.SCHEDULER_STORAGE.lower():
            return Redis.from_url(self.config.SCHEDULER_STORAGE_CONNECTION_URI)
        return None

    def _listener(self, event):
        if event.exception:
            Console.log(f"MWeb Scheduler Job {event.job_id} failed", system_log=True)

    def _acquire_lock(self):
        if not self._redis_client:
            return True  # no redis, assume single-worker mode

        lock_acquired = self._redis_client.set(
            self.config.SCHEDULER_LOCK_KEY,
            "1",
            nx=True,
            ex=self.config.SCHEDULER_LOCK_TIMEOUT,
        )
        return lock_acquired

    def _release_lock(self):
        if self._redis_client:
            self._redis_client.delete(self.config.SCHEDULER_LOCK_KEY)

    def initialize(self, mweb_app: MWebBase):
        mweb_app.before_serving(self.start)

    async def start(self, paused=False):
        if not self._started:
            if not self._acquire_lock():
                Console.log(f"MWeb Scheduler Skipping start — another worker owns the lock", system_log=True)
                return
            Console.log(f"MWeb Scheduler Starting scheduler...", system_log=True)
            self._scheduler.start(paused=paused)
            self._started = True

    def stop(self, wait=False):
        if self._started:
            Console.log(f"MWeb Scheduler Stopping scheduler...", system_log=True)
            self._scheduler.shutdown(wait=wait)
            self._release_lock()
            self._started = False

    def add_interval_job(self, func, job_id: str, hours=0, minutes=0, seconds=0, args=None, kwargs=None):
        job = self._scheduler.add_job(
            func=func,
            trigger="interval",
            id=job_id,
            replace_existing=True,
            hours=hours,
            minutes=minutes,
            seconds=seconds,
            args=args or [],
            kwargs=kwargs or {},
        )
        Console.log(f"MWeb Scheduler Added interval job: {job_id}")
        return job

    def add_cron_job(self, func, job_id: str, hour=None, minute=None, second=None, day=None, args=None, kwargs=None):
        job = self._scheduler.add_job(
            func=func,
            trigger="cron",
            id=job_id,
            replace_existing=True,
            hour=hour,
            minute=minute,
            second=second,
            day=day,
            args=args or [],
            kwargs=kwargs or {},
        )
        Console.log(f"MWeb Scheduler Added cron job: {job_id}")
        return job

    def remove(self, job_id: str):
        self._scheduler.remove_job(job_id)
        Console.log(f"MWeb Scheduler Removed job: {job_id}")

    def list_jobs(self):
        jobs_list = []
        for job in self._scheduler.get_jobs():
            job_data = {
                "id": job.id,
                "name": job.name,
                "next_run": str(job.next_run_time),
                "trigger": str(job.trigger),
                "func": str(job.func_ref),
            }
            jobs_list.append(job_data)
        return jobs_list


mweb_scheduler = MWebScheduler(MWebBuiltinConfig)
