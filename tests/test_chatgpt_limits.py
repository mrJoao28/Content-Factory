"""Representative seven-scene payloads and independent finite streaming budgets."""

import asyncio
import json

import httpx
import pytest
from factory.chatgpt_limits import StreamBudget, StreamLimitExceeded
from factory.chatgpt_provider import completed_text, sse_events
from factory.chatgpt_text import StreamText
from factory.config import settings
from factory.schemas import Board
from factory.storyboard_limits import validate_generated


def representative_board():
    return Board.model_validate(
        {
            "scenes": [
                {
                    "duration": 5,
                    "narration": "An original robot explores the garden safely.",
                    "layers": [
                        {
                            "kind": "robot",
                            "color": "#64e8cf",
                            "size": 0.12,
                            "keyframes": [
                                {
                                    "time": index,
                                    "x": 0.1 + index * 0.11,
                                    "y": 0.2 + layer * 0.06,
                                    "rotation": index * 3,
                                }
                                for index in range(6)
                            ],
                        }
                        for layer in range(8)
                    ],
                }
                for _ in range(7)
            ]
        }
    )


def event(value):
    return ("data: " + json.dumps(value, separators=(",", ":"), ensure_ascii=False) + "\n\n").encode()


def representative_stream(text):
    pieces = [
        event(
            {
                "type": "response.output_text.delta",
                "output_index": 0,
                "content_index": 0,
                "item_id": "msg_fixture",
                "sequence_number": index,
                "delta": char,
            }
        )
        for index, char in enumerate(text)
    ]
    pieces += [
        event({"type": "response.output_text.done", "output_index": 0, "content_index": 0, "text": text}),
        event(
            {
                "type": "response.output_item.done",
                "output_index": 0,
                "item": {
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": text}],
                },
            }
        ),
        event({"type": "response.completed", "response": {"status": "completed", "output": []}}),
    ]
    return b"".join(pieces)


class BytesStream(httpx.AsyncByteStream):
    def __init__(self, payload, chunk=11_000):
        self.payload, self.chunk = payload, chunk

    async def __aiter__(self):
        for index in range(0, len(self.payload), self.chunk):
            yield self.payload[index : index + self.chunk]


async def parse(payload):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, headers={"Content-Type": "text/event-stream"}, stream=BytesStream(payload)
        )
    )
    budget = StreamBudget()
    text = StreamText()
    async with httpx.AsyncClient(transport=transport) as client:
        async with client.stream("POST", "https://example.test/responses") as response:
            complete = None
            async for item in sse_events(response, budget=budget):
                text.add(item, completed_text)
                if item.get("type") == "response.completed":
                    complete = completed_text(item, text.completed())
    return complete, budget, text


def test_seven_scenes_many_events_exceed_old_wire_limit_but_fit_unique_text():
    board = representative_board()
    text = json.dumps(board.model_dump(exclude_defaults=True), separators=(",", ":"))
    payload = representative_stream(text)
    assert len(payload) > 2_000_000
    complete, budget, collected = asyncio.run(parse(payload))
    assert budget.traffic == len(payload) < settings.chatgpt_stream_max_bytes
    assert collected.bytes == len(text.encode()) < settings.chatgpt_text_max_bytes
    assert collected.delta_events == len(text)
    assert Board.model_validate_json(complete) == board
    assert sum(scene.duration for scene in board.scenes) == 35
    validate_generated(board, {"duration": 35})


def test_unique_text_does_not_count_finalized_copies(monkeypatch):
    monkeypatch.setattr(settings, "chatgpt_text_max_bytes", 10)
    text = StreamText()
    text.add({"type": "response.output_text.delta", "delta": "12345"})
    text.add({"type": "response.output_text.delta", "delta": "67890"})
    text.add({"type": "response.output_text.done", "text": "1234567890"})
    text.add(
        {
            "type": "response.output_item.done",
            "item": {
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": "1234567890"}],
            },
        }
    )
    assert text.bytes == 10 and text.completed() == "1234567890"
    with pytest.raises(StreamLimitExceeded, match="text limit"):
        text.add({"type": "response.output_text.delta", "output_index": 1, "delta": "X"})


@pytest.mark.parametrize("layout", ["line", "multiline", "comment"])
def test_single_event_or_buffer_limit_is_independent(monkeypatch, layout):
    monkeypatch.setattr(settings, "chatgpt_event_max_bytes", 256)
    monkeypatch.setattr(settings, "chatgpt_stream_max_bytes", 50_000)
    payload = (
        b"data: " + b"x" * 300
        if layout == "line"
        else (b"data: {}\n" * 40 if layout == "multiline" else b":" + b"x" * 300 + b"\n")
    )
    with pytest.raises(StreamLimitExceeded) as raised:
        asyncio.run(parse(payload))
    assert raised.value.code == "event_limit"


def test_total_stream_limit_is_independent_of_event_size(monkeypatch):
    monkeypatch.setattr(settings, "chatgpt_stream_max_bytes", 200)
    monkeypatch.setattr(settings, "chatgpt_event_max_bytes", 100)
    with pytest.raises(StreamLimitExceeded) as raised:
        asyncio.run(parse(b": keepalive\n\n" * 100))
    assert raised.value.code == "stream_limit"


def test_many_small_events_in_one_chunk_do_not_become_one_large_event(monkeypatch):
    monkeypatch.setattr(settings, "chatgpt_event_max_bytes", 256)
    complete, _, _ = asyncio.run(
        parse(
            b": keepalive\n\n" * 3000
            + event(
                {
                    "type": "response.completed",
                    "response": {
                        "status": "completed",
                        "output": [
                            {
                                "type": "message",
                                "role": "assistant",
                                "content": [{"type": "output_text", "text": "{}"}],
                            }
                        ],
                    },
                }
            )
        )
    )
    assert complete == "{}"


def test_duration_complexity_and_keyframe_time_rejected_before_checkpoint():
    board = representative_board()
    board.scenes[0].duration = 4
    with pytest.raises(ValueError, match="durations"):
        validate_generated(board, {"duration": 35})
    board = representative_board()
    board.scenes[0].layers.append(board.scenes[0].layers[0])
    with pytest.raises(ValueError, match="layer"):
        validate_generated(board, {"duration": 35})
    board = representative_board()
    board.scenes[0].layers[0].keyframes[-1].time = 6
    with pytest.raises(ValueError, match="duration"):
        validate_generated(board, {"duration": 35})


def test_text_limit_is_enforced_from_real_events_before_completion(monkeypatch):
    monkeypatch.setattr(settings, "chatgpt_text_max_bytes", 64)
    with pytest.raises(StreamLimitExceeded) as raised:
        asyncio.run(parse(event({"type": "response.output_text.delta", "delta": "X" * 65})))
    assert raised.value.code == "text_limit"


@pytest.mark.parametrize(
    "name,value",
    [
        ("chatgpt_stream_max_bytes", 134_217_729),
        ("chatgpt_event_max_bytes", 8_388_609),
        ("chatgpt_text_max_bytes", 4_194_305),
        ("chatgpt_timeout_seconds", 1801),
    ],
)
def test_limits_configuration_cannot_become_unbounded(name, value):
    from factory.config import Settings
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{name: value})
