"""The checks at start of what an operation declares for the card of the Hub's assistant: its preview
(``base.E005``), its check (``base.E012``), the records its data name (``base.E009``), the names a person says of them
(``base.E014``) and the currency of its amounts (``base.E011``).
"""

from typing import Any

from django.core import checks
from live import assistant as shared
from live.assistant import NAME_OF, REFERS, preview_of, risk
from live.operations import Operation, registry

from .cards import CURRENCY, _names, active_apps_label, check_of

# The card's helpers by the names this module reads them by (``live.assistant``'s).
_is_money = shared.is_money
_is_signed = shared.is_signed
_output_schema = shared.output_schema
_resolved = shared.resolved
_schema = shared.input_schema

#: Where a read goes on from when its answer is too long to be told at once (``live.assistant``): never a write's data,
#: so a preview or a check reads it from its start, which it can only do when the read does not need one.
READ_ON = "offset"


@checks.register("base")
def check_previews(app_configs=None, **kwargs) -> list[checks.CheckMessage]:
    """``base.E005``: a preview names a read of the write's own app, the data of its answer the card shows and nothing
    the write does not send; only a dangerous write declares one (a normal one's card is a single line), and only an
    amount (``MONEY``, on a whole number) is declared signed."""
    errors: list[checks.CheckMessage] = []
    for op in registry.values():
        declared = preview_of(op)
        problems = [] if declared is None else _preview_problems(op, declared)
        if problems:
            errors.append(
                checks.Error(
                    f"{op.name} declares a preview that {'; '.join(problems)}.",
                    hint='Declare ai={"risk": "high", "preview": {"operation": "<app>.<entity>.<a query>", "fields": '
                    '[<data of its answer>]}} on a dangerous write, with a read whose input the write also takes.',
                    obj=op.name,
                    id="base.E005",
                )
            )
    return errors


def _preview_problems(op: Operation, declared: Any) -> list[str]:
    if not isinstance(declared, dict) or not isinstance(declared.get("operation"), str):
        return ["is not an operation and fields"]
    problems = []
    if op.kind != "command" or risk(op) != "high":
        problems.append("is never shown: it is not dangerous (risk high)")
    read = registry.get(declared["operation"])
    if read is None:
        return [*problems, f"names no operation {declared['operation']}"]
    problems += _read_problems(op, read)
    fields = declared.get("fields")
    if not isinstance(fields, list) or not fields or not all(isinstance(name, str) for name in fields):
        return [*problems, "names no field of its answer"]
    schema = _output_schema(read)
    given = schema.get("properties", {})
    problems += [f"shows {name}, but {read.name} gives no field {name}" for name in fields if name not in given]
    shown = {name: _resolved(given[name], schema.get("$defs", {})) for name in fields if name in given}
    problems += [
        f"marks {name} signed, but it is no amount marked money"
        for name, prop in shown.items()
        if _is_signed(prop) and not (prop.get("type") == "integer" and _is_money(prop))
    ]
    return problems


def _read_problems(op: Operation, read: Operation) -> list[str]:
    """What is wrong with the read the write ``op`` names (its preview or its check): of another app, not a read, or
    reading data the write never takes."""
    problems = []
    if read.app_label != op.app_label:
        problems.append(f"names {read.name}, of another app")
    if read.kind != "query":
        problems.append(f"names {read.name}, not a read")
    problems += [
        f"reads {name}, but the write never takes {name}"
        for name, field in read.input.model_fields.items()
        if name not in op.input.model_fields and (name != READ_ON or field.is_required())
    ]
    return problems


@checks.register("base")
def check_checks(app_configs=None, **kwargs) -> list[checks.CheckMessage]:
    """``base.E012``: a write's check (``check_of``) names a read of its own app whose input the write also takes."""
    errors: list[checks.CheckMessage] = []
    for op in registry.values():
        declared = check_of(op)
        problems = [] if declared is None else _check_problems(op, declared)
        if problems:
            errors.append(
                checks.Error(
                    f"{op.name} declares a check that {'; '.join(problems)}.",
                    hint='Declare ai={"check": "<app>.<entity>.<a query>"} with a read of its own app whose input the '
                    "write also takes.",
                    obj=op.name,
                    id="base.E012",
                )
            )
    return errors


def _check_problems(op: Operation, declared: Any) -> list[str]:
    if not isinstance(declared, str):
        return ["is not the name of a read"]
    read = registry.get(declared)
    if read is None:
        return [f"names no operation {declared}"]
    return _read_problems(op, read)


@checks.register("base")
def check_references(app_configs=None, **kwargs) -> list[checks.CheckMessage]:
    """``base.E009``: a datum marked ``REFERS`` names a read of the operation's own app, of ``base`` or of one it
    requires, that takes the datum (``by``) and the data of its own object it is read with (``within``), and answers
    the record's name (``name``); only text a person says is said as said (``as_said``), never an id."""
    errors: list[checks.CheckMessage] = []
    for op in registry.values():
        schema = _schema(op)
        defs = schema.get("$defs", {})
        problems = [
            f"{path} {problem}"
            for path, declared in _marks(schema, defs)
            for problem in _reference_problems(op, declared)
        ] + [
            f"{path}.{name} {problem}" if path else f"{name} {problem}"
            for path, props in _objects(schema, defs)
            for name, prop in props.items()
            for problem in _beside_problems(prop, props, defs)
        ]
        if problems:
            errors.append(
                checks.Error(
                    f"{op.name} marks a reference that {'; '.join(problems)}.",
                    hint='Mark it json_schema_extra={"refers": {"read": "<app>.<entity>.<a query>", "by": "<its input>", '
                    '"name": "<the datum of its answer that names the record>"}}.',
                    obj=op.name,
                    id="base.E009",
                )
            )
    return errors


def _marks(prop: dict, defs: dict, path: str = "", depth: int = 0, mark: str = REFERS) -> list[tuple[str, Any]]:
    """Each ``mark`` (``REFERS``, else another) of the schema ``prop`` at any depth, with the path of its datum."""
    if depth > 8:  # a schema that names itself
        return []
    prop = _unreferred(prop, defs)
    found = [(path, prop[mark])] if mark in prop else []
    for branch in [*prop.get("anyOf", []), *prop.get("oneOf", []), *prop.get("allOf", [])]:
        found += _marks(branch, defs, path, depth + 1, mark)
    for name, inner in prop.get("properties", {}).items():
        found += _marks(inner, defs, f"{path}.{name}" if path else name, depth + 1, mark)
    if isinstance(prop.get("items"), dict):
        found += _marks(prop["items"], defs, f"{path}[]", depth + 1, mark)
    return found


@checks.register("base")
def check_names(app_configs=None, **kwargs) -> list[checks.CheckMessage]:
    """``base.E014``: a text marked ``NAME_OF`` (the name a person says of a record, as a booking's service by its name:
    hub#860; never an id) names a datum of its own object that names a record (``REFERS``, or an id). A mark that
    names any other leaves the line said by how many, with nothing said at start."""
    errors: list[checks.CheckMessage] = []
    for op in registry.values():
        schema = _schema(op)
        defs = schema.get("$defs", {})
        problems = [
            f"{path}.{name} {problem}" if path else f"{name} {problem}"
            for path, props in _objects(schema, defs)
            for name, prop in props.items()
            for problem in _name_problems(_resolved(prop, defs), props, defs)
        ]
        if problems:
            errors.append(
                checks.Error(
                    f"{op.name} marks a name that {'; '.join(problems)}.",
                    hint='Mark the text json_schema_extra={"name_of": "<the datum of its own object that names the record '
                    'by its id>"}.',
                    obj=op.name,
                    id="base.E014",
                )
            )
    return errors


def _name_problems(prop: dict, props: dict, defs: dict) -> list[str]:
    if NAME_OF not in prop:
        return []
    of = prop[NAME_OF]
    if not isinstance(of, str):
        return ["is not the name of a datum"]
    # An id is no text a person says: the card never says one, so the line would stay in «1 elemento».
    problems = [] if prop.get("type") == "string" and prop.get("format") != "uuid" else ["is no text"]
    if of not in props:
        return [*problems, f"names no {of} of its own object"]
    record = _resolved(props[of], defs)
    if REFERS not in record and record.get("format") != "uuid":
        problems.append(f"names {of}, which is no record")
    return problems


def _unreferred(prop: dict, defs: dict) -> dict:
    """``prop`` with the schema its ``$ref`` names, what it says itself on top."""
    ref = prop.get("$ref")
    if not ref:
        return prop
    return {**defs.get(ref.rsplit("/", 1)[-1], {}), **{key: inner for key, inner in prop.items() if key != "$ref"}}


def _objects(prop: dict, defs: dict, path: str = "", depth: int = 0) -> list[tuple[str, dict]]:
    """Each object of the schema ``prop`` at any depth, by the path of its datum, with its properties."""
    if depth > 8:  # a schema that names itself
        return []
    prop = _unreferred(prop, defs)
    props = prop.get("properties", {})
    found = [(path, props)] if props else []
    for branch in [*prop.get("anyOf", []), *prop.get("oneOf", []), *prop.get("allOf", [])]:
        found += _objects(branch, defs, path, depth + 1)
    for name, inner in props.items():
        found += _objects(inner, defs, f"{path}.{name}" if path else name, depth + 1)
    if isinstance(prop.get("items"), dict):
        found += _objects(prop["items"], defs, f"{path}[]", depth + 1)
    return found


@checks.register("base")
def check_currencies(app_configs=None, **kwargs) -> list[checks.CheckMessage]:
    """``base.E011``: a datum marked ``CURRENCY`` is a code (``True``) or names a record by a read of the operation's
    own app, of ``base`` or of one it requires, that takes the datum (``by``) and answers its currency (``code``)."""
    errors: list[checks.CheckMessage] = []
    for op in registry.values():
        schema = _schema(op)
        problems = [
            f"{path} {problem}"
            for path, declared in _marks(schema, schema.get("$defs", {}), mark=CURRENCY)
            for problem in _currency_problems(op, declared)
        ]
        if problems:
            errors.append(
                checks.Error(
                    f"{op.name} marks a currency that {'; '.join(problems)}.",
                    hint='Mark a code json_schema_extra={"currency": True}, or the datum that names a record in a currency '
                    'of its own base.schemas.assistant.in_currency_of("<app>.<entity>.<a query>", by="<its input>", '
                    'code="<the datum of its answer that gives the currency>").',
                    obj=op.name,
                    id="base.E011",
                )
            )
    return errors


def _currency_problems(op: Operation, declared: Any) -> list[str]:
    if declared is True:
        return []
    if not isinstance(declared, dict) or not all(isinstance(declared.get(key), str) for key in ("read", "by", "code")):
        return ["is not true nor a read, by and code"]
    return _reference_problems(op, {"read": declared["read"], "by": declared["by"], "name": declared["code"]})


def _beside_problems(prop: dict, props: dict, defs: dict) -> list[str]:
    """What is wrong with the datum ``prop`` of an object (``props``) a mark reads with the data beside it
    (``within``), leaves unread beside others (``unless``) or says as said (``as_said``): data its own object does not
    have, or an id said as said."""
    declared = prop.get(REFERS)
    if not isinstance(declared, dict):
        return []
    problems = [
        f"is {verb} with {name}, which its own object does not have"
        for key, verb in (("within", "read"), ("unless", "left unread"))
        for name in (declared.get(key) if isinstance(declared.get(key), list) else [])
        if isinstance(name, str) and name not in props
    ]
    if declared.get("as_said") is True and _is_id(prop, defs):
        problems.append("is said as said, but it is an id")
    return problems


def _is_id(prop: dict, defs: dict, depth: int = 0) -> bool:
    """Whether the schema ``prop`` is an id (``format: uuid``), on its own or as a branch of its union."""
    prop = _unreferred(prop, defs)
    branches = [*prop.get("anyOf", []), *prop.get("oneOf", [])]
    return prop.get("format") == "uuid" or (depth < 8 and any(_is_id(branch, defs, depth + 1) for branch in branches))


def _reference_problems(op: Operation, declared: Any) -> list[str]:
    if (
        not isinstance(declared, dict)
        or not all(isinstance(declared.get(key), str) for key in ("read", "by"))
        or not _names(declared)
        or not all(isinstance(name, str) for name in _names(declared))
        or not isinstance(declared.get("within", []), list)
        or not all(isinstance(name, str) for name in declared.get("within", []))
        or not isinstance(declared.get("as_said", False), bool)
        or not isinstance(declared.get("unless", []), list)
        or not all(isinstance(name, str) for name in declared.get("unless", []))
    ):
        return ["is not a read, by and name"]
    read = registry.get(declared["read"])
    if read is None:
        return [f"names no operation {declared['read']}"]
    problems = []
    if read.kind != "query":
        problems.append(f"names {read.name}, not a read")
    own = active_apps_label(op.app_label)
    if read.app_label not in {op.app_label, "base", *(own.requires if own else ())}:
        problems.append(f"names {read.name}, of {read.app_label}, which {op.app_label} does not require")
    problems += [
        f"names {read.name}, which takes no {name}"
        for name in [declared["by"], *declared.get("within", [])]
        if name not in read.input.model_fields
    ]
    given = _output_schema(read).get("properties", {})
    problems += [f"names {read.name}, which gives no {name}" for name in _names(declared) if name not in given]
    return problems
