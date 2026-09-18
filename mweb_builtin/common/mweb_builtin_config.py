class MWebBuiltinConfig:

    # MWeb Scheduler Configuration
    ENABLE_SCHEDULER: bool = False
    SCHEDULER_STORAGE: str = "sqlalchemy"
    SCHEDULER_STORAGE_CONNECTION_URI: str = "sqlite:///mweb_scheduler.sqlite3"  # SQLAlchemy or Radis Connection URL

    SCHEDULER_THREAD_POOL_SIZE: int = 9
    # Job defaults
    SCHEDULER_JOB_COALESCE: bool = False
    SCHEDULER_JOB_MAX_INSTANCES: int = 3
    # Redis-based distributed lock
    SCHEDULER_LOCK_KEY: str = "mweb:scheduler:lock"
    SCHEDULER_LOCK_TIMEOUT: int = 60  # seconds
    SCHEDULER_TIMEZONE: str = "Asia/Dhaka"

    SCHEDULER_JOB_MISFIRE_GRACE_TIME: int = 60
    SCHEDULER_LEADER_CHECK_INTERVAL: int = 5

    # Enable when running multiple application workers.
    # Supported distributed databases:
    # PostgreSQL
    # MySQL
    # MariaDB
    SCHEDULER_MULTI_WORKER: bool = True