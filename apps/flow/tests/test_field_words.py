"""Every datum the automation editor can offer has its words in English and in Spanish (FLOW-F11:
«the data are named in the screen's language, never with their internal name»).

The editor names a datum by ``flow.fields.<name>`` of ``frontend/locale/{en,es}.json`` (``fieldLabel``
of ``frontend/lib/phrasing.ts``), each part of a dotted path apart (``pathLabel``); a name without its
words falls back to the internal name humanized, in English on a Spanish screen («Start date label»).
Nothing else stops a module from adding a field without them, so this guardrail walks every name the
editor can offer, of every installed module and not only the ones a test hub turns on:

- what each action and read of the catalog asks for and leaves (``action_fields``, ``action_outputs``);
- what each event brings (the «What brought it» data of «Which data?»): the keys of every payload a
  module's ``services.py`` gives ``record_event``, read from its source, since an event declares no
  schema. A payload the reader cannot follow fails too, so a new way of building one is taught here
  instead of slipping by.

The editor's own data (a call's ``status``, an answer's ``approved``…) are checked by
``frontend/lib/phrasing.test.ts``.
"""

import ast
import json
from collections import defaultdict
from pathlib import Path

from django.apps import apps

from apps.flow import queries

LOCALE = Path(apps.get_app_config("flow").path) / "frontend" / "locale"


def words(language: str) -> dict[str, str]:
    return json.loads((LOCALE / f"{language}.json").read_text(encoding="utf-8"))["flow"]["fields"]


def without_words(names: dict[str, set[str]]) -> dict[str, list[str]]:
    """``{name: where it comes from}`` of the names (each part of a dotted one) without their words in
    English or in Spanish."""
    en, es = words("en"), words("es")
    found: dict[str, set[str]] = defaultdict(set)
    for name, where in names.items():
        for part in name.split("."):
            if not (en.get(part, "").strip() and es.get(part, "").strip()):
                found[part] |= where
    return {part: sorted(where)[:3] for part, where in sorted(found.items())}


# --- What the actions and reads ask for and leave ------------------------------------------------


def catalog_names() -> dict[str, set[str]]:
    """Everything the editor offers, the cancellations only «Ask me first» may use included (``ask_first_catalog``)."""
    names: dict[str, set[str]] = defaultdict(set)
    for name, op in queries.ask_first_catalog().items():
        for field in queries.action_fields(op):
            names[field["name"]].add(f"{name} asks for it")
        for output in queries.action_outputs(op):
            names[output].add(f"{name} leaves it")
    return names


def test_the_catalog_reaches_every_module_with_actions():
    covered = {op.app_label for op in queries.catalog_operations().values()}
    assert {"appointment", "reservation", "sale", "task", "inventory"} <= covered
    names = catalog_names()
    assert "appointment.appointment.get leaves it" in names["start_date_label"]
    assert "reservation.reservation.get leaves it" in names["date_label"]
    assert "reservation.reservation.cancel asks for it" in names["reason"]


def test_every_field_an_action_asks_for_or_leaves_has_its_words():
    assert without_words(catalog_names()) == {}


# --- What the events bring ------------------------------------------------------------------------

_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
#: A value the editor never offers on its own (``flatten`` of ``frontend/lib/document.ts``: «a list is
#: never offered»), so its key needs no words.
_LISTS = (ast.List, ast.ListComp, ast.Tuple, ast.Set, ast.SetComp)


class PayloadReader:
    """The keys the payloads of one module's ``record_event`` calls can carry, nested ones included.

    It follows what the modules write: a dict literal (and its ``**`` parts), a name assigned in the same
    function (also by tuple, ``|=``, ``[key] =``, ``update`` or ``setdefault``), a parameter (through the
    callers of its function in the module, a ``**`` one by the keywords they pass), a call of a function
    of the module (what it returns), ``dict(…)``, ``a | b``, ``a if … else b`` and a comprehension whose
    keys are filtered by a known list. Anything else is reported in ``unread``. A value under a key is
    followed when it is a dict literal, a function of the module or a variable that holds one of those
    (assigned, or passed by the callers); any other value (an id, a text, a flag, a method call) counts
    as not a dict.
    """

    def __init__(self, source: str, where: str):
        self.where = where
        self.tree = ast.parse(source)
        self.functions = {node.name: node for node in self.tree.body if isinstance(node, _FUNCTIONS)}
        self.constants = {
            target.id: node.value
            for node in self.tree.body
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        self.parent = {child: node for node in ast.walk(self.tree) for child in ast.iter_child_nodes(node)}
        self.keys: dict[str, set[str]] = defaultdict(set)
        self.unread: list[str] = []
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call) and self._called(node) == "record_event":
                payload = node.args[2] if len(node.args) > 2 else self._keyword(node, "payload")
                site = f"{where}:{node.lineno}"
                for key in self.read(payload, self._scope(node), site, frozenset()):
                    self.keys[key].add(site)

    @staticmethod
    def _called(call: ast.Call) -> str | None:
        func = call.func
        return func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None

    @staticmethod
    def _keyword(call: ast.Call, name: str) -> ast.expr | None:
        return next((keyword.value for keyword in call.keywords if keyword.arg == name), None)

    def _scope(self, node: ast.AST) -> ast.AST:
        while node in self.parent:
            node = self.parent[node]
            if isinstance(node, _FUNCTIONS):
                return node
        return self.tree

    def _unread(self, site: str, expr: ast.AST) -> set[str]:
        self.unread.append(f"{site}: {ast.unparse(expr)[:80]}")
        return set()

    def read(self, expr: ast.expr | None, scope: ast.AST, site: str, seen: frozenset[str]) -> set[str]:
        if expr is None or (isinstance(expr, ast.Constant) and expr.value is None):
            return set()
        if isinstance(expr, ast.Dict):
            keys: set[str] = set()
            for key, value in zip(expr.keys, expr.values, strict=True):
                if key is None:
                    keys |= self.read(value, scope, site, seen)
                elif isinstance(key, ast.Constant) and isinstance(key.value, str):
                    if not isinstance(value, _LISTS):
                        keys.add(key.value)
                        keys |= {f"{key.value}.{inner}" for inner in self._nested(value, scope, seen)}
                else:
                    self._unread(site, key)
            return keys
        if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.BitOr):
            return self.read(expr.left, scope, site, seen) | self.read(expr.right, scope, site, seen)
        if isinstance(expr, ast.IfExp):
            return self.read(expr.body, scope, site, seen) | self.read(expr.orelse, scope, site, seen)
        if isinstance(expr, ast.Name):
            return self._name(expr.id, scope, site, seen)
        if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name):
            if expr.func.id == "dict":
                keys = {keyword.arg for keyword in expr.keywords if keyword.arg}
                for arg in expr.args:
                    keys |= self.read(arg, scope, site, seen)
                return keys
            if expr.func.id in self.functions:
                return self._returned(self.functions[expr.func.id], site, seen)
        if isinstance(expr, ast.DictComp):
            return self._filtered(expr, site)
        return self._unread(site, expr)

    def _nested(self, value: ast.expr, scope: ast.AST, seen: frozenset[str]) -> set[str]:
        """The keys of a value that is itself a dict (``flatten`` offers each of them); none for a value
        that is not one (an id, a number, a text)."""
        if isinstance(value, ast.Dict):
            return self.read(value, scope, f"{self.where}:{value.lineno}", seen)
        if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id in self.functions:
            function = self.functions[value.func.id]
            if function.name in seen:
                return set()
            returns = [node.value for node in ast.walk(function) if isinstance(node, ast.Return)]
            return set().union(*(self._nested(found, function, seen | {function.name}) for found in returns if found))
        if isinstance(value, ast.Name):
            return self._nested_name(value.id, scope, seen)
        return set()

    def _nested_name(self, name: str, scope: ast.AST, seen: frozenset[str]) -> set[str]:
        """A variable that may hold a dict: what it is assigned in the function or, as a parameter, what
        the callers pass; none for anything else (a flag, an id)."""
        assigned = [
            node.value
            for node in ast.walk(scope)
            if isinstance(node, (ast.Assign, ast.AnnAssign))
            and node.value is not None
            and any(
                isinstance(target, ast.Name) and target.id == name
                for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
            )
        ]
        if assigned:
            return set().union(*(self._nested(value, scope, seen) for value in assigned))
        if not isinstance(scope, _FUNCTIONS) or scope.name in seen:
            return set()
        positional, named = self._parameters(scope)
        if name not in named:
            return set()
        keys: set[str] = set()
        for call in ast.walk(self.tree):
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == scope.name:
                passed = self._argument(call, positional, name)
                if passed is not None:
                    keys |= self._nested(passed, self._scope(call), seen | {scope.name})
        return keys

    @staticmethod
    def _parameters(function: ast.AST) -> tuple[list[str], set[str]]:
        """``(positional names, every name)`` of a function's parameters."""
        arguments = function.args
        positional = [arg.arg for arg in (*arguments.posonlyargs, *arguments.args)]
        return positional, {*positional, *(arg.arg for arg in arguments.kwonlyargs)}

    def _argument(self, call: ast.Call, positional: list[str], name: str) -> ast.expr | None:
        """What ``call`` passes as the parameter ``name``, by position or by keyword."""
        index = positional.index(name) if name in positional else None
        return call.args[index] if index is not None and index < len(call.args) else self._keyword(call, name)

    def _returned(self, function: ast.AST, site: str, seen: frozenset[str]) -> set[str]:
        if function.name in seen:
            return set()
        found = [node.value for node in ast.walk(function) if isinstance(node, ast.Return) and node.value]
        return set().union(*(self.read(value, function, site, seen | {function.name}) for value in found))

    def _name(self, name: str, scope: ast.AST, site: str, seen: frozenset[str]) -> set[str]:
        keys: set[str] = set()
        assigned = False
        for node in ast.walk(scope):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == name:
                        assigned = True
                        keys |= self.read(node.value, scope, site, seen)
                    elif isinstance(target, ast.Tuple) and isinstance(node.value, ast.Tuple):
                        for inner, value in zip(target.elts, node.value.elts, strict=True):
                            if isinstance(inner, ast.Name) and inner.id == name:
                                assigned = True
                                keys |= self.read(value, scope, site, seen)
                    elif isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name) and target.value.id == name:
                        if isinstance(target.slice, ast.Constant) and isinstance(target.slice.value, str):
                            keys.add(target.slice.value)
                        else:
                            self._unread(site, target)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name and node.value:
                assigned = True
                keys |= self.read(node.value, scope, site, seen)
            elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
                keys |= self.read(node.value, scope, site, seen)
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == name
            ):
                if node.func.attr == "update":
                    keys |= {keyword.arg for keyword in node.keywords if keyword.arg}
                    for arg in node.args:
                        keys |= self.read(arg, scope, site, seen)
                elif node.func.attr == "setdefault" and node.args:
                    keys |= self.read(ast.Dict(keys=[node.args[0]], values=[ast.Constant(None)]), scope, site, seen)
        if assigned:
            return keys
        if isinstance(scope, _FUNCTIONS):
            passed = self._passed(scope, name, site, seen)
            if passed is not None:
                return keys | passed
        return keys | self._unread(site, ast.Name(name))

    def _passed(self, function: ast.AST, name: str, site: str, seen: frozenset[str]) -> set[str] | None:
        """What the callers of ``function`` in the module pass as its parameter ``name``; ``None`` if it
        has no such parameter."""
        arguments = function.args
        positional, named = self._parameters(function)
        is_rest = arguments.kwarg is not None and arguments.kwarg.arg == name
        if name not in named and not is_rest:
            return None
        if function.name in seen:
            return set()
        inner = seen | {function.name}
        keys: set[str] = set()
        for call in ast.walk(self.tree):
            if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == function.name):
                continue
            scope = self._scope(call)
            if is_rest:
                for keyword in call.keywords:
                    if keyword.arg is None:
                        keys |= self.read(keyword.value, scope, site, inner)
                    elif keyword.arg not in named:
                        keys |= self.read(ast.Dict(keys=[ast.Constant(keyword.arg)], values=[keyword.value]), scope, site, inner)
                continue
            keys |= self.read(self._argument(call, positional, name), scope, site, inner)
        return keys

    def _filtered(self, comprehension: ast.DictComp, site: str) -> set[str]:
        """``{field: … for field, … in … if field in (<known names>)}``: the known names."""
        key = comprehension.key
        for generator in comprehension.generators:
            for condition in generator.ifs:
                if (
                    isinstance(condition, ast.Compare)
                    and isinstance(key, ast.Name)
                    and isinstance(condition.left, ast.Name)
                    and condition.left.id == key.id
                    and isinstance(condition.ops[0], ast.In)
                ):
                    names = self._strings(condition.comparators[0])
                    if names is not None:
                        return names
        return self._unread(site, comprehension)

    def _strings(self, expr: ast.expr) -> set[str] | None:
        if isinstance(expr, ast.Name) and expr.id in self.constants:
            return self._strings(self.constants[expr.id])
        if isinstance(expr, ast.Starred):
            return self._strings(expr.value)
        if isinstance(expr, (ast.Tuple, ast.List, ast.Set)):
            found: set[str] = set()
            for element in expr.elts:
                inner = (
                    {element.value}
                    if isinstance(element, ast.Constant) and isinstance(element.value, str)
                    else self._strings(element)
                )
                if inner is None:
                    return None
                found |= inner
            return found
        return None


def event_names() -> tuple[dict[str, set[str]], list[str]]:
    """``({key: where it is sent}, unread payloads)`` of the events of every installed module."""
    names: dict[str, set[str]] = defaultdict(set)
    unread: list[str] = []
    for label, config in sorted(queries.active_apps().items()):
        services = Path(config.path) / "services.py"
        if not services.exists():
            continue
        reader = PayloadReader(services.read_text(encoding="utf-8"), f"apps/{label}/services.py")
        for key, where in reader.keys.items():
            names[key] |= where
        unread += reader.unread
    return names, unread


SAMPLE = '''
SLOT = ("date", "time")


def _payload(item):
    return {"id": item.id, "nested": {"inner": 1}}


def _event(ctx, name, item, **extra):
    record_event(ctx, name, {"number": item.number, **extra})


def _send(ctx, name, payload):
    record_event(ctx, name, payload)


def notify(ctx, item, person, flag):
    record_event(ctx, "a.b.notified", {"person": person, "flag": flag})
    _event(ctx, "a.b.carried", item, who=person, by=flag)


def create(ctx, item, changes):
    person = {"deep": 1}
    notify(ctx, item, person, True)
    _event(ctx, "a.b.created", item, by_keyword=1, **{"spread": 2})
    _send(ctx, "a.b.sent", {"passed": 1})
    record_event(ctx, "a.b.listed", {"rows": [1, 2], "when": None})
    record_event(ctx, "a.b.called", _payload(item) | dict(merged=1))
    built, other = {"unpacked": 1}, 2
    built["indexed"] = 1
    built.update({"updated": 1})
    built |= {"or_ed": 1}
    built.setdefault("defaulted", 1)
    record_event(ctx, "a.b.built", built)
    told = {field: value for field, value in changes.items() if field in (*SLOT, "guest")}
    record_event(ctx, "a.b.told", {"id": 1, **told})
    record_event(ctx, "a.b.unknown", payload_from_elsewhere())
'''


def test_the_reader_follows_every_way_a_module_builds_a_payload():
    reader = PayloadReader(SAMPLE, "sample.py")
    assert set(reader.keys) == {
        "number", "by_keyword", "spread", "passed", "when", "id", "nested", "nested.inner", "merged",
        "unpacked", "indexed", "updated", "or_ed", "defaulted", "date", "time", "guest",
        "person", "person.deep", "flag", "who", "who.deep", "by",
    }  # fmt: skip
    assert reader.unread == ["sample.py:37: payload_from_elsewhere()"]


def test_the_reader_reads_every_payload_of_the_modules():
    names, unread = event_names()
    assert unread == []
    # Positive control: what Appointments' and Reservations' events carry is found.
    assert {"start", "customer_id", "party_size"} <= set(names)
    assert len(names) > 100


def test_every_datum_an_event_brings_has_its_words():
    assert without_words(event_names()[0]) == {}
