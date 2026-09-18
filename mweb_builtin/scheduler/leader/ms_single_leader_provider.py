from .ms_leader_provider import MWebSchedulerLeaderProvider


class MWebSingleSchedulerLeaderProvider(MWebSchedulerLeaderProvider):

    async def acquire(self) -> bool:
        return True

    async def alive(self) -> bool:
        return True

    async def release(self) -> None:
        pass

    async def close(self) -> None:
        pass
