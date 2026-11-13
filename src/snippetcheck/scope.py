"""Undefined names and unused imports, from a scope analysis of the AST.

The analysis follows Python's own name resolution:

* module and class bodies are read in order, so a name used before it is bound is
  undefined there;
* function and lambda bodies are read after the enclosing body is complete (they run
  later), so they see every module-level binding, wherever it is;
* a function looks names up in its own scope, then in enclosing function scopes
  (class scopes are skipped, as at run time), then the module, then builtins;
* comprehensions get their own scope; the first iterable is evaluated outside it, and
  an assignment expression binds in the enclosing scope;
* ``global`` and ``nonlocal`` redirect bindings, ``from x import *`` silences the
  undefined-name check for the scopes it can reach, and a name inside a ``try`` body
  that catches ``NameError`` is not reported;
* annotations are checked, including string annotations, which are parsed and checked
  once the module is complete (as forward references); with
  ``from __future__ import annotations`` all annotations are deferred that way.

Nothing is imported or executed.
"""

from __future__ import annotations

import ast
import builtins
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field


class _ClassMagic:
    names = dir()


BUILTINS = frozenset(dir(builtins)) | {"__file__", "__builtins__", "__annotations__",
                                        "WindowsError"}
CLASS_MAGIC = frozenset(_ClassMagic.names)
PYTHON2_BUILTINS = frozenset({
    "raw_input", "xrange", "unicode", "basestring", "long", "unichr", "reduce", "file",
    "execfile", "cmp", "reload", "intern", "buffer", "apply", "coerce",
})


@dataclass
class _Binding:
    kind: str
    line: int = 0
    col: int = 0
    used: bool = False
    label: str = ""  # for imports: the text shown in the report


@dataclass
class _Scope:
    kind: str  # "module", "class", "function", "comprehension"
    bindings: dict[str, _Binding] = field(default_factory=dict)
    globals_: set[str] = field(default_factory=set)
    star: bool = False


@dataclass(frozen=True)
class NameIssue:
    name: str
    line: int
    col: int  # 1-based


@dataclass
class ScopeReport:
    undefined: list[NameIssue]
    unused_imports: list[NameIssue]
    star_import: bool


def _node_name(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


class _Analyzer(ast.NodeVisitor):
    def __init__(self, extra_builtins: Iterable[str] = ()) -> None:
        self.builtins = BUILTINS | frozenset(extra_builtins)
        self.stack: list[_Scope] = []
        self.deferred: list[tuple[list[_Scope], Callable[[], None]]] = []
        self.undefined: list[NameIssue] = []
        self.imports: list[_Binding] = []
        self.handlers: list[set[str]] = [set()]
        self.future_annotations = False
        self.in_annotation = 0
        self.star = False
        self.declared_global: set[str] = set()
        self.all_names: set[str] = set()

    # -- driver -----------------------------------------------------------------
    def run(self, tree: ast.Module) -> ScopeReport:
        self.stack = [_Scope("module")]
        for stmt in tree.body:
            self.visit(stmt)
        while self.deferred:
            stack, job = self.deferred.pop(0)
            self.stack, saved_handlers = stack, self.handlers
            self.handlers = [set()]
            job()
            self.handlers = saved_handlers
        module = self.stack[0] if self.stack else None
        for name in self.all_names:  # names exported through __all__ count as used
            if module is not None and name in module.bindings:
                module.bindings[name].used = True
        # as in pyflakes: a name some function declares global counts as defined
        self.undefined = [i for i in self.undefined if i.name not in self.declared_global]
        unused = [NameIssue(b.label, b.line, b.col) for b in self.imports if not b.used]
        unused.sort(key=lambda i: (i.line, i.col))
        self.undefined.sort(key=lambda i: (i.line, i.col))
        return ScopeReport(self.undefined, unused, self.star)

    def _defer(self, job: Callable[[], None]) -> None:
        self.deferred.append((list(self.stack), job))

    # -- bindings and lookups ---------------------------------------------------
    def bind(self, name: str, kind: str, node: ast.AST | None = None, label: str = "") -> None:
        scope = self.stack[-1]
        if scope.kind == "comprehension" and kind == "walrus":
            scope = next(s for s in reversed(self.stack) if s.kind != "comprehension")
        if name in scope.globals_:
            scope = self.stack[0]
        binding = _Binding(kind, getattr(node, "lineno", 0), getattr(node, "col_offset", -1) + 1,
                           label=label or name)
        previous = scope.bindings.get(name)
        if previous is not None and previous.kind == "import" and not previous.used:
            # rebinding an unused import is a redefinition (as pyflakes counts it), not an
            # unused import; this also covers try/except ImportError fallbacks
            self.imports.remove(previous)
        if kind == "import":
            self.imports.append(binding)
        scope.bindings[name] = binding

    def lookup(self, name: str) -> bool:
        last = len(self.stack) - 1
        for i in range(last, -1, -1):
            scope = self.stack[i]
            if scope.kind == "class" and i != last:
                continue
            if name in scope.globals_:
                module = self.stack[0]
                if name in module.bindings:
                    module.bindings[name].used = True
                    return True
                return module.star or name in self.builtins
            binding = scope.bindings.get(name)
            if binding is not None:
                binding.used = True
                return True
        if any(scope.star for scope in self.stack):
            return True
        if name == "__class__" and any(scope.kind == "class" for scope in self.stack[:-1]):
            return True  # the implicit closure cell of methods
        if name in self.builtins:
            return True
        return name in CLASS_MAGIC and self.stack[-1].kind == "class"

    def load(self, name: str, node: ast.AST) -> None:
        if not self.lookup(name) and "NameError" not in self.handlers[-1]:
            self.undefined.append(NameIssue(name, node.lineno, node.col_offset + 1))

    # -- names ------------------------------------------------------------------
    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Store):
            self.bind(node.id, "assign", node)
        else:  # Load and Del
            self.load(node.id, node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if self.in_annotation and isinstance(node.value, str):
            self._string_annotation(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        if self.in_annotation and _node_name(node.value) == "Literal":
            self.visit(node.value)
            saved, self.in_annotation = self.in_annotation, 0
            self.visit(node.slice)
            self.in_annotation = saved
            return
        self.generic_visit(node)

    def _string_annotation(self, node: ast.Constant) -> None:
        try:
            expr = ast.parse(node.value.strip(), mode="eval")
        except (SyntaxError, ValueError):
            return
        for sub in ast.walk(expr):
            if hasattr(sub, "lineno"):
                sub.lineno, sub.col_offset = node.lineno, node.col_offset
        self._defer(lambda: self._annotation_now(expr.body))

    def _annotation(self, node: ast.AST | None) -> None:
        if node is None:
            return
        if self.future_annotations and not self.deferred_annotation_pass:
            self._defer(lambda: self._annotation_now(node))
            return
        self._annotation_now(node)

    deferred_annotation_pass = False

    def _annotation_now(self, node: ast.AST) -> None:
        saved = self.deferred_annotation_pass
        self.deferred_annotation_pass = True
        self.in_annotation += 1
        self.visit(node)
        self.in_annotation -= 1
        self.deferred_annotation_pass = saved

    # -- statements that bind -----------------------------------------------------
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            name = alias.asname or alias.name.split(".")[0]
            label = f"{alias.name} as {alias.asname}" if alias.asname else alias.name
            self.bind(name, "import", node, label)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = "." * node.level + (node.module or "")
        for alias in node.names:
            if node.module == "__future__":
                if alias.name == "annotations":
                    self.future_annotations = True
                continue
            if alias.name == "*":
                self.stack[-1].star = True
                self.star = True
                continue
            name = alias.asname or alias.name
            label = f"{module}.{alias.name}" + (f" as {alias.asname}" if alias.asname else "")
            self.bind(name, "import", node, label)

    def visit_Global(self, node: ast.Global) -> None:
        if self.stack[-1].kind != "module":
            self.stack[-1].globals_.update(node.names)
            self.declared_global.update(node.names)
            for name in node.names:
                self.stack[0].bindings.setdefault(name, _Binding("global", used=True))

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        for name in node.names:
            self.bind(name, "nonlocal", node)

    def _exports(self, target: ast.AST, value: ast.AST) -> None:
        if (len(self.stack) == 1 and isinstance(target, ast.Name) and target.id == "__all__"
                and isinstance(value, (ast.List, ast.Tuple))):
            self.all_names.update(e.value for e in value.elts
                                  if isinstance(e, ast.Constant) and isinstance(e.value, str))

    def visit_TypeAlias(self, node: ast.AST) -> None:
        self.bind(node.name.id, "assign", node.name)
        pushed = self._type_params(node)
        self.visit(node.value)
        if pushed:
            self.stack.pop()

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._exports(target, node.value)
        self.visit(node.value)
        for target in node.targets:
            self.visit(target)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self._exports(node.target, node.value)
        if isinstance(node.target, ast.Name):
            self.load(node.target.id, node.target)
            self.visit(node.value)
            self.bind(node.target.id, "assign", node.target)
        else:
            self.visit(node.value)
            self.visit(node.target)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._annotation(node.annotation)
        if node.value is not None:
            self.visit(node.value)
            self.visit(node.target)
        elif not isinstance(node.target, ast.Name):
            self.visit(node.target)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self.visit(node.value)
        self.bind(node.target.id, "walrus", node.target)

    def visit_For(self, node: ast.For | ast.AsyncFor) -> None:
        self.visit(node.iter)
        self.visit(node.target)
        for stmt in node.body + node.orelse:
            self.visit(stmt)

    visit_AsyncFor = visit_For

    def visit_Try(self, node: ast.Try) -> None:
        names: set[str] = set()
        for handler in node.handlers:
            types = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
            names.update(n for n in (_node_name(t) for t in types) if n)
        self.handlers.append(names)
        for stmt in node.body:
            self.visit(stmt)
        self.handlers.pop()
        for handler in node.handlers:
            self.visit(handler)
        for stmt in node.orelse + node.finalbody:
            self.visit(stmt)

    visit_TryStar = visit_Try

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is not None:
            self.visit(node.type)
        if node.name:
            self.bind(node.name, "except", node)
        for stmt in node.body:
            self.visit(stmt)

    def visit_MatchAs(self, node: ast.AST) -> None:
        if node.pattern is not None:
            self.visit(node.pattern)
        if node.name:
            self.bind(node.name, "match", node)

    def visit_MatchStar(self, node: ast.AST) -> None:
        if node.name:
            self.bind(node.name, "match", node)

    def visit_MatchMapping(self, node: ast.AST) -> None:
        for key in node.keys:
            self.visit(key)
        for pattern in node.patterns:
            self.visit(pattern)
        if node.rest:
            self.bind(node.rest, "match", node)

    # -- scopes -------------------------------------------------------------------
    def _type_params(self, node: ast.AST) -> bool:
        params = getattr(node, "type_params", None)
        if not params:
            return False
        scope = _Scope("function")
        for param in params:
            scope.bindings[param.name] = _Binding("typeparam", used=True)
        self.stack.append(scope)
        return True

    def _arguments(self, args: ast.arguments) -> list[ast.arg]:
        every = args.posonlyargs + args.args + args.kwonlyargs
        if args.vararg:
            every.append(args.vararg)
        if args.kwarg:
            every.append(args.kwarg)
        return every

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        pushed = self._type_params(node)
        for default in node.args.defaults + [d for d in node.args.kw_defaults if d]:
            self.visit(default)
        every = self._arguments(node.args)
        for arg in every:
            self._annotation(arg.annotation)
        self._annotation(node.returns)
        scope = _Scope("function")
        for arg in every:
            scope.bindings[arg.arg] = _Binding("arg", arg.lineno, arg.col_offset + 1, used=True)
        stack = list(self.stack) + [scope]
        body = node.body
        self.deferred.append((stack, lambda: self._body(body)))
        if pushed:
            self.stack.pop()
        self.bind(node.name, "def", node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def _body(self, body: list[ast.stmt]) -> None:
        for stmt in body:
            self.visit(stmt)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for default in node.args.defaults + [d for d in node.args.kw_defaults if d]:
            self.visit(default)
        scope = _Scope("function")
        for arg in self._arguments(node.args):
            scope.bindings[arg.arg] = _Binding("arg", used=True)
        expr = node.body
        self.deferred.append((list(self.stack) + [scope], lambda: self.visit(expr)))

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        pushed = self._type_params(node)
        for base in node.bases:
            self.visit(base)
        for keyword in node.keywords:
            self.visit(keyword.value)
        self.stack.append(_Scope("class"))
        for stmt in node.body:
            self.visit(stmt)
        self.stack.pop()
        if pushed:
            self.stack.pop()
        self.bind(node.name, "class", node)

    def _comprehension(self, node: ast.AST, results: list[ast.AST]) -> None:
        generators = node.generators
        self.visit(generators[0].iter)
        self.stack.append(_Scope("comprehension"))
        for k, gen in enumerate(generators):
            if k:
                self.visit(gen.iter)
            self.visit(gen.target)
            for cond in gen.ifs:
                self.visit(cond)
        for result in results:
            self.visit(result)
        self.stack.pop()

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._comprehension(node, [node.elt])

    visit_SetComp = visit_ListComp
    visit_GeneratorExp = visit_ListComp

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self._comprehension(node, [node.key, node.value])


def analyse(tree: ast.Module, extra_builtins: Iterable[str] = ()) -> ScopeReport:
    """Return the undefined names and unused imports of a parsed module."""
    return _Analyzer(extra_builtins).run(tree)
