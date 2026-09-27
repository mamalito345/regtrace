"""
regtrace.codefacts
~~~~~~~~~~~~~~~~~~
Generic Python source-code fact extraction using the standard `ast` module.

Extracts objective structural facts from Python source code.
No policy-specific, domain-specific, or company-specific logic lives here.
Semantic classification (e.g. "this call is an external export") belongs
to the Policy ↔ Code Matcher (next milestone).

Fact types
----------
FUNCTION      – a function/method definition
PARAMETER     – a parameter of a function
FIELD_ACCESS  – attribute read:  obj.attr
CALL          – a function/method call
CONDITION     – an expression used as an `if` / `elif` test
RETURN        – a return statement (value is the string repr of the returned expr)
ASSIGNMENT    – a simple assignment (target = value)

Relationships (edges)
---------------------
CONTAINS  – function → {call, field_access, return, assignment, condition}
CALLS     – function → call (direct-call summary)
GUARDS    – condition → call  (condition is the nearest enclosing if-test)
FLOWS_TO  – field_access / name → call argument position (when statically visible)
"""
from __future__ import annotations

import ast
from enum import Enum
from typing import Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Fact model
# ---------------------------------------------------------------------------

class CodeFactKind(str, Enum):
    FUNCTION     = "FUNCTION"
    PARAMETER    = "PARAMETER"
    FIELD_ACCESS = "FIELD_ACCESS"
    CALL         = "CALL"
    CONDITION    = "CONDITION"
    RETURN       = "RETURN"
    ASSIGNMENT   = "ASSIGNMENT"


class RelationKind(str, Enum):
    CONTAINS  = "CONTAINS"
    CALLS     = "CALLS"
    GUARDS    = "GUARDS"
    FLOWS_TO  = "FLOWS_TO"


class CodeFact(BaseModel):
    kind: CodeFactKind
    name: str                        # primary identifier (function name, call expr, etc.)
    detail: Optional[str] = None     # secondary info (field owner, arg repr, etc.)
    function_context: Optional[str] = None   # enclosing function name, if any
    lineno: Optional[int] = None


class CodeRelation(BaseModel):
    kind: RelationKind
    subject: str      # the "from" entity name
    object_: str      # the "to" entity name  (object is a Python builtin)
    detail: Optional[str] = None   # e.g. argument index for FLOWS_TO
    object_lineno: Optional[int] = None   # lineno of the object (call site) for GUARDS


class CodeFactSet(BaseModel):
    """All facts and relations extracted from one source file."""
    filename: str
    facts: list[CodeFact] = []
    relations: list[CodeRelation] = []


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _expr_to_str(node: ast.expr) -> str:
    """Best-effort single-line string representation of an AST expression."""
    try:
        return ast.unparse(node)
    except Exception:
        return "<expr>"


def _call_name(node: ast.Call) -> str:
    """Return a canonical name string for a call node, e.g. 'crm.send'."""
    return _expr_to_str(node.func)


# ---------------------------------------------------------------------------
# Visitor
# ---------------------------------------------------------------------------

class _FactVisitor(ast.NodeVisitor):
    """
    Single-pass AST visitor that builds a CodeFactSet.

    State tracked per visit:
      _current_function   – name of the enclosing function (None at module level)
      _guard_conditions   – stack of condition-expression strings as we enter if-blocks
    """

    def __init__(self, filename: str) -> None:
        self.fs = CodeFactSet(filename=filename)
        self._current_function: Optional[str] = None
        self._guard_stack: list[str] = []   # conditions active at the current node

    # --- helpers ---

    def _add_fact(self, kind: CodeFactKind, name: str, *,
                  detail: str | None = None, lineno: int | None = None) -> None:
        self.fs.facts.append(CodeFact(
            kind=kind,
            name=name,
            detail=detail,
            function_context=self._current_function,
            lineno=lineno,
        ))

    def _add_relation(self, kind: RelationKind, subject: str, object_: str,
                      detail: str | None = None,
                      object_lineno: int | None = None) -> None:
        self.fs.relations.append(CodeRelation(
            kind=kind, subject=subject, object_=object_, detail=detail,
            object_lineno=object_lineno,
        ))

    # --- visitors ---

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._add_fact(CodeFactKind.FUNCTION, node.name, lineno=node.lineno)
        # Parameters
        for arg in node.args.args:
            self._add_fact(CodeFactKind.PARAMETER, arg.arg,
                           detail=node.name, lineno=arg.col_offset or node.lineno)
            self._add_relation(RelationKind.CONTAINS, node.name, arg.arg)

        outer = self._current_function
        self._current_function = node.name
        self.generic_visit(node)
        self._current_function = outer

    # Treat async functions identically
    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_If(self, node: ast.If) -> None:  # noqa: N802
        cond_str = _expr_to_str(node.test)
        self._add_fact(CodeFactKind.CONDITION, cond_str, lineno=node.lineno)
        if self._current_function:
            self._add_relation(RelationKind.CONTAINS, self._current_function, cond_str)

        # Visit the test sub-expression so field-accesses inside it are recorded.
        # We do NOT push the guard yet — the condition itself is not guarded by itself.
        self.visit(node.test)

        self._guard_stack.append(cond_str)
        # Visit body (guarded) and orelse (not guarded by this condition)
        for child in node.body:
            self.visit(child)
        self._guard_stack.pop()
        for child in node.orelse:
            self.visit(child)

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
        # Only emit FIELD_ACCESS for loads (reads), not stores
        if isinstance(node.ctx, ast.Load):
            owner = _expr_to_str(node.value)
            field_name = f"{owner}.{node.attr}"
            self._add_fact(CodeFactKind.FIELD_ACCESS, field_name,
                           detail=owner, lineno=node.lineno)
            if self._current_function:
                self._add_relation(RelationKind.CONTAINS,
                                   self._current_function, field_name)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        call_name = _call_name(node)
        self._add_fact(CodeFactKind.CALL, call_name, lineno=node.lineno)

        if self._current_function:
            self._add_relation(RelationKind.CONTAINS, self._current_function, call_name)
            self._add_relation(RelationKind.CALLS, self._current_function, call_name)

        # GUARDS: each condition currently on the guard stack guards this call
        for cond in self._guard_stack:
            self._add_relation(RelationKind.GUARDS, cond, call_name,
                               object_lineno=node.lineno)

        # FLOWS_TO: track direct argument expressions
        for idx, arg in enumerate(node.args):
            arg_str = _expr_to_str(arg)
            # Only record field accesses and names — skip nested calls etc.
            if isinstance(arg, (ast.Attribute, ast.Name)):
                self._add_relation(RelationKind.FLOWS_TO, arg_str, call_name,
                                   detail=str(idx))

        self.generic_visit(node)

    def visit_Return(self, node: ast.Return) -> None:  # noqa: N802
        val = _expr_to_str(node.value) if node.value else "None"
        self._add_fact(CodeFactKind.RETURN, val, lineno=node.lineno)
        if self._current_function:
            self._add_relation(RelationKind.CONTAINS, self._current_function, val)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        for target in node.targets:
            target_str = _expr_to_str(target)
            val_str = _expr_to_str(node.value)
            self._add_fact(CodeFactKind.ASSIGNMENT, target_str,
                           detail=val_str, lineno=node.lineno)
            if self._current_function:
                self._add_relation(RelationKind.CONTAINS,
                                   self._current_function, target_str)
        self.generic_visit(node)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class AnalysisError(Exception):
    """Raised when source code cannot be parsed."""


class PythonCodeFactsProvider:
    """Analyzes Python source code and returns a CodeFactSet."""

    def analyze_source(self, source: str, filename: str = "<string>") -> CodeFactSet:
        """
        Parse `source` and extract CodeFacts.

        Raises `AnalysisError` on syntax errors so callers get a clear failure
        rather than an empty or misleading fact set.
        """
        try:
            tree = ast.parse(source, filename=filename)
        except SyntaxError as exc:
            raise AnalysisError(
                f"Syntax error in {filename!r}: {exc.msg} (line {exc.lineno})"
            ) from exc

        visitor = _FactVisitor(filename=filename)
        visitor.visit(tree)
        return visitor.fs


# Module-level convenience
def analyze_source(source: str, filename: str = "<string>") -> CodeFactSet:
    return PythonCodeFactsProvider().analyze_source(source, filename)
