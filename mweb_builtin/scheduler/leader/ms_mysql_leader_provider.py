from sqlalchemy import text
from sqlalchemy.engine import Connection
from .ms_sql_leader_provider import MWebSQLSchedulerLeaderProvider


class MWebMySQLSchedulerLeaderProvider(MWebSQLSchedulerLeaderProvider):

    def _execute_acquire(self, connection: Connection) -> bool:
        acquired = connection.execute(
            text(
                "SELECT GET_LOCK(:lock_key, 0)"
            ),
            {
                "lock_key": self.lock_key,
            },
        ).scalar_one()

        return acquired == 1

    def _execute_release(self, connection: Connection) -> None:
        connection.execute(
            text(
                "SELECT RELEASE_LOCK(:lock_key)"
            ),
            {
                "lock_key": self.lock_key,
            },
        ).scalar_one()
