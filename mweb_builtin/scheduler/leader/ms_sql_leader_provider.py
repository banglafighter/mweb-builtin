import asyncio
from abc import abstractmethod
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import Connection
from .ms_leader_provider import MWebSchedulerLeaderProvider


class MWebSQLSchedulerLeaderProvider(MWebSchedulerLeaderProvider):

    def __init__(self, connection_uri: str, lock_key: str):
        self.connection_uri = connection_uri
        self.lock_key = lock_key

        self._engine: Engine | None = None
        self._connection: Connection | None = None

    def _create_engine(self) -> None:
        if self._engine is not None:
            return

        self._engine = create_engine(
            self.connection_uri,
            pool_pre_ping=True,
            isolation_level="AUTOCOMMIT",
        )

    def _acquire_sync(self) -> bool:
        if self._connection is not None:
            return True

        self._create_engine()

        if self._engine is None:
            raise RuntimeError(
                "MWeb Scheduler leader engine was not created."
            )

        connection = self._engine.connect()

        try:
            acquired = self._execute_acquire(
                connection
            )

            if acquired:
                self._connection = connection
                return True

            connection.close()
            return False

        except Exception:
            connection.close()
            raise

    async def acquire(self) -> bool:
        return await asyncio.to_thread(
            self._acquire_sync
        )

    def _alive_sync(self) -> bool:
        connection = self._connection

        if connection is None:
            return False

        try:
            connection.execute(
                text("SELECT 1")
            ).scalar_one()

            return True

        except Exception:
            return False

    async def alive(self) -> bool:
        return await asyncio.to_thread(
            self._alive_sync
        )

    def _release_sync(self) -> None:
        connection = self._connection

        if connection is None:
            return

        self._connection = None

        try:
            self._execute_release(
                connection
            )

        except Exception:
            pass

        finally:
            try:
                connection.close()
            except Exception:
                pass

    async def release(self) -> None:
        await asyncio.to_thread(
            self._release_sync
        )

    def _close_sync(self) -> None:
        self._release_sync()

        engine = self._engine
        self._engine = None

        if engine is not None:
            engine.dispose()

    async def close(self) -> None:
        await asyncio.to_thread(
            self._close_sync
        )

    @abstractmethod
    def _execute_acquire(self, connection: Connection) -> bool:
        raise NotImplementedError

    @abstractmethod
    def _execute_release(self, connection: Connection) -> None:
        raise NotImplementedError