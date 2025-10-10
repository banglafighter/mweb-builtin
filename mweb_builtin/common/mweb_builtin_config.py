class MWebBuiltinConfig:

    # MWeb Scheduler Configuration
    SCHEDULER_STORAGE: str = "memory"   # "redis", "sqlalchemy", or "memory"
    SCHEDULER_STORAGE_CONNECTION_URI: str = None  # SQLAlchemy or Radis Connection URL
    SCHEDULER_THREAD_POOL_SIZE: int = 9
    # Job defaults
    SCHEDULER_JOB_COALESCE: bool = False
    SCHEDULER_JOB_MAX_INSTANCES: int = 3
    # Redis-based distributed lock
    SCHEDULER_LOCK_KEY: str = "mweb:scheduler:lock"
    SCHEDULER_LOCK_TIMEOUT: int = 60  # seconds
    SCHEDULER_TIMEZONE: str = "Asia/Dhaka"
