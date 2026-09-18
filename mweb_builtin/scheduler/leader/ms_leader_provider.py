from abc import ABC, abstractmethod


class MWebSchedulerLeaderProvider(ABC):

    @abstractmethod
    async def acquire(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def alive(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def release(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        raise NotImplementedError
