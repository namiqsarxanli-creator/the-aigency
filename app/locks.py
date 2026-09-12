"""Layihə başına kilid — manual `/run` çağırışı ilə avtonom fon dövrəsinin (scheduler)
eyni layihəni EYNI ANDA irəlilətməsinin (və nəticədə hər rol üçün təkrarlanan tapşırıqların
yaranmasının) qarşısını alır. Tək prosesli uvicorn daxilində asyncio.Lock kifayətdir."""
import asyncio

_locks: dict[int, asyncio.Lock] = {}


def get_lock(project_id: int) -> asyncio.Lock:
    lock = _locks.get(project_id)
    if lock is None:
        lock = asyncio.Lock()
        _locks[project_id] = lock
    return lock
