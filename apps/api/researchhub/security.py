"""Small process-local login limiter for the single-user deployment."""

import math
import os
import time
from collections import OrderedDict, deque
from threading import Lock

from fastapi import HTTPException


class LoginAttempts:
    def __init__(self):
        self.peers = OrderedDict()
        self.lock = Lock()

    def begin(self, peer):
        now = time.monotonic()
        window = int(os.getenv("LOGIN_ATTEMPT_WINDOW_SECONDS", "900"))
        limit = int(os.getenv("LOGIN_ATTEMPT_LIMIT", "10"))
        with self.lock:
            attempts = self.peers.setdefault(peer, deque())
            self.peers.move_to_end(peer)
            while attempts and attempts[0] <= now - window:
                attempts.popleft()
            if len(attempts) >= limit:
                retry = max(1, math.ceil(window - (now - attempts[0])))
                raise HTTPException(
                    429,
                    "Too many login attempts; retry later",
                    headers={"Retry-After": str(retry)},
                )
            attempts.append(now)
            while len(self.peers) > 1024:
                self.peers.popitem(last=False)

    def success(self, peer):
        with self.lock:
            self.peers.pop(peer, None)
