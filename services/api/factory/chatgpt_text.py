"""Keep streamed text in memory until the response confirms completion."""

from .chatgpt_http import MAX_BODY


class StreamText:
    def __init__(self):
        self.deltas = {}
        self.text_done = {}
        self.items_done = {}
        self.delta_events = 0
        self.bytes = 0

    def position(self, event, content=True):
        values = (
            (event.get("output_index", 0), event.get("content_index", 0))
            if content
            else (event.get("output_index", 0),)
        )
        if any(type(v) is not int or not 0 <= v < 10000 for v in values):
            raise ValueError("ChatGPT sent invalid text event indices")
        return values

    def text(self, value):
        if not isinstance(value, str):
            raise ValueError("ChatGPT sent invalid text event data")
        try:
            self.bytes += len(value.encode("utf-8"))
        except UnicodeError:
            raise ValueError("ChatGPT sent invalid Unicode text") from None
        if self.bytes > MAX_BODY:
            raise ValueError("ChatGPT text exceeded the allowed size")
        return value

    def add(self, event, extract):
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
                self.items_done[key] = self.text(
                    extract({"response": {"status": "completed", "output": [item]}})
                )
        elif kind == "response.output_text.delta":
            key = self.position(event)
            if key in self.text_done:
                raise ValueError("ChatGPT sent a text delta after finalization")
            self.deltas.setdefault(key, []).append(self.text(event.get("delta")))
            self.delta_events += 1
        elif kind == "response.output_text.done":
            key = self.position(event)
            if key in self.text_done:
                raise ValueError("ChatGPT sent duplicate finalized text")
            self.text_done[key] = self.text(event.get("text"))
            if key in self.deltas and "".join(self.deltas[key]) != self.text_done[key]:
                raise ValueError("ChatGPT finalized text differs from its stream")

    def completed(self):
        if self.items_done:
            return "".join(self.items_done[key] for key in sorted(self.items_done))
        if self.text_done:
            if any(key not in self.text_done for key in self.deltas):
                raise ValueError("ChatGPT left text parts unfinished")
            return "".join(self.text_done[key] for key in sorted(self.text_done))
        return "".join("".join(self.deltas[key]) for key in sorted(self.deltas))

    def summary(self):
        return f"delta_events={self.delta_events}, finalized_text_parts={len(self.text_done)}, finalized_items={len(self.items_done)}"
