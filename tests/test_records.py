import json

from snippetcheck.records import BadLine, Record, read_jsonl


def load(*objs, **kwargs):
    lines = [o if isinstance(o, str) else json.dumps(o) for o in objs]
    return list(read_jsonl(lines, **kwargs))


def test_messages_shape_pairs_prompt_with_answer():
    [rec] = load({"id": 7, "messages": [
        {"role": "system", "content": "Be brief."},
        {"role": "user", "content": "Write add in Python."},
        {"role": "assistant", "content": "def add(a, b): return a + b"},
        {"role": "user", "content": "Now in JavaScript."},
        {"role": "assistant",
         "content": [{"type": "text", "text": "const add = (a, b) => a + b;"}]},
    ]})
    assert isinstance(rec, Record)
    assert rec.id == "7"
    assert rec.shape == "messages"
    assert [t.prompt for t in rec.turns] == ["Write add in Python.", "Now in JavaScript."]
    assert rec.turns[1].answer == "const add = (a, b) => a + b;"


def test_sharegpt_shape():
    [rec] = load({"conversations": [
        {"from": "human", "value": "hi"},
        {"from": "gpt", "value": "hello"},
    ]})
    assert rec.shape == "sharegpt"
    assert rec.id == "1"
    assert rec.turns[0].answer == "hello"


def test_alpaca_shape_joins_instruction_and_input():
    [rec] = load({"instruction": "Sort this list.", "input": "[3, 1, 2]", "output": "sorted(x)"})
    assert rec.shape == "alpaca"
    assert rec.turns[0].prompt == "Sort this list.\n[3, 1, 2]"


def test_pair_shapes():
    [rec] = load({"problem": "p", "solution": "s"})
    assert rec.shape == "pair:problem/solution"
    assert rec.turns[0].answer == "s"


def test_field_option_with_dotted_path():
    [rec] = load({"meta": {"code": "x = 1"}, "ask": "q"}, field="meta.code", prompt_field="ask")
    assert rec.shape == "field"
    assert rec.turns[0].answer == "x = 1"
    assert rec.turns[0].prompt == "q"


def test_bad_lines_are_reported_not_raised():
    out = load("{not json", "[1, 2]", {"something": "else"}, "")
    assert all(isinstance(item, BadLine) for item in out)
    assert [item.line for item in out] == [1, 2, 3]
