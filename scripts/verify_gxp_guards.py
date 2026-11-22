"""Fast static GxP guards for bioprocesos-PROJECT (stdlib only, read-only, < 2 s).

Default checks (run by the Kiro hooks in .kiro/hooks/ and by the CI):

1. ``src/``: every module parses (no syntax errors); no NaN/Inf in module-level numeric
   constants or class-level defaults (AST constant folding); ``config.mode`` and
   ``glucose_feedback_in_static`` never reach the kinetic law of ``bioreactor_twin.py``
   (forbidden names in ``_build_rhs`` and the kinetic helpers, plus a data- and
   control-flow taint check on every argument of every ``_build_rhs(...)`` call).
2. Every ``.py``, ``.md``, ``.json``, ``.yml`` and ``.yaml`` file of the repository is valid
   UTF-8 without BOM (files from ``git ls-files``; filesystem walk when git is unavailable).
3. Every JSON file under ``.kiro/`` and ``data/`` is strict JSON (no NaN/Infinity, no
   duplicate keys), and ``.kiro/hooks/*.json`` follow the Kiro v1 hook schema.
4. Front matter of ``.kiro/steering/*.md`` and ``.kiro/agents/*.md`` (flat YAML subset with
   JSON flow values, so the standard library can validate it).

Options:
  --hook             Read the Kiro hook event (JSON on stdin) and run only when the edited
                     path is under src/, docs/, data/ or .kiro/. When the event names no
                     path, or cannot be read, the checks run anyway (fail-safe).
  --frozen-base REF  Also compare the AST (docstrings removed) of the frozen symbols with
                     git REF, e.g. v1.4.0 or origin/main (gxp-scientific-integrity steering).

Exit status: 0 = pass, 1 = findings (stderr, "path:line: [check] message"), 2 = usage
error. The script never writes files; docs/04 is only written by ``pytest tests/``.

Usage (repository root, PowerShell or bash):  python scripts/verify_gxp_guards.py
"""

import argparse
import ast
import json
import math
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEXT_SUFFIXES = {".py", ".md", ".json", ".yml", ".yaml"}
SKIP_DIRS = {".git", ".hypothesis", ".pytest_cache", ".mypy_cache", ".ruff_cache", "__pycache__",
             "node_modules", ".venv", "venv", "env", ".tox", ".nox", ".worktrees"}
GUARDED_TREES = ("src", "docs", "data", ".kiro")
TIME_BUDGET_S = 2.0

# --- Check 1: config.mode must never reach the kinetic law (bioreactor_twin.py) -------------
TWIN_MODULE = "src/bioreactor_twin.py"
RHS_BUILDER = "_build_rhs"
SIMULATOR = "simulate_cho_fed_batch"
KINETIC_FUNCTIONS = ("_build_rhs", "_interp_temperature", "do_hypoxia_factor",
                     "compute_dissolved_oxygen_state", "compute_hydrodynamic_stress")
MODE_ATTRIBUTES = {"mode", "glucose_feedback_in_static"}
KINETIC_FORBIDDEN_NAMES = {"config", "cfg", "mode", "ARK_ADAPTIVE_FACTORS"}
KINETIC_FORBIDDEN_STRINGS = {"static", "closed_loop"}
NON_FINITE_ATTRIBUTES = {"nan", "NaN", "NAN", "inf", "Inf", "infty", "Infinity", "PINF", "NINF"}

# --- Optional check: frozen symbols (compared with --frozen-base REF) ------------------------
# (file, top-level symbol); None = the whole module. Docstrings are ignored.
FROZEN_SYMBOLS = (
    ("src/amab_design_space.py", "evaluate_amab_design_space"),
    ("src/audit_trail_part11.py", "AuditTrailLogger"),
    ("src/thermal_vtb_mkt.py", None),
)

# --- Checks 3 and 4: Kiro configuration (kiro.dev/docs/hooks, /steering, /custom-agents) -----
KIRO_HOOK_TRIGGERS = {
    "PreToolUse", "PermissionRequest", "PostToolUse", "SessionStart", "SessionEnd", "Stop",
    "SubagentStop", "UserPromptSubmit", "PreTaskExec", "PostTaskExec", "PreCompact",
    "PostCompact", "PostFileCreate", "PostFileSave", "PostFileDelete",
}
STEERING_KEYS = {"inclusion", "fileMatchPattern", "name", "description"}
STEERING_INCLUSION = {"always", "fileMatch", "manual", "auto"}
AGENT_KEYS = {"name", "description", "prompt", "model", "tools", "excludedTools", "includeMcpJson",
              "includePowers", "mcpServers", "resources", "permissions", "welcomeMessage", "hooks"}
PERMISSION_EFFECTS = {"allow", "ask", "deny", "evaluate"}
FRONT_MATTER_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):(?:[ \t]+(.*))?$")


class Findings:
    """Collects ``path:line: [check] message`` findings."""

    def __init__(self):
        self.items: list[tuple[str, int, str, str]] = []

    def add(self, path, line, check, message):
        self.items.append((str(path), int(line or 0), check, message))

    def __len__(self):
        return len(self.items)


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


# =============================================================================================
# Check 1: src/ syntax, non-finite constants and config.mode leaks into the kinetics
# =============================================================================================
def parse_sources(findings: Findings) -> dict:
    """Parse every src/**/*.py file; syntax and decoding errors become findings."""
    trees = {}
    paths = sorted((ROOT / "src").rglob("*.py"))
    if not paths:
        findings.add("src", 0, "src", "no Python modules found under src/")
    for path in paths:
        rel = _rel(path)
        try:
            trees[rel] = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        except SyntaxError as exc:
            findings.add(rel, exc.lineno, "src", f"syntax error: {exc.msg}")
        except UnicodeDecodeError as exc:
            findings.add(rel, 0, "src", f"not valid UTF-8 ({exc.reason})")
    return trees


class _NotFoldable(Exception):
    """The expression is not a numeric constant expression."""


def _fold(node, env):
    """Evaluate a numeric constant expression (numbers, + - * / **, known names, NaN spellings)."""
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return node.value
    if isinstance(node, ast.Name) and node.id in env:
        return env[node.id]
    if isinstance(node, ast.Attribute) and node.attr in NON_FINITE_ATTRIBUTES:
        return float("nan") if node.attr.lower() == "nan" else float("inf")
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "float"
            and len(node.args) == 1 and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)):
        return float(node.args[0].value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _fold(node.operand, env)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
        left, right = _fold(node.left, env), _fold(node.right, env)
        ops = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
               ast.Div: lambda a, b: a / b, ast.Pow: lambda a, b: a ** b}
        return ops[type(node.op)](left, right)
    if isinstance(node, (ast.Tuple, ast.List, ast.Set, ast.Dict)):
        # Containers: keep the foldable elements (a NaN next to a string is still found).
        elements = node.values if isinstance(node, ast.Dict) else node.elts
        folded = []
        for element in elements:
            try:
                folded.append(_fold(element, env))
            except _NotFoldable:
                continue
        return tuple(folded)
    raise _NotFoldable


def _non_finite(value) -> bool:
    if isinstance(value, tuple):
        return any(_non_finite(v) for v in value)
    return isinstance(value, float) and not math.isfinite(value)


def check_constants(trees: dict, findings: Findings) -> int:
    """No NaN/Inf in module-level constants or class-level defaults (e.g. dataclass fields)."""
    checked = 0
    for rel, tree in trees.items():
        env = {}
        scopes = [(tree.body, True)] + [(n.body, False) for n in tree.body if isinstance(n, ast.ClassDef)]
        for body, module_level in scopes:
            for stmt in body:
                if isinstance(stmt, ast.Assign):
                    targets, value = stmt.targets, stmt.value
                elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
                    targets, value = [stmt.target], stmt.value
                else:
                    continue
                try:
                    folded = _fold(value, env)
                except _NotFoldable:
                    continue
                except (ArithmeticError, ValueError) as exc:
                    findings.add(rel, stmt.lineno, "src", f"constant expression cannot be evaluated ({exc})")
                    continue
                checked += 1
                if _non_finite(folded):
                    names = ", ".join(t.id for t in targets if isinstance(t, ast.Name)) or "constant"
                    findings.add(rel, stmt.lineno, "src", f"non-finite value (NaN/Inf) in {names}")
                if module_level:
                    env.update({t.id: folded for t in targets if isinstance(t, ast.Name)})
    return checked


def _target_names(target):
    """Base names bound or mutated by an assignment target (x, x[i], x.a, (x, y), *x)."""
    if isinstance(target, ast.Name):
        yield target.id
    elif isinstance(target, (ast.Tuple, ast.List)):
        for element in target.elts:
            yield from _target_names(element)
    elif isinstance(target, ast.Starred):
        yield from _target_names(target.value)
    elif isinstance(target, (ast.Subscript, ast.Attribute)):
        base = target.value
        while isinstance(base, (ast.Subscript, ast.Attribute)):
            base = base.value
        if isinstance(base, ast.Name):
            yield base.id


def _mentions_mode(expr, tainted: set) -> bool:
    """True when ``expr`` reads config.mode / glucose_feedback_in_static or a tainted name."""
    for node in ast.walk(expr):
        if isinstance(node, ast.Attribute) and node.attr in MODE_ATTRIBUTES:
            return True
        if isinstance(node, ast.Name) and (node.id in tainted or node.id == "ARK_ADAPTIVE_FACTORS"):
            return True
    return False


_COMPOUND = (ast.If, ast.While, ast.For, ast.AsyncFor, ast.With, ast.AsyncWith, ast.Try,
             ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _collect_flows(statements, guarded, flows):
    """Record (targets, value, guards) for every binding, with the enclosing control conditions.

    A binding inside ``if``/``while``/``for`` whose condition or iterable reads the mode is
    tainted even when its value does not (implicit flow).
    """
    for stmt in statements:
        if isinstance(stmt, ast.Assign):
            flows.append((stmt.targets, stmt.value, guarded))
        elif isinstance(stmt, (ast.AugAssign, ast.AnnAssign)) and stmt.value is not None:
            flows.append(([stmt.target], stmt.value, guarded))
        elif isinstance(stmt, (ast.For, ast.AsyncFor)):
            flows.append(([stmt.target], stmt.iter, guarded))
        if not isinstance(stmt, _COMPOUND):
            for node in ast.walk(stmt):
                if isinstance(node, ast.NamedExpr):
                    flows.append(([node.target], node.value, guarded))
        if isinstance(stmt, (ast.If, ast.While)):
            inner = guarded + [stmt.test]
            _collect_flows(stmt.body, inner, flows)
            _collect_flows(stmt.orelse, inner, flows)
        elif isinstance(stmt, (ast.For, ast.AsyncFor)):
            _collect_flows(stmt.body, guarded + [stmt.iter], flows)
            _collect_flows(stmt.orelse, guarded, flows)
        elif isinstance(stmt, (ast.With, ast.AsyncWith)):
            _collect_flows(stmt.body, guarded, flows)
        elif isinstance(stmt, ast.Try):
            for block in (stmt.body, stmt.orelse, stmt.finalbody, *[h.body for h in stmt.handlers]):
                _collect_flows(block, guarded, flows)
        elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _collect_flows(stmt.body, guarded, flows)


def _tainted_names(function: ast.FunctionDef) -> set:
    """Names that carry information from config.mode (data or control flow), to a fixpoint."""
    flows = []
    _collect_flows(function.body, [], flows)
    tainted: set = set()
    changed = True
    while changed:
        changed = False
        for targets, value, guards in flows:
            if _mentions_mode(value, tainted) or any(_mentions_mode(g, tainted) for g in guards):
                for target in targets:
                    for name in _target_names(target):
                        if name not in tainted:
                            tainted.add(name)
                            changed = True
    return tainted


def check_mode_leak(trees: dict, findings: Findings) -> int:
    """config.mode never enters _build_rhs, the kinetic helpers or the arguments of _build_rhs."""
    tree = trees.get(TWIN_MODULE)
    if tree is None:
        findings.add(TWIN_MODULE, 0, "mode-leak", "module missing or not parsable; RHS not verified")
        return 0
    functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    for name in KINETIC_FUNCTIONS:
        function = functions.get(name)
        if function is None:
            findings.add(TWIN_MODULE, 0, "mode-leak", f"kinetic function {name}() not found; RHS not verified")
            continue
        arguments = function.args.posonlyargs + function.args.args + function.args.kwonlyargs
        for arg in arguments:
            if arg.arg in KINETIC_FORBIDDEN_NAMES:
                findings.add(TWIN_MODULE, arg.lineno, "mode-leak", f"{name}() takes '{arg.arg}' as an argument")
        for node in ast.walk(function):
            if isinstance(node, ast.Name) and node.id in KINETIC_FORBIDDEN_NAMES:
                findings.add(TWIN_MODULE, node.lineno, "mode-leak", f"{name}() reads '{node.id}'")
            elif isinstance(node, ast.Attribute) and node.attr in MODE_ATTRIBUTES:
                findings.add(TWIN_MODULE, node.lineno, "mode-leak", f"{name}() reads '.{node.attr}'")
            elif isinstance(node, ast.Constant) and node.value in KINETIC_FORBIDDEN_STRINGS:
                findings.add(TWIN_MODULE, node.lineno, "mode-leak", f"{name}() branches on mode literal {node.value!r}")
    simulator = functions.get(SIMULATOR)
    if simulator is None:
        findings.add(TWIN_MODULE, 0, "mode-leak", f"{SIMULATOR}() not found; RHS arguments not verified")
        return len(KINETIC_FUNCTIONS)
    tainted = _tainted_names(simulator)
    calls = [n for n in ast.walk(simulator)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == RHS_BUILDER]
    if not calls:
        findings.add(TWIN_MODULE, simulator.lineno, "mode-leak", f"no {RHS_BUILDER}() call in {SIMULATOR}()")
    for call in calls:
        for position, arg in enumerate(list(call.args) + [k.value for k in call.keywords]):
            if _mentions_mode(arg, tainted):
                findings.add(TWIN_MODULE, arg.lineno, "mode-leak",
                             f"argument {position} of {RHS_BUILDER}() depends on config.mode "
                             f"({ast.unparse(arg)})")
    return len(KINETIC_FUNCTIONS) + len(calls)


# =============================================================================================
# Check 2: UTF-8 without BOM
# =============================================================================================
def _repository_files():
    """Tracked plus untracked, non-ignored files (git); filesystem walk as a fallback."""
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            capture_output=True, check=True, timeout=20,
        )
        names = result.stdout.decode("utf-8", "surrogateescape").split("\0")
        return [ROOT / name for name in names if name], "git ls-files"
    except (OSError, subprocess.SubprocessError):
        files = []
        for directory, subdirs, filenames in os.walk(ROOT):
            subdirs[:] = [d for d in subdirs if d not in SKIP_DIRS and not d.startswith(".venv")]
            files.extend(Path(directory) / name for name in filenames)
        return files, "filesystem walk"


def check_utf8(findings: Findings) -> tuple[int, str]:
    files, source = _repository_files()
    text_files = sorted({p for p in files if p.suffix.lower() in TEXT_SUFFIXES and p.is_file()})
    for path in text_files:
        rel = _rel(path)
        data = path.read_bytes()
        if data.startswith(b"\xef\xbb\xbf"):
            findings.add(rel, 1, "utf8", "UTF-8 BOM present (save as UTF-8 without BOM)")
            continue
        if data.startswith((b"\xff\xfe", b"\xfe\xff")):
            findings.add(rel, 1, "utf8", "UTF-16 BOM: the file is not UTF-8")
            continue
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            line = data[: exc.start].count(b"\n") + 1
            findings.add(rel, line, "utf8", f"invalid UTF-8 byte sequence at offset {exc.start}")
    return len(text_files), source


# =============================================================================================
# Check 3: strict JSON in .kiro/ and data/, Kiro v1 hook schema
# =============================================================================================
def strict_json_loads(text: str):
    """json.loads that rejects NaN/Infinity (not JSON per RFC 8259) and duplicate keys."""
    def reject_constant(name):
        raise ValueError(f"non-standard JSON constant {name}")

    def reject_duplicates(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError(f"duplicate key {key!r}")
            obj[key] = value
        return obj

    return json.loads(text, parse_constant=reject_constant, object_pairs_hook=reject_duplicates)


def _is_text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _check_hook_file(rel: str, config, findings: Findings) -> None:
    if not isinstance(config, dict) or config.get("version") != "v1":
        findings.add(rel, 1, "kiro-hooks", 'top level must be an object with "version": "v1"')
        return
    hooks = config.get("hooks")
    if not isinstance(hooks, list) or not hooks:
        findings.add(rel, 1, "kiro-hooks", '"hooks" must be a non-empty array')
        return
    for i, hook in enumerate(hooks):
        where = f"hooks[{i}]"
        if not isinstance(hook, dict):
            findings.add(rel, 0, "kiro-hooks", f"{where} must be an object")
            continue
        if not _is_text(hook.get("name")):
            findings.add(rel, 0, "kiro-hooks", f"{where}.name is required")
        if hook.get("trigger") not in KIRO_HOOK_TRIGGERS:
            findings.add(rel, 0, "kiro-hooks", f"{where}.trigger {hook.get('trigger')!r} is not a known Kiro trigger")
        action = hook.get("action")
        kind = action.get("type") if isinstance(action, dict) else None
        if kind == "command" and not _is_text(action.get("command")):
            findings.add(rel, 0, "kiro-hooks", f"{where}.action.command is required for type 'command'")
        elif kind == "agent" and not _is_text(action.get("prompt")):
            findings.add(rel, 0, "kiro-hooks", f"{where}.action.prompt is required for type 'agent'")
        elif kind not in ("command", "agent"):
            findings.add(rel, 0, "kiro-hooks", f"{where}.action.type must be 'command' or 'agent'")
        if "matcher" in hook:
            try:
                re.compile(hook["matcher"])
            except (re.error, TypeError) as exc:
                findings.add(rel, 0, "kiro-hooks", f"{where}.matcher is not a valid regex ({exc})")
        timeout = hook.get("timeout", 0)
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout < 0:
            findings.add(rel, 0, "kiro-hooks", f"{where}.timeout must be a number >= 0")
        if not isinstance(hook.get("enabled", True), bool):
            findings.add(rel, 0, "kiro-hooks", f"{where}.enabled must be a boolean")


def check_json(findings: Findings) -> int:
    paths = sorted(p for tree in (".kiro", "data") for p in (ROOT / tree).rglob("*.json") if p.is_file())
    for path in paths:
        rel = _rel(path)
        try:
            config = strict_json_loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            findings.add(rel, exc.lineno, "json", f"invalid JSON: {exc.msg}")
            continue
        except (ValueError, UnicodeDecodeError) as exc:
            findings.add(rel, 0, "json", f"invalid JSON: {exc}")
            continue
        if path.parent == ROOT / ".kiro" / "hooks":
            _check_hook_file(rel, config, findings)
        elif path.parent == ROOT / ".kiro" / "agents":
            _check_agent_config(rel, config, findings)
    return len(paths)


# =============================================================================================
# Check 4: front matter of .kiro/steering/*.md and .kiro/agents/*.md
# =============================================================================================
def parse_front_matter(text: str):
    """Return (fields, body) of a Markdown file; fields is None when there is no front matter.

    Supported subset (valid YAML): one ``key: value`` per line, where value is a plain
    scalar, a double-quoted string or a JSON flow list/object. Raises ValueError otherwise.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, text
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        raise ValueError("front matter opened with '---' but never closed") from None
    fields = {}
    for number, raw in enumerate(lines[1:end], start=2):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        match = FRONT_MATTER_KEY.match(raw.rstrip())
        if raw[0] in " \t" or not match:
            raise ValueError(f"line {number}: expected 'key: value' (nested blocks: use JSON flow style)")
        key, value = match.group(1), (match.group(2) or "").strip()
        if key in fields:
            raise ValueError(f"line {number}: duplicate key {key!r}")
        if value[:1] in ('"', "[", "{"):
            value = strict_json_loads(value)
        elif value[:1] in ("'", "&", "*", "!", "|", ">", "%", "@", "`") or ": " in value or " #" in value:
            raise ValueError(f"line {number}: quote the value of {key!r} with double quotes")
        elif value in ("true", "false"):
            value = value == "true"
        fields[key] = value
    return fields, "\n".join(lines[end + 1:])


def _is_text_list(value) -> bool:
    return isinstance(value, list) and bool(value) and all(_is_text(v) for v in value)


def _check_agent_config(rel: str, fields: dict, findings: Findings) -> None:
    if not isinstance(fields, dict):
        findings.add(rel, 1, "kiro-agents", "agent configuration must be an object")
        return
    for key in sorted(set(fields) - AGENT_KEYS):
        findings.add(rel, 1, "kiro-agents", f"unknown agent field {key!r}")
    for key in ("name", "description", "prompt", "model", "welcomeMessage"):
        if key in fields and not _is_text(fields[key]):
            findings.add(rel, 1, "kiro-agents", f"{key} must be a non-empty string")
    for key in ("tools", "excludedTools", "resources"):
        if key in fields and not isinstance(fields[key], list):
            findings.add(rel, 1, "kiro-agents", f"{key} must be a list")
    permissions = fields.get("permissions")
    if permissions is not None:
        rules = permissions.get("rules") if isinstance(permissions, dict) else None
        if not isinstance(rules, list):
            findings.add(rel, 1, "kiro-agents", 'permissions must be an object with a "rules" list')
            return
        for i, rule in enumerate(rules):
            ok = (isinstance(rule, dict) and _is_text(rule.get("capability"))
                  and rule.get("effect") in PERMISSION_EFFECTS
                  and all(_is_text_list(rule[k]) for k in ("match", "exclude") if k in rule))
            if not ok:
                findings.add(rel, 1, "kiro-agents",
                             f"permissions.rules[{i}] needs capability, effect in {sorted(PERMISSION_EFFECTS)} "
                             "and optional non-empty match/exclude lists")


def check_front_matter(findings: Findings) -> int:
    paths = sorted((ROOT / ".kiro" / "steering").glob("*.md")) + sorted((ROOT / ".kiro" / "agents").rglob("*.md"))
    for path in paths:
        rel = _rel(path)
        try:
            fields, body = parse_front_matter(path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            findings.add(rel, 1, "front-matter", str(exc))
            continue
        if path.parent.name == "steering":
            if fields is None:
                continue  # no front matter: Kiro includes the file always
            for key in sorted(set(fields) - STEERING_KEYS):
                findings.add(rel, 1, "front-matter", f"unknown steering field {key!r}")
            inclusion = fields.get("inclusion", "always")
            if inclusion not in STEERING_INCLUSION:
                findings.add(rel, 1, "front-matter", f"inclusion {inclusion!r} not in {sorted(STEERING_INCLUSION)}")
            pattern = fields.get("fileMatchPattern")
            if inclusion == "fileMatch" and not (_is_text(pattern) or _is_text_list(pattern)):
                findings.add(rel, 1, "front-matter", "fileMatch needs fileMatchPattern (string or list of strings)")
            if inclusion == "auto" and not (_is_text(fields.get("name")) and _is_text(fields.get("description"))):
                findings.add(rel, 1, "front-matter", "inclusion auto needs name and description")
        else:
            if fields is None:
                findings.add(rel, 1, "front-matter", "agent file needs YAML front matter")
                continue
            _check_agent_config(rel, fields, findings)
            if not body.strip():
                findings.add(rel, 1, "front-matter", "agent body (system prompt) is empty")
    return len(paths)


# =============================================================================================
# Optional: frozen symbols against a git reference (--frozen-base REF)
# =============================================================================================
def _strip_docstrings(tree):
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                node.body = body[1:] or [ast.Pass()]
    return tree


def _symbol_fingerprint(source: str, symbol, filename: str):
    """ast.dump of a top-level symbol (or the module) without docstrings; (None, 0) if absent."""
    tree = _strip_docstrings(ast.parse(source, filename=filename))
    if symbol is None:
        return ast.dump(tree, include_attributes=False), 1
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == symbol:
            return ast.dump(node, include_attributes=False), node.lineno
    return None, 0


def check_frozen(ref: str, findings: Findings) -> int:
    for rel, symbol in FROZEN_SYMBOLS:
        label = f"{rel}::{symbol}" if symbol else rel
        try:
            base_source = subprocess.run(
                ["git", "-C", str(ROOT), "show", f"{ref}:{rel}"], capture_output=True, check=True, timeout=20,
            ).stdout.decode("utf-8")
            current, line = _symbol_fingerprint((ROOT / rel).read_text(encoding="utf-8"), symbol, rel)
            base, _ = _symbol_fingerprint(base_source, symbol, f"{ref}:{rel}")
        except (OSError, subprocess.SubprocessError, UnicodeDecodeError, SyntaxError) as exc:
            findings.add(rel, 0, "frozen", f"cannot compare {label} with {ref}: {exc}")
            continue
        if current is None or base is None:
            findings.add(rel, line, "frozen", f"{label} not found in the working tree or in {ref}")
        elif current != base:
            findings.add(rel, line, "frozen", f"{label} AST differs from {ref}: needs approved change control")
    return len(FROZEN_SYMBOLS)


# =============================================================================================
# --hook: decide from the Kiro hook event whether a guarded tree was edited
# =============================================================================================
def _read_stdin(timeout_s: float = 1.0) -> str:
    """Read stdin without blocking forever if the caller keeps the pipe open."""
    if sys.stdin is None or sys.stdin.isatty():
        return ""
    box = {}

    def reader():
        try:
            box["data"] = sys.stdin.read()
        except (OSError, ValueError):
            box["data"] = ""

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    thread.join(timeout_s)
    return box.get("data", "")


def hook_edits_guarded_tree(raw_event: str):
    """True/False when the event names edited paths; None when unknown (run the checks)."""
    try:
        event = json.loads(raw_event) if raw_event.strip() else None
    except ValueError:
        return None
    if not isinstance(event, dict):
        return None
    found = []

    def collect(obj, key=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                collect(v, str(k))
        elif isinstance(obj, list):
            for v in obj:
                collect(v, key)
        elif isinstance(obj, str) and re.search(r"path|file", key, re.IGNORECASE):
            found.append(obj)

    collect(event.get("tool_input", event))
    if not found:
        return None
    base = Path(event.get("cwd") or os.getcwd())
    for name in found:
        path = Path(name) if Path(name).is_absolute() else base / name
        try:
            parts = path.resolve().relative_to(ROOT).parts
        except (ValueError, OSError):
            continue
        if parts and parts[0] in GUARDED_TREES:
            return True
    return False


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Fast static GxP guards (read-only).")
    parser.add_argument("--hook", action="store_true",
                        help="read the Kiro hook event on stdin; skip when no guarded tree was edited")
    parser.add_argument("--frozen-base", metavar="REF",
                        help="also compare the frozen symbols with git REF (e.g. v1.4.0)")
    args = parser.parse_args(argv)
    start = time.perf_counter()
    if args.hook and hook_edits_guarded_tree(_read_stdin()) is False:
        print("verify_gxp_guards: skipped (the edit is outside src/, docs/, data/ and .kiro/)")
        return 0

    findings = Findings()
    trees = parse_sources(findings)
    counts = {
        "src-modules": len(trees),
        "constants": check_constants(trees, findings),
        "rhs-checks": check_mode_leak(trees, findings),
    }
    counts["utf8-files"], file_source = check_utf8(findings)
    counts["json-files"] = check_json(findings)
    counts["front-matter"] = check_front_matter(findings)
    if args.frozen_base:
        counts["frozen-symbols"] = check_frozen(args.frozen_base, findings)
    elapsed = time.perf_counter() - start

    summary = ", ".join(f"{k} {v}" for k, v in counts.items())
    if findings:
        for path, line, check, message in findings.items:
            print(f"{path}:{line}: [{check}] {message}", file=sys.stderr)
        print(f"verify_gxp_guards: FAIL - {len(findings)} finding(s); {summary} "
              f"({file_source}, {elapsed:.2f} s)", file=sys.stderr)
        return 1
    print(f"verify_gxp_guards: PASS - {summary} ({file_source}, {elapsed:.2f} s)")
    if elapsed > TIME_BUDGET_S:
        print(f"verify_gxp_guards: warning - {elapsed:.2f} s exceeds the {TIME_BUDGET_S:.0f} s budget",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
