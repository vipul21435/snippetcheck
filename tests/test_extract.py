from snippetcheck.extract import extract_blocks
from snippetcheck.lang import guess_language, looks_like_code, normalise_info


def test_single_fenced_block_with_info():
    text = "Here you go:\n\n```python\nx = 1\nprint(x)\n```\n\nDone."
    [block] = extract_blocks(text)
    assert block.kind == "fenced"
    assert block.code == "x = 1\nprint(x)"
    assert block.info == "python"
    assert block.lang == "python"
    assert block.lang_source == "info"
    assert block.start_line == 4
    assert block.terminated


def test_two_blocks_and_tilde_fence():
    text = "```js\nconsole.log(1)\n```\ntext\n~~~~ bash\necho hi\n~~~~\n"
    blocks = extract_blocks(text)
    assert [b.lang for b in blocks] == ["javascript", "shell"]
    assert [b.code for b in blocks] == ["console.log(1)", "echo hi"]


def test_closing_fence_must_match_char_and_length():
    text = "````python\n```\nstill code\n~~~\n````\n"
    [block] = extract_blocks(text)
    assert block.code == "```\nstill code\n~~~"
    assert block.terminated


def test_unterminated_fence_runs_to_end():
    text = "Answer:\n```python\ndef f(a, b):\n    return a +"
    [block] = extract_blocks(text)
    assert not block.terminated
    assert block.code == "def f(a, b):\n    return a +"


def test_inline_triple_backticks_are_not_a_fence():
    text = "Use ```print(x)``` to show it.\n"
    assert extract_blocks(text) == []


def test_indented_fence_inside_list_item_is_dedented():
    text = "1. Install:\n\n    ```bash\n    pip install foo\n    ```\n2. Run it.\n"
    [block] = extract_blocks(text)
    assert block.code == "pip install foo"
    assert block.lang == "shell"


def test_info_string_variants():
    assert normalise_info("Python3") == "python"
    assert normalise_info("{.python}") == "python"
    assert normalise_info("language-js") == "javascript"
    assert normalise_info('python title="a.py"') == "python"
    assert normalise_info("py:example.py") == "python"
    assert normalise_info("elixir") == "elixir"
    assert normalise_info("") == ""


def test_unlabelled_fence_gets_heuristic_language():
    text = "```\ndef add(a, b):\n    return a + b\n```"
    [block] = extract_blocks(text)
    assert block.lang == "python"
    assert block.lang_source == "heuristic"


def test_indented_block_after_blank_line():
    text = "Try this:\n\n    for i in range(3):\n        print(i)\n\nThat prints three lines."
    [block] = extract_blocks(text)
    assert block.kind == "indented"
    assert block.code == "for i in range(3):\n    print(i)"
    assert block.start_line == 3


def test_indented_list_continuation_is_not_code():
    text = "- first point\n\n    more about the first point.\n"
    assert extract_blocks(text) == []


def test_whole_answer_code():
    text = "import os\n\nfor name in os.listdir('.'):\n    print(name)\n"
    [block] = extract_blocks(text)
    assert block.kind == "whole"
    assert block.lang == "python"
    assert block.start_line == 1


def test_prose_answer_has_no_blocks():
    text = "The capital of France is Paris. It has been the capital for centuries."
    assert extract_blocks(text) == []
    assert not looks_like_code(text)


def test_crlf_line_endings():
    text = "```python\r\nx = 1\r\n```\r\n"
    [block] = extract_blocks(text)
    assert block.code == "x = 1"


def test_guess_language_cases():
    assert guess_language('{"a": 1, "b": [1, 2]}') == "json"
    assert guess_language("console.log('hi');\nconst x = 2;") == "javascript"
    assert guess_language("#include <stdio.h>\nint main() { printf(\"x\"); }") == "c"
    assert guess_language("#include <iostream>\nint main() { std::cout << 1; }") == "cpp"
    assert guess_language("SELECT name FROM users WHERE id = 3;") == "sql"
    assert guess_language("$ pip install requests") == "shell"
    assert guess_language("hello there") == ""


def test_unfenced_code_with_blank_line_is_taken_whole():
    text = "class A:\n\n    def f(self):\n        return 1\n"
    [block] = extract_blocks(text)
    assert block.kind == "whole"
    assert block.code.startswith("class A:")
    text = "import os\ndef main():\n\n    print(os.getcwd())\n\nmain()"
    [block] = extract_blocks(text)
    assert block.kind == "whole" and block.lang == "python"
    assert "import os" in block.code


def test_short_python_answer_is_code():
    [block] = extract_blocks("x = 5")
    assert block.kind == "whole" and block.lang == "python"
    assert extract_blocks("Yes") == []
    assert extract_blocks("42") == []


def test_indented_block_needs_a_prose_paragraph_before_it():
    text = "Here is the loop.\ndef f():\n\n    return 1\n\nThat is all, really."
    assert extract_blocks(text) == []
