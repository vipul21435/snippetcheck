# snippetcheck

Pull the code out of instruction and chat datasets and check it statically (syntax, undefined
names, placeholders, truncation, wrong language) without ever running it.

## Why this is hard

Code in a training dataset sits inside free text. It may be fenced with an info string, fenced
with none, indented, the whole answer, or cut off half way when the generation hit a token
limit. It may be Python 2 in a set that asks for Python 3, a notebook cell with magics, a REPL
transcript, a function body without its `def` line, or another language than the prompt asked
for. Running every snippet to find out is slow and unsafe, so most pipelines check nothing,
and the checks that do exist (execution filters) need a sandbox and tests for each sample.

## Install

```
pip install git+https://github.com/vipul21435/snippetcheck
```

Python 3.10 or newer, no runtime dependencies. `bash` and `node` are used when present.

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
| py-undefined-name | 1 | 7 python blocks | 14.3 % | 2.6 % to 51.3 % | 7#0.0 |
| py-unused-import | 0 | 7 python blocks | 0.0 % | 0.0 % to 35.4 % |  |
| placeholder | 0 | 7 python blocks | 0.0 % | 0.0 % to 35.4 % |  |
| truncated | 2 | 9 checked blocks | 22.2 % | 6.3 % to 54.7 % | 3#0.0, 10#0.0 |
| shell-syntax | 0 | 1 shell blocks | 0.0 % | 0.0 % to 79.3 % |  |
| js-syntax | 0 | 0 javascript blocks | 0.0 % | n/a |  |
| unbalanced-brackets | 0 | 0 balance blocks | 0.0 % | n/a |  |
| lang-mismatch | 0 | 4 answers to a one-language prompt | 0.0 % | 0.0 % to 49.0 % |  |
| no-code | 0 | 2 answers to a code request | 0.0 % | 0.0 % to 65.8 % |  |
| duplicate-block | 0 | 9 blocks | 0.0 % | 0.0 % to 29.9 % |  |
| json-invalid | 1 | 1 json blocks | 100.0 % | 20.7 % to 100.0 % | 4#0.0 |

## Languages

| language | blocks | blocks with a finding, by rule |
|---|---:|---|
| python | 7 | py-syntax 3, unterminated-fence 2, truncated 2, py2-syntax 1, py-compile 1, py-undefined-name 1 |
| json | 1 | json-invalid 1 |
| shell | 1 | - |

## Most common Python syntax errors

| key | count |
|---|---:|
| SyntaxError: '(' was never closed | 2 |
| SyntaxError: Missing parentheses in call to 'print'. Did you mean print(...)? | 1 |

## Most common undefined names

| key | count |
|---|---:|
| result | 1 |

Examples are record id#answer.block (block rules) or record id#answer (prompt rules), 0-based after the record id.
```

The error messages are those of the Python that runs snippetcheck (3.12 above); older versions
word some of them differently.

Other commands and options:

- `snippetcheck check --format json` prints the same numbers as JSON.
- `snippetcheck check data.jsonl --max py-syntax=2% --max truncated=0.5%` exits 1 when a share
  goes over its limit (0 otherwise, 2 for bad usage or input).
- `snippetcheck check data.jsonl --fix clean.jsonl --drop py-syntax,truncated` writes a copy
  without the records those rules reject; every other record, and every line that could not
  be read as a record, is copied unchanged. The copy is JSONL even when the input is a JSON
  array, and OUT may not be the input file.
- `snippetcheck extract data.jsonl --lang python` prints every block as one JSON line.
- `snippetcheck explain` lists the rules; `snippetcheck explain truncated` explains one.
- `--field key.path` (and `--prompt-field`) for JSONL in any other shape; `--no-external`
  skips `bash` and `node`; `--jobs N` overlaps their calls; `--no-dedupe` skips duplicates.

Input is UTF-8 JSONL (a byte-order mark is accepted), or a file holding one JSON array. Shapes are detected per record: `messages`
(role/content), ShareGPT `conversations` (from/value), Alpaca `instruction`/`input`/`output`,
and the pairs `instruction`/`response`, `problem`/`solution`, `prompt`/`completion`,
`prompt`/`response`, `question`/`answer`, `query`/`response`. For Alpaca the prompt is the
instruction followed by the input. `examples/check_sample.py` shows the Python API.

## How it works

**Extraction.** Fenced blocks follow the CommonMark rules for fences (three or more backticks
or tildes, closed by the same character at least as long, info string kept) with one
deliberate difference: fences indented by any amount are accepted, because model output
indents them inside list items. A fence that is never closed runs to the end of the text and
is reported (`unterminated-fence`). An answer with no fence is taken whole when it parses as
Python with at least one real statement (bare expressions, `name: value` lines, R's `<-` and
trailing semicolons do not count), or when 70 % of its non-blank lines read as code and a
language can be guessed. Only after that are indented blocks looked for, and only after a
blank line that follows a prose paragraph (not inside list items), so the indented body of
an unfenced function is never cut out of its answer. The language comes from the info string
(107 aliases), otherwise from a weighted keyword score per language; JavaScript with JSX or
HTML tags is called `jsx` or `html`.

**Python.** The block is dedented and parsed as it is. Only when that fails are `>>>`/`...`
transcripts unwrapped (output lines blanked), line magics (`%`, `!`) and `obj?` help lines
turned into `pass` so line numbers hold, and `%%bash`-style cells skipped. `ast.parse` gives the error class, message and line;
`compile()` on the tree then catches what the parser lets through (`'return' outside
function`). Neither runs anything. When a block fails, Python 2 markers are looked for
outside strings and comments (print statement, `except X, e`, `raise E, msg`, `<>`, `0777`,
`10L`, `ur''`), and the failure is called truncated when the end of the text explains it: a
string still open, brackets still open (closing them makes the code parse, or the innermost
one opened on the last line), or a last line ending in an operator, comma, backslash or a
block header with no body. It is not called when the last line is prose, when a string is
opened by an apostrophe in a sentence, when only comments follow the last code line, or
when the parser's error lies above the last code line.

**Scope analysis.** Written on the AST for this tool, following Python's name resolution:
module and class bodies are read in order, function and lambda bodies after the enclosing
body is complete, class scopes are invisible from functions and comprehensions,
comprehensions have their own scope (walrus binds outside it), `global`/`nonlocal`
redirect bindings, `from x import *` silences the check, a name inside `try` with
`except NameError` is not reported, and string annotations are checked as forward
references. It reports undefined names (Python 2 builtins such as `xrange` count as
undefined) and unused imports. Placeholders are functions whose body is only `pass`, `...`
or a docstring (abstract methods, overloads, Protocol/ABC members and exception classes
excepted), a bare `...` statement, and "your code here"-style comments or strings.

**Other languages.** JSON through `json.loads`; shell through `bash -n` (reads, never runs;
`$ ` prompts removed first); JavaScript through `node --check` (compiles, never runs; ES module
when it has `import`/`export`). For C, C++, C#, Java, Go, Rust, TypeScript, JSX, Kotlin,
Swift, Scala, PHP, Dart, CSS, Ruby, Perl, R, Julia and PowerShell only bracket and string
balance is checked: that is not a parse.

**Cross-checks.** `lang-mismatch`: the prompt names exactly one language and no block is in
it (shell, JSON, YAML and text blocks do not count; C/C++ and JavaScript/TypeScript/JSX are
accepted for each other). `no-code`: the prompt asks for code (a verb such as write or
implement followed within the clause by function, program, script, query and similar) and
the answer has no block. `duplicate-block`: a block of three or more non-blank lines
identical, after trailing whitespace is removed, to a block of an earlier record; the first
copy is not flagged, so `--drop duplicate-block` keeps one.

**Report.** Each rule is a count of units with at least one finding, over the units it
applies to (Python blocks, JSON blocks, fenced blocks, answers to a code request, and so
on), with a 95 % Wilson score interval:
(p + z²/2n ± z·√(p(1−p)/n + z²/4n²)) / (1 + z²/n), z = 1.96.

**Tests.** `uv run --extra dev pytest --cov=snippetcheck` runs 128 offline tests (fixtures
built in the tests, nothing from them imported or executed) with 95 % line coverage of the
package under Python 3.12; the same suite passes under 3.10.

The datasets this is meant for are built in the ways described by Code Alpaca (Chaudhary
2023, self-instruct for code), WizardCoder (Luo et al. 2023, Evol-Instruct for code) and
Magicoder (Wei et al. 2023, OSS-Instruct). SelfCodeAlign (Wei et al. 2024) filters generated
code by running it against generated tests in a sandbox; snippetcheck is the cheap static pass
that needs no sandbox and no tests. Allamanis (2019) measured how duplicated code inflates
results of models of code, which is why duplicate blocks are counted.

- S. Chaudhary, *Code Alpaca: An Instruction-following LLaMA model for code generation*, 2023.
  https://github.com/sahil280114/codealpaca
- Z. Luo et al., *WizardCoder: Empowering Code Large Language Models with Evol-Instruct*,
  2023. https://arxiv.org/abs/2306.08568
- Y. Wei et al., *Magicoder: Empowering Code Generation with OSS-Instruct*, 2023.
  https://arxiv.org/abs/2312.02120
- Y. Wei et al., *SelfCodeAlign: Self-Alignment for Code Generation*, 2024.
  https://arxiv.org/abs/2410.24198
- M. Allamanis, *The Adverse Effects of Code Duplication in Machine Learning Models of Code*,
  Onward! 2019. https://arxiv.org/abs/1812.06469
- CommonMark Spec 0.31.2, fenced and indented code blocks.
  https://spec.commonmark.org/0.31.2/

## Results on public data

Two public code-instruction sets, checked with snippetcheck under Python 3.12.13, bash 3.2
and node 25.9 (macOS):

```
bash scripts/fetch_data.sh data
snippetcheck check data/code_alpaca_20k.json --format json --jobs 8
snippetcheck check data/EvolInstruct-Code-80k.json --format json --jobs 8
```

| | CodeAlpaca-20k | Evol-Instruct-Code-80k-v1 |
|---|---|---|
| records | 20,022 | 78,264 |
| code blocks (fenced / indented / whole answer) | 15,084 (13 / 3 / 15,068) | 86,003 (54,882 / 45 / 31,076) |
| Python blocks | 8,223 | 43,361 |
| Python blocks that do not parse (`py-syntax`) | 316, 3.8 % (3.4 to 4.3 %) | 1,353, 3.1 % (3.0 to 3.3 %) |
| Python 2 syntax (`py2-syntax`) | 6, 0.07 % (0.03 to 0.16 %) | 24, 0.06 % (0.04 to 0.08 %) |
| parse but do not compile (`py-compile`) | 14, 0.17 % (0.10 to 0.29 %) | 41, 0.09 % (0.07 to 0.13 %) |
| with an undefined name (`py-undefined-name`) | 1,463, 17.8 % (17.0 to 18.6 %) | 7,749, 17.9 % (17.5 to 18.2 %) |
| with an unused import | 87, 1.1 % (0.9 to 1.3 %) | 847, 2.0 % (1.8 to 2.1 %) |
| placeholders | 26, 0.32 % (0.22 to 0.46 %) | 178, 0.41 % (0.35 to 0.48 %) |
| truncated, over all checked blocks | 16 of 13,001, 0.12 % (0.08 to 0.20 %) | 67 of 68,790, 0.10 % (0.08 to 0.12 %) |
| unterminated fences | 0 of 13, 0.00 % (0.00 to 22.81 %) | 120 of 54,882, 0.22 % (0.18 to 0.26 %) |
| JSON blocks that do not parse | 4 of 236, 1.7 % (0.7 to 4.3 %) | 36 of 1,778, 2.0 % (1.5 to 2.8 %) |
| `lang-mismatch` | 395 of 7,561, 5.2 % (4.7 to 5.7 %) | 932 of 34,368, 2.7 % (2.5 to 2.9 %) |
| `duplicate-block` | 75 of 15,084, 0.50 % (0.40 to 0.62 %) | 633 of 86,003, 0.74 % (0.68 to 0.80 %) |
| `shell-syntax` | 89 of 256, 34.8 % (29.2 to 40.8 %) | 188 of 1,335, 14.1 % (12.3 to 16.1 %) |
| `js-syntax` | 222 of 2,006, 11.1 % (9.8 to 12.5 %) | 571 of 9,335, 6.1 % (5.6 to 6.6 %) |

Intervals are 95 % Wilson intervals. Most common Python syntax errors, CodeAlpaca: `invalid syntax` 150, `expected an indented block after 'for' statement` 44, `expected an indented block after 'if' statement` 30, `expected an indented block after function definition` 18, `unindent does not match any outer indentation level` 9.
Evol-Instruct: `invalid syntax` 785, `unterminated string literal` 231, `expected an indented block after 'for' statement` 56, `expected an indented block after function definition` 53, `expected an indented block after 'if' statement` 46. Most common undefined names: `arr`, `string`, `my_list`, `array`, `np` in CodeAlpaca; `Node`, `np`, `arr`, `TreeNode`, `df`
in Evol-Instruct. The `no-code` rule is left out of the table: its precision has not been
measured since the extractor changed (see Limitations).

**False positives of the undefined-name check.** 50 of the 2,482 undefined-name findings
in CodeAlpaca (in 1,463 blocks) were drawn at random (`python scripts/sample_flags.py data/code_alpaca_20k.json py-undefined-name
--n 50 --seed 0`, which prints the prompt and the full answer with line numbers) and read one
by one, the flagged name looked up in prompt and answer. The verdicts are in
[results/codealpaca-undefined-sample.csv](results/codealpaca-undefined-sample.csv):

- 1 of 50 (2 %, 95 % CI 0.4 to 10.5 %) is a tool error: an answer written in JavaScript
  object notation (`{num: 1}`) parses as Python and is read as Python.
- 34 of 50 (68 %, 54.2 to 79.2 %) name a variable that the record's `input` field defines:
  the flag is right about the answer alone, but the record as a whole supplies the name.
- 15 of 50 (30 %, 19.1 to 43.8 %) are undefined in prompt and answer alike: modules used
  without an import (`datetime`, `math`, `tf`, `keras`, `urllib`, `string`), and helpers,
  models or data that are never defined.

All 50 sampled blocks are whole answers. A first sample, drawn before the extractor took
unfenced answers whole, held at least 9 tool errors in 50: indented function bodies cut out of
their answers, so names the rest of the answer defined looked undefined.

**Truncation flags.** All 13 CodeAlpaca truncation flags from the Python, JSON and bracket
checks (the 3 from bash and node are not included) were read one by one (`python
scripts/sample_flags.py data/code_alpaca_20k.json truncated --n 50 --seed 0 --no-external`;
[results/codealpaca-truncated-read.csv](results/codealpaca-truncated-read.csv)). 8 of 13
(62 %, 95 % CI 35.5 to 82.3 %) are code that stops before its end (cut inside a literal or
after `=`, a final closing brace missing). The other 5 are a missing-parenthesis typo, a
syntax template, an answer that is only a signature, an apostrophe in an output comment and
a string left open in the prompt itself. The Evol-Instruct flags were not read.

**Agreement with pyflakes.** On every Python block that parses, the (name, line) sets of
undefined names were compared with pyflakes 4.1.0
(`python scripts/pyflakes_agreement.py data/code_alpaca_20k.json data/EvolInstruct-Code-80k.json`):

```
code_alpaca_20k.json: 7906 parsing Python blocks; undefined names agree on 7903 (99.96 %), unused imports agree on 7906 (100.00 %); blocks with a name only snippetcheck reports: 3, only pyflakes reports: 0
EvolInstruct-Code-80k.json: 42007 parsing Python blocks; undefined names agree on 41992 (99.96 %), unused imports agree on 42007 (100.00 %); blocks with a name only snippetcheck reports: 15, only pyflakes reports: 0
```

The disagreeing blocks were not read. On the 69 small programs of `tests/scope_corpus.py` the
two agree on all but one, a comprehension in a class body that reads a class variable: Python
raises `NameError` there and snippetcheck reports it, pyflakes does not.

**Data and licences.** CodeAlpaca-20k (sahil2801/CodeAlpaca-20k on the Hugging Face hub,
`code_alpaca_20k.json`, sha256 `58d136bb...210e`) is CC BY 4.0 on its card. Evol-Instruct-Code-80k-v1
(nickrosh/Evol-Instruct-Code-80k-v1, `EvolInstruct-Code-80k.json`, sha256 `df31f664...ab8d8d`)
is CC BY-NC-SA 4.0 on its card. Neither is in this repository: `scripts/fetch_data.sh`
downloads both, and only ids, names and counts derived from them are committed.

## Limitations

- The undefined-name check reads the code alone. In the CodeAlpaca sample above 68 % of its
  findings are variables the `input` field defines; there is no option yet to count names
  bound in the prompt as defined.
- Precision has not been measured by reading for `lang-mismatch`, `shell-syntax`,
  `js-syntax`, `duplicate-block`, `placeholder` and `no-code`. 16 of the
  26 CodeAlpaca placeholder flags are an `__init__` whose
  body is `pass`. An earlier reading of 25 `no-code` flags found 22 answers that were code
  the extractor missed (Ruby, C, SQL, CSS, Perl and others); more languages are recognised
  now, but the rule has not been read again, so `--drop no-code` can delete good records.
- The language guess is a keyword score. `Unexpected token '<'` is still among the
  `js-syntax` messages (42 in CodeAlpaca, 228 in Evol-Instruct): markup the guess
  did not recognise. The `shell-syntax` shares (35 % and 14 %) likely include
  blocks sent to bash wrongly.
- The Python grammar is that of the interpreter running snippetcheck: a 3.10 run rejects
  syntax that only 3.12 accepts (such as reusing the outer quote inside an f-string), and
  error messages differ between versions.
- Truncation is only called when a block also fails to parse, so a snippet cut at a statement
  boundary is not detected (an unterminated fence still is).
- The scope analysis does not unbind a name after `del x`, nor an `except ... as e` name after
  its block, and does not report undefined names listed in `__all__`; pyflakes does all three.
- Fences inside block quotes (`> ```python`) are not extracted.
- Bracket balance for the other languages is a lexical scan, not a parse; Rust lifetimes are
  handled by not treating `'` as a quote in Rust.
- `bash -n` is bash's grammar, so zsh-only syntax is reported; the run above used macOS
  bash 3.2.
- Only Python, JSON, shell and JavaScript are parsed.

## Related tools

- [sftlint](https://github.com/vipul21435/sftlint) checks the structure of chat and
  tool-calling datasets; snippetcheck checks the code inside them.
- [datasieve](https://github.com/vipul21435/datasieve) deduplicates training data; the
  `duplicate-block` rule here only counts exact repeats of code blocks.
- [contamscan](https://github.com/vipul21435/contamscan) looks for benchmark contamination by
  n-gram overlap.
- [pyflakes](https://pypi.org/project/pyflakes/) is the reference for the scope analysis and
  is used in the tests.
- [divscore](https://github.com/vipul21435/divscore): diversity of a text dataset measured at a fixed budget of tokens or texts.
- [datadelta](https://github.com/vipul21435/datadelta): what was added, removed and edited between two versions of a dataset.
- [chatconv](https://github.com/vipul21435/chatconv): converts chat datasets between formats and reports what each conversion loses.

## Licence

MIT, see [LICENSE](LICENSE).

Built by Vipul Raj Jha · https://vipul21435.github.io
