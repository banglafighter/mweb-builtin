from sqlalchemy.engine import make_url

from .ms_mysql_leader_provider import MWebMySQLSchedulerLeaderProvider
from .ms_postgresql_leader_provider import MWebPostgreSQLSchedulerLeaderProvider
from .ms_single_leader_provider import MWebSingleSchedulerLeaderProvider
from .ms_sqlite_leader_provider import MWebSQLiteSchedulerLeaderProvider


class MWebSchedulerLeaderProviderFactory:

    @staticmethod
    def create(config) -> MWebSchedulerLeaderProvider:
        if not config.SCHEDULER_MULTI_WORKER:
            return MWebSingleSchedulerLeaderProvider()

        if config.SCHEDULER_STORAGE.lower() != "sqlalchemy":
            raise RuntimeError(
                "MWeb Scheduler multi-worker mode requires "
                "SCHEDULER_STORAGE='sqlalchemy'."
            )

        url = make_url(
            config.SCHEDULER_STORAGE_CONNECTION_URI
        )

        backend = url.get_backend_name()

        if backend == "sqlite":
            return MWebSQLiteSchedulerLeaderProvider(
                lock_key=config.SCHEDULER_LOCK_KEY,
            )

        if backend == "postgresql":
            return MWebPostgreSQLSchedulerLeaderProvider(
                connection_uri=config.SCHEDULER_STORAGE_CONNECTION_URI,
                lock_key=config.SCHEDULER_LOCK_KEY,
            )

        if backend in {"mysql", "mariadb"}:
            return MWebMySQLSchedulerLeaderProvider(
                connection_uri=config.SCHEDULER_STORAGE_CONNECTION_URI,
                lock_key=config.SCHEDULER_LOCK_KEY,
            )

        raise RuntimeError(
            f"MWeb Scheduler multi-worker leader election "
            f"is not supported for SQLAlchemy backend '{backend}'. "
            f"Currently supported: PostgreSQL, MySQL and MariaDB."
        )