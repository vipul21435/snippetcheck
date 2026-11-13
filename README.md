# snippetcheck

Pull the code out of instruction and chat datasets and check it statically (syntax, Python 2,
truncation, invalid JSON) without ever running it.

Status: early. The extraction, the Python and JSON checks and the report work; the scope
analysis, shell and JavaScript checks, cross-checks, thresholds and `--fix` are not written yet
(see "Not implemented yet" below).

## Why this is hard

Code in a training dataset sits inside free text. It may be fenced with an info string, fenced
with none, indented, the whole answer, or cut off half way when the generation hit a token
limit. It may be Python 2 in a set that asks for Python 3, or a notebook cell with magics that a
parser rejects. Nothing in the usual data pipeline looks at it before a model is trained on it,
and running it to find out is slow and unsafe.

## Install

```
pip install git+https://github.com/vipul21435/snippetcheck
```

Python 3.10 or newer, no runtime dependencies.

## Quickstart

`examples/sample.jsonl` holds ten short records written by hand for this README (Alpaca,
messages and ShareGPT shapes mixed):

```
$ snippetcheck check examples/sample.jsonl
# snippetcheck report

Records: 10 (0 unreadable lines), answers: 10, code blocks: 9

## Rules

| rule | count | over | share | 95 % CI (Wilson) | examples |
|---|---:|---|---:|---|---|
| unterminated-fence | 2 | 8 fenced blocks | 25.0 % | 7.1 % to 59.1 % | 3#0.0, 10#0.0 |
| py-syntax | 3 | 7 python blocks | 42.9 % | 15.8 % to 75.0 % | 2#0.0, 3#0.0, 10#0.0 |
| py2-syntax | 1 | 7 python blocks | 14.3 % | 2.6 % to 51.3 % | 2#0.0 |
| py-compile | 1 | 7 python blocks | 14.3 % | 2.6 % to 51.3 % | 7#0.0 |
| truncated | 2 | 8 checked blocks | 25.0 % | 7.1 % to 59.1 % | 3#0.0, 10#0.0 |
| json-invalid | 1 | 1 json blocks | 100.0 % | 20.7 % to 100.0 % | 4#0.0 |

## Languages

| language | blocks |
|---|---:|
| python | 7 |
| json | 1 |
| shell | 1 |

## Most common Python syntax errors

| error | blocks |
|---|---:|
| SyntaxError: '(' was never closed | 2 |
| SyntaxError: Missing parentheses in call to 'print'. Did you mean print(...)? | 1 |

Examples are record id#answer.block, all 0-based after the record id.
```

The error messages are those of the Python that runs snippetcheck (3.12 above); older versions
word some of them differently.

`snippetcheck check --format json` prints the same numbers as JSON. `snippetcheck extract`
prints every block as one JSON line (`--lang python` to filter), and `snippetcheck explain
RULE` says what a rule means and what it is counted over.

Input shapes are detected per record: `messages` (role/content), ShareGPT `conversations`
(from/value), Alpaca `instruction`/`input`/`output`, and a few prompt/answer key pairs such as
`problem`/`solution`. Anything else takes `--field key.path` (and `--prompt-field`).

## What works so far

- Extraction: fenced blocks (backticks or tildes, info string kept), fences never closed,
  fences indented inside list items, indented blocks after a blank line, and answers that are
  entirely code. The language comes from the info string, then from a keyword score.
- Python: `ast.parse` and then `compile` on the parsed tree, with the error class, message and
  line. Python 2 constructs are named when a block fails to parse. `>>>` transcripts are
  unwrapped and notebook magics replaced before parsing; a `%%bash` cell is skipped.
- Truncation: a failed parse is called truncated when the end of the text explains it: a
  string still open, brackets still open (and closing them makes the code parse, or the bracket
  opened on the last line), or a last line ending in an operator, comma, backslash or a block
  header with no body.
- JSON: `json.loads`, with the same open-string and open-bracket truncation signal.
- Report: count and share per rule over the blocks the rule applies to, a 95 % Wilson score
  interval, example ids, a language table and the most common Python syntax errors.

Nothing taken from a dataset is executed or imported: the checks use `ast.parse`, `compile`
(which builds a code object and does not run it) and `json.loads`.

## Not implemented yet

- the undefined-name and unused-import scope analysis, and placeholder detection;
- shell (`bash -n`) and JavaScript (`node --check`) checks, bracket balance for other languages;
- cross-checks: wrong language for the prompt, a code request with no code, duplicate blocks;
- exit-code thresholds and `--fix`;
- results on real public datasets.

## Licence

MIT, see [LICENSE](LICENSE).

Built by Vipul Raj Jha · https://vipul21435.github.io
