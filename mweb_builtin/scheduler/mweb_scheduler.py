import asyncio
from datetime import datetime
import inspect
from collections.abc import Callable
from apscheduler.job import Job
import threading
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.jobstores.memory import MemoryJobStore
from sqlalchemy.engine import make_url
from apscheduler.events import (
    EVENT_JOB_ERROR,
    EVENT_JOB_MISSED,
    JobExecutionEvent,
)
from apscheduler.executors.asyncio import AsyncIOExecutor
from mw_common import Console, MwException
from .leader.ms_factory_leader_provider import MWebSchedulerLeaderProviderFactory
from .leader.ms_leader_provider import MWebSchedulerLeaderProvider
from ..common.mweb_builtin_config import MWebBuiltinConfig
from apscheduler.executors.pool import ThreadPoolExecutor


class MWebScheduler:
    config: type[MWebBuiltinConfig]
    _instance: MWebScheduler | None = None
    _instance_lock = threading.Lock()

    def __new__(cls, config):
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False

            return cls._instance

    def __init__(self, config):
        if self._initialized:
            return

        self.config = config

        self._scheduler: AsyncIOScheduler | None = None
        self._leader_provider: MWebSchedulerLeaderProvider | None = None
        self._leader_task: asyncio.Task[None] | None = None

        self._registered_jobs: dict[str, dict] = {}

        self._started: bool = False
        self._is_leader: bool = False
        self._initialized: bool = True

    def initialize(self, mweb_app, enable: bool = False) -> None:
        if not enable:
            return

        self._validate_configuration()
        self._leader_provider = (
            MWebSchedulerLeaderProviderFactory.create(
                self.config
            )
        )

        mweb_app.before_serving(
            self.start
        )

        mweb_app.after_serving(
            self.stop
        )

    def _validate_configuration(self) -> None:
        storage = (
            self.config.SCHEDULER_STORAGE
            .strip()
            .lower()
        )

        if storage not in {"memory", "sqlalchemy"}:
            raise MwException(
                "SCHEDULER_STORAGE must be "
                "'memory' or 'sqlalchemy'."
            )

        if storage == "sqlalchemy":
            connection_uri = (
                self.config
                .SCHEDULER_STORAGE_CONNECTION_URI
            )

            if not connection_uri:
                raise MwException(
                    "SCHEDULER_STORAGE_CONNECTION_URI "
                    "is required for SQLAlchemy storage."
                )

            make_url(
                connection_uri
            )

        if (self.config.SCHEDULER_MULTI_WORKER and storage == "memory"):
            raise MwException(
                "Memory scheduler storage cannot be used"
                "with SCHEDULER_MULTI_WORKER=True."
            )

        if self.config.SCHEDULER_THREAD_POOL_SIZE < 1:
            raise MwException("SCHEDULER_THREAD_POOL_SIZE must be greater than 0.")

        if self.config.SCHEDULER_JOB_MAX_INSTANCES < 1:
            raise MwException("SCHEDULER_JOB_MAX_INSTANCES must be greater than 0.")

        if self.config.SCHEDULER_JOB_MISFIRE_GRACE_TIME < 1:
            raise MwException("SCHEDULER_JOB_MISFIRE_GRACE_TIME must be greater than 0.")

        if self.config.SCHEDULER_LEADER_CHECK_INTERVAL < 1:
            raise MwException("SCHEDULER_LEADER_CHECK_INTERVAL must be greater than 0.")

        if not self.config.SCHEDULER_LOCK_KEY.strip():
            raise MwException("SCHEDULER_LOCK_KEY cannot be empty.")

    def _create_job_store(self) -> dict:
        storage = (self.config.SCHEDULER_STORAGE.strip().lower())

        if storage == "memory":
            return {
                "default": MemoryJobStore(),
            }

        return {
            "default": SQLAlchemyJobStore(
                url=self.config.SCHEDULER_STORAGE_CONNECTION_URI,
                engine_options={
                    "pool_pre_ping": True,
                },
            ),
        }

    def _create_scheduler(self) -> AsyncIOScheduler:
        scheduler = AsyncIOScheduler(
            jobstores=self._create_job_store(),
            executors={
                "default": AsyncIOExecutor(),
                "threadpool": ThreadPoolExecutor(
                    max_workers=(
                        self.config
                        .SCHEDULER_THREAD_POOL_SIZE
                    ),
                ),
            },
            job_defaults={
                "coalesce": (
                    self.config
                    .SCHEDULER_JOB_COALESCE
                ),
                "max_instances": (
                    self.config
                    .SCHEDULER_JOB_MAX_INSTANCES
                ),
                "misfire_grace_time": (
                    self.config
                    .SCHEDULER_JOB_MISFIRE_GRACE_TIME
                ),
            },
            timezone=self.config.SCHEDULER_TIMEZONE,
        )

        scheduler.add_listener(
            self._listener,
            EVENT_JOB_ERROR | EVENT_JOB_MISSED,
        )
        return scheduler

    async def start(self, paused: bool = False) -> None:
        if self._started:
            return

        self._started = True

        if not self.config.SCHEDULER_MULTI_WORKER:
            await self._become_leader(
                paused=paused
            )

            return

        self._leader_task = asyncio.create_task(
            self._leader_loop(
                paused=paused
            ),
            name="mweb-scheduler-leader",
        )

    async def stop(self, wait: bool = False) -> None:
        if not self._started:
            return

        self._started = False

        leader_task = self._leader_task
        self._leader_task = None

        if leader_task is not None:
            leader_task.cancel()

            try:
                await leader_task

            except asyncio.CancelledError:
                pass

        await self._relinquish_leader(
            wait=wait
        )

        if self._leader_provider is not None:
            await self._leader_provider.close()

        Console.log(
            "MWeb Scheduler stopped",
            system_log=True,
        )

    # ============================================================
    # Leader Election
    # ============================================================

    async def _leader_loop(self, paused: bool) -> None:
        try:
            while self._started:
                try:
                    if not self._is_leader:
                        if self._leader_provider is None:
                            raise RuntimeError(
                                "MWeb Scheduler leader provider "
                                "is not initialized."
                            )

                        acquired = (
                            await self
                            ._leader_provider
                            .acquire()
                        )

                        if acquired:
                            await self._become_leader(
                                paused=paused
                            )

                    else:
                        if self._leader_provider is None:
                            raise RuntimeError(
                                "MWeb Scheduler leader provider "
                                "is not initialized."
                            )

                        alive = (
                            await self
                            ._leader_provider
                            .alive()
                        )

                        if not alive:
                            Console.log(
                                "MWeb Scheduler lost leadership",
                                system_log=True,
                            )

                            await self._relinquish_leader(
                                wait=False
                            )

                except asyncio.CancelledError:
                    raise

                except Exception as exc:
                    Console.log(
                        f"MWeb Scheduler leader election error: {exc}",
                        system_log=True,
                    )

                    await self._relinquish_leader(
                        wait=False
                    )

                await asyncio.sleep(
                    self.config
                    .SCHEDULER_LEADER_CHECK_INTERVAL
                )

        except asyncio.CancelledError:
            raise

    async def _become_leader(self, paused: bool = False) -> None:
        if self._is_leader:
            return

        try:
            scheduler = self._create_scheduler()

            scheduler.start(
                paused=paused
            )

            self._scheduler = scheduler
            self._is_leader = True

            self._install_registered_jobs()

            Console.log(
                "MWeb Scheduler became leader",
                system_log=True,
            )

        except Exception:
            self._scheduler = None
            self._is_leader = False

            if self._leader_provider is not None:
                await self._leader_provider.release()

            raise

    async def _relinquish_leader(self, wait: bool = False) -> None:
        scheduler = self._scheduler

        self._scheduler = None
        self._is_leader = False

        if scheduler is not None:
            try:
                if scheduler.running:
                    scheduler.shutdown(
                        wait=wait
                    )

            except Exception as exc:
                Console.log(
                    f"MWeb Scheduler shutdown error: {exc}",
                    system_log=True,
                )

        if self._leader_provider is not None:
            await self._leader_provider.release()

    # ============================================================
    # Job Registration
    # ============================================================

    def _resolve_executor(self, func: Callable, executor: str | None) -> str:
        if executor is not None:
            return executor

        if inspect.iscoroutinefunction(func):
            return "default"

        return "threadpool"

    def add_job(
            self,
            func: Callable,
            trigger,
            job_id: str,
            args: list | None = None,
            kwargs: dict | None = None,
            replace_existing: bool = True,
            executor: str | None = None,
            **trigger_args,
    ) -> Job | None:
        definition = {
            "func": func,
            "trigger": trigger,
            "id": job_id,
            "args": args or [],
            "kwargs": kwargs or {},
            "replace_existing": replace_existing,
            "executor": self._resolve_executor(
                func,
                executor,
            ),
            **trigger_args,
        }

        self._registered_jobs[job_id] = definition

        Console.log(
            f"MWeb Scheduler registered job: {job_id}"
        )

        if (
                self._scheduler is not None
                and self._is_leader
        ):
            return self._scheduler.add_job(
                **definition
            )

        return None

    def add_interval_job(
            self,
            func: Callable,
            job_id: str,
            hours: int = 0,
            minutes: int = 0,
            seconds: int = 0,
            args: list | None = None,
            kwargs: dict | None = None,
            replace_existing: bool = True,
            executor: str | None = None,
    ) -> Job | None:

        if (hours <= 0 and minutes <= 0 and seconds <= 0):
            raise MwException(
                "Interval job requires hours, minutes "
                "or seconds greater than zero."
            )

        return self.add_job(
            func=func,
            trigger="interval",
            job_id=job_id,
            hours=hours,
            minutes=minutes,
            seconds=seconds,
            args=args,
            kwargs=kwargs,
            replace_existing=replace_existing,
            executor=executor,
        )

    def add_cron_job(
            self,
            func: Callable,
            job_id: str,
            year: int | str | None = None,
            month: int | str | None = None,
            day: int | str | None = None,
            week: int | str | None = None,
            day_of_week: int | str | None = None,
            hour: int | str | None = None,
            minute: int | str | None = None,
            second: int | str | None = None,
            args: list | None = None,
            kwargs: dict | None = None,
            replace_existing: bool = True,
            executor: str | None = None
    ) -> Job | None:

        return self.add_job(
            func=func,
            trigger="cron",
            job_id=job_id,
            year=year,
            month=month,
            day=day,
            week=week,
            day_of_week=day_of_week,
            hour=hour,
            minute=minute,
            second=second,
            args=args,
            kwargs=kwargs,
            replace_existing=replace_existing,
            executor=executor,
        )

    def add_date_job(
            self,
            func: Callable,
            job_id: str,
            run_date: datetime | str | None = None,
            args: list | None = None,
            kwargs: dict | None = None,
            replace_existing: bool = True,
            executor: str | None = None,
    ) -> Job | None:
        return self.add_job(
            func=func,
            trigger="date",
            job_id=job_id,
            run_date=run_date,
            args=args,
            kwargs=kwargs,
            replace_existing=replace_existing,
            executor=executor,
        )

    def _install_registered_jobs(self) -> None:
        scheduler = self._scheduler
        if scheduler is None:
            return

        for definition in self._registered_jobs.values():
            scheduler.add_job(
                **definition
            )

    def get_job(self, job_id: str) -> Job | None:
        scheduler = self._scheduler

        if scheduler is None:
            return None

        return scheduler.get_job(
            job_id
        )

    def job_exists(self, job_id: str) -> bool:
        if job_id in self._registered_jobs:
            return True

        scheduler = self._scheduler

        if scheduler is None:
            return False

        return scheduler.get_job(
            job_id
        ) is not None

    def remove(self, job_id: str) -> bool:
        registered = (
                self._registered_jobs.pop(
                    job_id,
                    None,
                )
                is not None
        )

        scheduler = self._scheduler

        if scheduler is None:
            return registered

        job = scheduler.get_job(
            job_id
        )

        if job is None:
            return registered

        scheduler.remove_job(
            job_id
        )

        return True

    def remove_all(self) -> None:
        self._registered_jobs.clear()

        if self._scheduler is not None:
            self._scheduler.remove_all_jobs()

    def pause(self, job_id: str) -> Job | None:
        scheduler = self._scheduler

        if scheduler is None:
            return None

        if scheduler.get_job(job_id) is None:
            return None

        return scheduler.pause_job(
            job_id
        )

    def resume(self, job_id: str) -> Job | None:
        scheduler = self._scheduler

        if scheduler is None:
            return None

        if scheduler.get_job(job_id) is None:
            return None

        return scheduler.resume_job(
            job_id
        )

    def reschedule(self, job_id: str, trigger, **trigger_args) -> Job | None:
        scheduler = self._scheduler

        if scheduler is None:
            return None

        if scheduler.get_job(job_id) is None:
            return None

        return scheduler.reschedule_job(
            job_id,
            trigger=trigger,
            **trigger_args,
        )

    def run_now(self, job_id: str) -> Job | None:
        scheduler = self._scheduler

        if scheduler is None:
            return None

        if scheduler.get_job(job_id) is None:
            return None

        return scheduler.modify_job(
            job_id,
            next_run_time=datetime.now(
                scheduler.timezone
            ),
        )

    def list_jobs(self) -> list[dict]:
        scheduler = self._scheduler

        if scheduler is None:
            return []

        return [
            {
                "id": job.id,
                "name": job.name,
                "next_run": (
                    str(job.next_run_time)
                    if job.next_run_time
                    else None
                ),
                "trigger": str(job.trigger),
                "func": job.func_ref,
            }
            for job in scheduler.get_jobs()
        ]

    def status(self) -> dict[str, object]:
        return {
            "started": self._started,
            "leader": self._is_leader,
            "running": (
                    self._scheduler is not None
                    and self._scheduler.running
            ),
            "multi_worker": (
                self.config
                .SCHEDULER_MULTI_WORKER
            ),
            "storage": (
                self.config
                .SCHEDULER_STORAGE
            ),
            "registered_jobs": len(
                self._registered_jobs
            ),
        }

    @property
    def started(self) -> bool:
        return self._started

    @property
    def is_leader(self) -> bool:
        return self._is_leader

    @property
    def running(self) -> bool:
        return (
                self._scheduler is not None
                and self._scheduler.running
        )

    # ============================================================
    # Events
    # ============================================================

    def _listener(self, event: JobExecutionEvent) -> None:
        if event.code == EVENT_JOB_ERROR:
            Console.log(
                f"MWeb Scheduler Job '{event.job_id}' failed: "
                f"{event.exception}",
                system_log=True,
            )

        elif event.code == EVENT_JOB_MISSED:
            Console.log(
                f"MWeb Scheduler Job '{event.job_id}' missed",
                system_log=True,
            )


mweb_scheduler = MWebScheduler(MWebBuiltinConfig)



# ==============================================================================
# MWEB SCHEDULER - USAGE EXAMPLES
# ==============================================================================
#
# Supports:
#   - Interval jobs
#   - Cron jobs
#   - One-time/date jobs
#   - Memory or persistent SQLAlchemy job storage
#   - Multi-worker leader election
#   - SQLite, PostgreSQL, MySQL and MariaDB
#
# ------------------------------------------------------------------------------
# 1. INTERVAL JOB
# ------------------------------------------------------------------------------
#
# async def process_queue():
#     ...
#
# mweb_scheduler.add_interval_job(
#     func=process_queue,
#     job_id="process-queue",
#     minutes=5,
# )
#
# ------------------------------------------------------------------------------
# 2. CRON JOB - EVERY DAY AT 5:00 PM
# ------------------------------------------------------------------------------
#
# async def daily_report():
#     ...
#
# mweb_scheduler.add_cron_job(
#     func=daily_report,
#     job_id="daily-report",
#     hour=17,
#     minute=0,
# )
#
# ------------------------------------------------------------------------------
# 3. CRON JOB - EVERY MONTH ON DAY 1 AT 5:00 PM
# ------------------------------------------------------------------------------
#
# async def monthly_report():
#     ...
#
# mweb_scheduler.add_cron_job(
#     func=monthly_report,
#     job_id="monthly-report",
#     day=1,
#     hour=17,
#     minute=0,
# )
#
# ------------------------------------------------------------------------------
# 4. CRON JOB - EVERY MONDAY AT 8:00 AM
# ------------------------------------------------------------------------------
#   "mon"  = Monday
#   "tue"  = Tuesday
#   "wed"  = Wednesday
#   "thu"  = Thursday
#   "fri"  = Friday
#   "sat"  = Saturday
#   "sun"  = Sunday
#
# mweb_scheduler.add_cron_job(
#     func=weekly_report,
#     job_id="weekly-report",
#     day_of_week="mon",
#     hour=8,
#     minute=0,
# )
#
# ------------------------------------------------------------------------------
# 5. ONE-TIME / DATE JOB
# ------------------------------------------------------------------------------
#
# async def send_notification():
#     ...
#
# mweb_scheduler.add_date_job(
#     func=send_notification,
#     job_id="send-notification",
#     run_date="2026-10-01 10:30:00",
# )
#
# ------------------------------------------------------------------------------
# 6. PASS POSITIONAL ARGUMENTS
# ------------------------------------------------------------------------------
#
# async def send_message(phone: str, message: str):
#     ...
#
# mweb_scheduler.add_interval_job(
#     func=send_message,
#     job_id="send-message",
#     minutes=10,
#     args=[
#         "017XXXXXXXX",
#         "Hello",
#     ],
# )
#
# ------------------------------------------------------------------------------
# 7. PASS KEYWORD ARGUMENTS
# ------------------------------------------------------------------------------
#
# async def send_message(phone: str, message: str):
#     ...
#
# mweb_scheduler.add_interval_job(
#     func=send_message,
#     job_id="send-message",
#     minutes=10,
#     kwargs={
#         "phone": "017XXXXXXXX",
#         "message": "Hello",
#     },
# )
#
# ------------------------------------------------------------------------------
# 8. BLOCKING / SYNCHRONOUS JOB
# ------------------------------------------------------------------------------
#
# def generate_pdf():
#     ...
#
# Sync functions automatically use the scheduler thread pool.
#
# mweb_scheduler.add_interval_job(
#     func=generate_pdf,
#     job_id="generate-pdf",
#     minutes=10,
# )
#
# You can also explicitly select an executor:
#
# mweb_scheduler.add_interval_job(
#     func=generate_pdf,
#     job_id="generate-pdf",
#     minutes=10,
#     executor="threadpool",
# )
#
# ------------------------------------------------------------------------------
# 9. REMOVE JOB
# ------------------------------------------------------------------------------
#
# mweb_scheduler.remove("process-queue")
#
# ------------------------------------------------------------------------------
# 10. PAUSE / RESUME JOB
# ------------------------------------------------------------------------------
#
# mweb_scheduler.pause("process-queue")
#
# mweb_scheduler.resume("process-queue")
#
# ------------------------------------------------------------------------------
# 11. RUN JOB IMMEDIATELY
# ------------------------------------------------------------------------------
#
# mweb_scheduler.run_now("process-queue")
#
# ------------------------------------------------------------------------------
# 12. CHECK JOB
# ------------------------------------------------------------------------------
#
# job = mweb_scheduler.get_job("process-queue")
#
# exists = mweb_scheduler.job_exists("process-queue")
#
# ------------------------------------------------------------------------------
# 13. LIST JOBS
# ------------------------------------------------------------------------------
#
# jobs = mweb_scheduler.list_jobs()
#
# ------------------------------------------------------------------------------
# 14. SCHEDULER STATUS
# ------------------------------------------------------------------------------
#
# status = mweb_scheduler.status()
#
# started = mweb_scheduler.started
# running = mweb_scheduler.running
# leader = mweb_scheduler.is_leader
#
# ------------------------------------------------------------------------------
# 15. DEVELOPMENT - MEMORY STORAGE
# ------------------------------------------------------------------------------
#
# SCHEDULER_STORAGE = "memory"
# SCHEDULER_MULTI_WORKER = False
#
# Jobs are lost when the application stops.
#
# ------------------------------------------------------------------------------
# 16. SQLITE - SINGLE WORKER
# ------------------------------------------------------------------------------
#
# SCHEDULER_STORAGE = "sqlalchemy"
# SCHEDULER_STORAGE_CONNECTION_URI = "sqlite:///mweb_scheduler.sqlite3"
# SCHEDULER_MULTI_WORKER = False
#
# Jobs are persisted in SQLite.
#
# ------------------------------------------------------------------------------
# 17. SQLITE - MULTIPLE WORKERS ON SAME HOST
# ------------------------------------------------------------------------------
#
# SCHEDULER_STORAGE = "sqlalchemy"
# SCHEDULER_STORAGE_CONNECTION_URI = "sqlite:///mweb_scheduler.sqlite3"
# SCHEDULER_MULTI_WORKER = True
#
# SQLite multi-worker leader election uses an operating-system file lock.
#
# IMPORTANT:
#   SQLite multi-worker mode is intended only for workers running on the
#   same host and sharing the same filesystem.
#
# ------------------------------------------------------------------------------
# 18. POSTGRESQL - MULTI-WORKER
# ------------------------------------------------------------------------------
#
# SCHEDULER_STORAGE = "sqlalchemy"
# SCHEDULER_STORAGE_CONNECTION_URI = (
#     "postgresql+psycopg://user:password@localhost/database"
# )
# SCHEDULER_MULTI_WORKER = True
#
# PostgreSQL advisory locking is automatically used for leader election.
#
# ------------------------------------------------------------------------------
# 19. MYSQL / MARIADB - MULTI-WORKER
# ------------------------------------------------------------------------------
#
# SCHEDULER_STORAGE = "sqlalchemy"
# SCHEDULER_STORAGE_CONNECTION_URI = (
#     "mysql+pymysql://user:password@localhost/database"
# )
# SCHEDULER_MULTI_WORKER = True
#
# MySQL/MariaDB named locking is automatically used for leader election.
#
# ------------------------------------------------------------------------------
# MULTI-WORKER BEHAVIOR
# ------------------------------------------------------------------------------
#
# When SCHEDULER_MULTI_WORKER=True:
#
#   Worker 1 ─┐
#   Worker 2 ─┤
#   Worker 3 ─┼── Leader Election
#   Worker 4 ─┘
#                 |
#                 +--> One worker becomes scheduler leader
#                 |
#                 +--> Other workers remain standby
#
# Only the leader starts and runs APScheduler.
#
# If the leader disappears, standby workers continue attempting to acquire
# leadership and one of them becomes the new scheduler leader.
#
# ------------------------------------------------------------------------------
# IMPORTANT NOTES
# ------------------------------------------------------------------------------
#
# - Always use a unique job_id.
#
# - Use importable module-level functions for persistent jobs.
#   Avoid lambda functions, local functions and closures.
#
# - Async functions use AsyncIOExecutor by default.
#
# - Blocking/synchronous functions use the threadpool executor by default.
#
# - replace_existing=True is recommended for application jobs registered
#   during startup when persistent job storage is enabled.
#
# - SCHEDULER_JOB_COALESCE controls whether multiple missed executions are
#   combined into a single execution.
#
# - SCHEDULER_JOB_MAX_INSTANCES controls how many instances of the same job
#   may run concurrently.
#
# - SCHEDULER_JOB_MISFIRE_GRACE_TIME controls how late a job may execute
#   after its scheduled time before APScheduler considers it missed.
#
# - Memory storage should only be used for simple/single-process scenarios.
#
# - SQLite multi-worker mode is single-host only.
#
# - PostgreSQL, MySQL or MariaDB should be used when scheduler coordination
#   is required across multiple application hosts.
#
# - Database-specific leader election is selected automatically from the
#   SQLAlchemy connection URI.
#
# ==============================================================================

