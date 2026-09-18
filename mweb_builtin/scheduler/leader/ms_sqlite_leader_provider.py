import asyncio
import sys
import tempfile
from pathlib import Path
from typing import IO
from .ms_leader_provider import MWebSchedulerLeaderProvider


class MWebSQLiteSchedulerLeaderProvider(MWebSchedulerLeaderProvider):

    def __init__(self, lock_key: str):
        self.lock_key = lock_key

        self._lock_file: IO[bytes] | None = None
        self._lock_path = self._get_lock_path()

    # ============================================================
    # Lock Path
    # ============================================================

    def _get_lock_path(self) -> Path:
        safe_key = "".join(
            character
            if character.isalnum() or character in {"-", "_"}
            else "_"
            for character in self.lock_key
        )

        return Path(
            tempfile.gettempdir()
        ) / f"{safe_key}.lock"

    # ============================================================
    # Acquire
    # ============================================================

    def _acquire_sync(self) -> bool:
        if self._lock_file is not None:
            return True

        lock_path = self._lock_path

        lock_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        lock_file = open(
            lock_path,
            "a+b",
        )

        try:
            if sys.platform == "win32":
                acquired = self._acquire_windows(
                    lock_file
                )

            else:
                acquired = self._acquire_unix(
                    lock_file
                )

            if not acquired:
                lock_file.close()

                return False

            self._lock_file = lock_file

            return True

        except Exception:
            lock_file.close()

            raise

    async def acquire(self) -> bool:
        return await asyncio.to_thread(
            self._acquire_sync
        )

    # ============================================================
    # Unix Lock
    # ============================================================

    def _acquire_unix(self, lock_file: IO[bytes]) -> bool:
        import fcntl

        try:
            fcntl.flock(
                lock_file.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )

            return True

        except BlockingIOError:
            return False

    # ============================================================
    # Windows Lock
    # ============================================================

    def _acquire_windows(self, lock_file: IO[bytes]) -> bool:
        import msvcrt

        lock_file.seek(
            0
        )

        # Windows locking requires at least one byte to exist.
        if lock_file.read(1) == b"":
            lock_file.seek(
                0
            )

            lock_file.write(
                b"\0"
            )

            lock_file.flush()

        lock_file.seek(
            0
        )

        try:
            msvcrt.locking(
                lock_file.fileno(),
                msvcrt.LK_NBLCK,
                1,
            )

            return True

        except OSError:
            return False

    # ============================================================
    # Alive
    # ============================================================

    async def alive(self) -> bool:
        return self._lock_file is not None

    # ============================================================
    # Release
    # ============================================================

    def _release_sync(self) -> None:
        lock_file = self._lock_file

        if lock_file is None:
            return

        self._lock_file = None

        try:
            if sys.platform == "win32":
                self._release_windows(
                    lock_file
                )

            else:
                self._release_unix(
                    lock_file
                )

        finally:
            try:
                lock_file.close()

            except Exception:
                pass

    async def release(self) -> None:
        await asyncio.to_thread(
            self._release_sync
        )

    # ============================================================
    # Unix Release
    # ============================================================

    def _release_unix(self, lock_file: IO[bytes]) -> None:
        import fcntl

        try:
            fcntl.flock(
                lock_file.fileno(),
                fcntl.LOCK_UN,
            )

        except Exception:
            pass

    # ============================================================
    # Windows Release
    # ============================================================

    def _release_windows(self, lock_file: IO[bytes]) -> None:
        import msvcrt

        try:
            lock_file.seek(
                0
            )

            msvcrt.locking(
                lock_file.fileno(),
                msvcrt.LK_UNLCK,
                1,
            )

        except Exception:
            pass

    # ============================================================
    # Close
    # ============================================================

    async def close(self) -> None:
        await self.release()

    # ============================================================
    # Information
    # ============================================================

    @property
    def lock_path(self) -> Path:
        return self._lock_path
