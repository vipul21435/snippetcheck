"""Read JSONL datasets in the common instruction and chat shapes.

Each record becomes a list of turns, one per answer: the answer text and the prompt
that asked for it. Shapes are detected per record:

* ``messages``: ``{"messages": [{"role": ..., "content": ...}, ...]}``
* ``sharegpt``: ``{"conversations": [{"from": ..., "value": ...}, ...]}``
* ``alpaca``: ``{"instruction": ..., "input": ..., "output": ...}``
* ``pair``: one of the prompt/answer key pairs in ``PAIR_KEYS``
* ``field``: any object, with the answer taken from ``--field``
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

ASSISTANT_ROLES = {"assistant", "gpt", "model", "bot", "chatgpt", "bard", "claude"}
USER_ROLES = {"user", "human", "prompter"}
PAIR_KEYS = [
    ("instruction", "response"),
    ("problem", "solution"),
    ("prompt", "completion"),
    ("prompt", "response"),
    ("question", "answer"),
    ("query", "response"),
]


@dataclass(frozen=True)
class Turn:
    prompt: str
    answer: str


@dataclass(frozen=True)
class Record:
    id: str
    line: int
    shape: str
    turns: tuple[Turn, ...]
    raw: str = ""  # the input line, for writing a filtered copy


@dataclass(frozen=True)
class BadLine:
    line: int
    reason: str


def _text(value: object) -> str:
    """Flatten a content value: a string, or a list of strings / {"text": ...} parts."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for part in value:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
        return "\n".join(parts)
    return ""


def _chat_turns(messages: list, role_key: str, content_key: str) -> tuple[Turn, ...]:
    turns: list[Turn] = []
    prompt = ""
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get(role_key, "")).lower()
        content = _text(message.get(content_key))
        if role in USER_ROLES:
            prompt = content
        elif role in ASSISTANT_ROLES:
            turns.append(Turn(prompt, content))
    return tuple(turns)


def _lookup(obj: dict, path: str) -> object:
    value: object = obj
    for key in path.split("."):
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def detect_shape(obj: dict) -> str | None:
    if isinstance(obj.get("messages"), list):
        return "messages"
    if isinstance(obj.get("conversations"), list):
        return "sharegpt"
    if "instruction" in obj and "output" in obj:
        return "alpaca"
    for prompt_key, answer_key in PAIR_KEYS:
        if prompt_key in obj and answer_key in obj:
            return f"pair:{prompt_key}/{answer_key}"
    return None


def to_record(obj: dict, line: int, field: str | None = None,
              prompt_field: str | None = None) -> Record | BadLine:
    raw_id = obj.get("id")
    rid = str(raw_id) if isinstance(raw_id, (str, int)) and str(raw_id) else str(line)
    if field:
        answer = _text(_lookup(obj, field))
        prompt = _text(_lookup(obj, prompt_field)) if prompt_field else ""
        return Record(rid, line, "field", (Turn(prompt, answer),))
    shape = detect_shape(obj)
    if shape == "messages":
        turns = _chat_turns(obj["messages"], "role", "content")
    elif shape == "sharegpt":
        turns = _chat_turns(obj["conversations"], "from", "value")
    elif shape == "alpaca":
        prompt = _text(obj.get("instruction"))
        extra = _text(obj.get("input"))
        if extra:
            prompt = f"{prompt}\n{extra}"
        turns = (Turn(prompt, _text(obj.get("output"))),)
    elif shape is not None:
        prompt_key, answer_key = shape.split(":", 1)[1].split("/")
        turns = (Turn(_text(obj.get(prompt_key)), _text(obj.get(answer_key))),)
    else:
        return BadLine(line, "unrecognised record shape (use --field)")
    return Record(rid, line, shape, turns)


def read_jsonl(lines: Iterable[str], field: str | None = None,
               prompt_field: str | None = None) -> Iterator[Record | BadLine]:
    """Yield a Record or a BadLine for every non-blank line."""
    for number, raw in enumerate(lines, start=1):
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw)
        except ValueError as exc:
            yield BadLine(number, f"invalid JSON: {exc}")
            continue
        if not isinstance(obj, dict):
            yield BadLine(number, "line is not a JSON object")
            continue
        item = to_record(obj, number, field, prompt_field)
        if isinstance(item, Record):
            item = Record(item.id, item.line, item.shape, item.turns, raw.rstrip("\n"))
        yield item


def iter_lines(handle: Iterable[str]) -> Iterator[str]:
    """Yield JSONL lines; a file holding one JSON array yields one line per element."""
    iterator = iter(handle)
    head: list[str] = []
    for line in iterator:
        head.append(line)
        if line.strip():
            break
    if head and head[-1].lstrip().startswith("["):
        text = "".join(head) + "".join(iterator)
        try:
            items = json.loads(text)
        except ValueError:
            yield from text.splitlines()
            return
        for item in items if isinstance(items, list) else [items]:
            yield json.dumps(item, ensure_ascii=False)
        return
    yield from head
    yield from iterator
