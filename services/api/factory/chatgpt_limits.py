"""Separate finite budgets for streaming transport, frames and unique text."""

import time

from .chatgpt_http import ChatGPTTransient
from .config import settings
from .security import Cancelled


class StreamLimitExceeded(ValueError):
    def __init__(self, resource, limit):
        self.code = resource + "_limit"
        super().__init__(
            f"ChatGPT {resource} limit reached ({limit} bytes). Reduce storyboard complexity or review the corresponding CHATGPT limit; completed checkpoints were retained."
        )


class StreamTimeout(ChatGPTTransient):
    def __init__(self):
        super().__init__()
        self.code = "runtime_limit"
        self.args = (
            "ChatGPT generation time limit reached. Review CHATGPT_TIMEOUT_SECONDS and resume; completed checkpoints were retained.",
        )


class StreamBudget:
    def __init__(self, deadline=None, cancel=None):
        self.max_traffic = settings.chatgpt_stream_max_bytes
        self.max_event = settings.chatgpt_event_max_bytes
        self.traffic = 0
        self.deadline, self.cancel = deadline, cancel
        self.last_cancel_check = 0.0

    def check(self):
        now = time.monotonic()
        if self.deadline is not None and now >= self.deadline:
            raise StreamTimeout()
        if self.cancel and now - self.last_cancel_check >= 0.1:
            self.last_cancel_check = now
            if self.cancel():
                raise Cancelled("Text generation cancelled")

    async def read(self, response):
        async for chunk in response.aiter_bytes():
            self.check()
            self.traffic += len(chunk)
            if self.traffic > self.max_traffic:
                raise StreamLimitExceeded("stream", self.max_traffic)
            # Process a transport chunk incrementally, even if it contains many SSE events.
            for start in range(0, len(chunk), 16_384):
                yield chunk[start : start + 16_384]
