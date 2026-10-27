"""Account unique text by output/content index; finalized versions replace no bytes."""

from .chatgpt_limits import StreamLimitExceeded
from .config import settings


class StreamText:
    def __init__(self):
        self.parts = {}
        self.text_done = set()
        self.items_done = set()
        self.delta_events = 0
        self.bytes = 0
        self.max_bytes = settings.chatgpt_text_max_bytes

    def position(self, event, content=True):
        values = (
            (event.get("output_index", 0), event.get("content_index", 0))
            if content
            else (event.get("output_index", 0),)
        )
        if any(type(v) is not int or not 0 <= v < 10000 for v in values):
            raise ValueError("ChatGPT sent invalid text event indices")
        return values

    def put(self, key, value, *, delta=False):
        if not isinstance(value, str):
            raise ValueError("ChatGPT sent invalid text event data")
        try:
            encoded = value.encode("utf-8")
        except UnicodeError:
            raise ValueError("ChatGPT sent invalid Unicode text") from None
        previous = self.parts.get(key)
        if not delta and previous is not None:
            if previous != encoded:
                raise ValueError("ChatGPT finalized text differs from its stream")
            return
        added = len(encoded)
        if self.bytes + added > self.max_bytes:
            raise StreamLimitExceeded("text", self.max_bytes)
        if previous is None:
            if len(self.parts) >= 128:
                raise ValueError("ChatGPT returned too many text parts")
            self.parts[key] = bytearray(encoded)
        else:
            previous.extend(encoded)
        self.bytes += added

    def add(self, event, extract=None):
        kind = event.get("type")
        if kind in {"response.refusal.delta", "response.refusal.done"}:
            raise ValueError("ChatGPT refused the request; no text result was saved")
        if kind in {"response.output_item.added", "response.output_item.done"}:
            item = event.get("item")
            if not isinstance(item, dict):
                raise ValueError("ChatGPT sent invalid output item data")
            if item.get("type") == "reasoning":
                return
            if item.get("type") != "message" or item.get("role") != "assistant":
                raise ValueError("ChatGPT returned unsupported output; no tools are executed")
            if kind == "response.output_item.done":
                if item.get("status") != "completed":
                    raise ValueError("ChatGPT output item did not complete")
                key = self.position(event, content=False)
                if key in self.items_done:
                    raise ValueError("ChatGPT sent duplicate finalized output items")
                content = item.get("content")
                if not isinstance(content, list) or not content:
                    raise ValueError("ChatGPT returned an empty finalized message")
                for index, part in enumerate(content):
                    if not isinstance(part, dict) or part.get("type") != "output_text":
                        raise ValueError("ChatGPT refused or returned non-text output")
                    self.put((key[0], index), part.get("text"))
                if any(k[0] == key[0] and k[1] >= len(content) for k in self.parts):
                    raise ValueError("ChatGPT finalized message omitted text parts")
                self.items_done.add(key)
        elif kind == "response.output_text.delta":
            key = self.position(event)
            if key in self.text_done or (key[0],) in self.items_done:
                raise ValueError("ChatGPT sent a text delta after finalization")
            self.put(key, event.get("delta"), delta=True)
            self.delta_events += 1
        elif kind == "response.output_text.done":
            key = self.position(event)
            if key in self.text_done:
                raise ValueError("ChatGPT sent duplicate finalized text")
            self.put(key, event.get("text"))
            self.text_done.add(key)

    def completed(self):
        if self.items_done and any((key[0],) not in self.items_done for key in self.parts):
            raise ValueError("ChatGPT left output items unfinished")
        if self.text_done and not self.items_done and any(key not in self.text_done for key in self.parts):
            raise ValueError("ChatGPT left text parts unfinished")
        return b"".join(self.parts[key] for key in sorted(self.parts)).decode("utf-8")

    def summary(self):
        return f"delta_events={self.delta_events}, finalized_text_parts={len(self.text_done)}, finalized_items={len(self.items_done)}, unique_text_bytes={self.bytes}"
