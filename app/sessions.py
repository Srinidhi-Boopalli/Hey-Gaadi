"""Bounded, process-local demo sessions; replace with shared storage before scaling."""
import threading
import time
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from app.schemas import VehicleState


@dataclass
class Session:
    state: VehicleState = field(default_factory=VehicleState)
    pending: str | None = None
    touched: float = field(default_factory=time.monotonic)
    lock: threading.RLock = field(default_factory=threading.RLock)


class SessionStore:
    def __init__(self, max_sessions=1000, ttl_seconds=3600):
        self.sessions = {}
        self.lock = threading.Lock()
        self.max_sessions = max_sessions
        self.ttl = ttl_seconds

    def get(self, requested: UUID | None) -> tuple[UUID, Session]:
        with self.lock:
            now = time.monotonic()
            # Never evict a session while a command holds its lock.
            for identifier, session in list(self.sessions.items()):
                if now - session.touched > self.ttl and session.lock.acquire(blocking=False):
                    try:
                        self.sessions.pop(identifier)
                    finally:
                        session.lock.release()
            identifier = requested or uuid4()
            if identifier not in self.sessions:
                if len(self.sessions) >= self.max_sessions:
                    raise ValueError("Session capacity reached; retry after old sessions expire")
                self.sessions[identifier] = Session()
            session = self.sessions[identifier]
            session.touched = now
            return identifier, session

    def reset(self, identifier: UUID) -> None:
        _, session = self.get(identifier)
        with session.lock:
            session.state = VehicleState()
            session.pending = None
