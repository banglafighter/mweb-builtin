import hashlib
from sqlalchemy import text
from sqlalchemy.engine import Connection
from .ms_sql_leader_provider import MWebSQLSchedulerLeaderProvider


class MWebPostgreSQLSchedulerLeaderProvider(MWebSQLSchedulerLeaderProvider):

    def _get_lock_id(self) -> int:
        digest = hashlib.sha256(
            self.lock_key.encode("utf-8")
        ).digest()

        return int.from_bytes(
            digest[:8],
            byteorder="big",
            signed=True,
        )

    def _execute_acquire(self, connection: Connection) -> bool:
        acquired = connection.execute(
            text(
                "SELECT pg_try_advisory_lock(:lock_id)"
            ),
            {
                "lock_id": self._get_lock_id(),
            },
        ).scalar_one()

        return bool(acquired)

    def _execute_release(self, connection: Connection) -> None:
        connection.execute(
            text(
                "SELECT pg_advisory_unlock(:lock_id)"
            ),
            {
                "lock_id": self._get_lock_id(),
            },
        ).scalar_one()