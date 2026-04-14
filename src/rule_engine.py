from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

try:
    from .app_paths import data_path
except Exception:
    from app_paths import data_path


RULES_FILE = data_path("rule_engine_rules.json")

# Keep empty by design: the rule engine must run only on user-defined rules.
DEFAULT_RULES: List[Dict[str, Any]] = []


def _as_number(value: Any) -> Optional[float]:
    try:
        return float(str(value).strip())
    except Exception:
        return None


def _coerce_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _normalize_rule(rule: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(rule or {})
    row["id"] = str(row.get("id") or "").strip()
    row["name"] = str(row.get("name") or row["id"] or "Rule").strip()
    row["enabled"] = _coerce_bool(row.get("enabled"), True)
    row["severity"] = str(row.get("severity") or "warning").strip().lower() or "warning"
    row["trigger"] = str(row.get("trigger") or "rule_engine").strip().lower() or "rule_engine"
    row["message_template"] = str(row.get("message_template") or "").strip()
    row["dedup_window_minutes"] = int(_as_number(row.get("dedup_window_minutes")) or 360)
    condition = row.get("condition")
    row["condition"] = condition if isinstance(condition, dict) else {}
    return row


def load_rules() -> List[Dict[str, Any]]:
    try:
        if RULES_FILE.exists():
            payload = json.loads(RULES_FILE.read_text(encoding="utf-8")) or []
            if isinstance(payload, list):
                rows = [_normalize_rule(item) for item in payload if isinstance(item, dict)]
                rows = [row for row in rows if row.get("id")]
                return rows
    except Exception:
        pass
    return []


def save_rules(rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = [_normalize_rule(item) for item in (rules or []) if isinstance(item, dict)]
    rows = [row for row in rows if row.get("id")]
    RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
    RULES_FILE.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return rows


def _contains(actual: Any, expected: Any) -> bool:
    if isinstance(actual, (list, tuple, set)):
        needle = str(expected or "").strip().lower()
        for item in actual:
            if str(item or "").strip().lower() == needle:
                return True
        return False
    return str(expected or "").strip().lower() in str(actual or "").strip().lower()


def _compare(actual: Any, op: str, expected: Any) -> bool:
    op = str(op or "eq").strip().lower()
    a_num = _as_number(actual)
    e_num = _as_number(expected)

    if op == "exists":
        return actual not in (None, "", [], {}, ())
    if op == "truthy":
        return bool(actual)
    if op == "contains":
        return _contains(actual, expected)
    if op == "in":
        if isinstance(expected, (list, tuple, set)):
            values = {str(item).strip().lower() for item in expected}
        else:
            values = {part.strip().lower() for part in str(expected or "").split(",") if part.strip()}
        return str(actual or "").strip().lower() in values
    if op == "between":
        if isinstance(expected, (list, tuple)) and len(expected) >= 2 and a_num is not None:
            low = _as_number(expected[0])
            high = _as_number(expected[1])
            if low is None or high is None:
                return False
            return low <= a_num <= high
        return False

    if a_num is not None and e_num is not None:
        if op == "eq":
            return a_num == e_num
        if op in {"neq", "ne"}:
            return a_num != e_num
        if op == "gt":
            return a_num > e_num
        if op == "gte":
            return a_num >= e_num
        if op == "lt":
            return a_num < e_num
        if op == "lte":
            return a_num <= e_num
        return False

    a_txt = str(actual or "").strip().lower()
    e_txt = str(expected or "").strip().lower()
    if op == "eq":
        return a_txt == e_txt
    if op in {"neq", "ne"}:
        return a_txt != e_txt
    if op == "gt":
        return a_txt > e_txt
    if op == "gte":
        return a_txt >= e_txt
    if op == "lt":
        return a_txt < e_txt
    if op == "lte":
        return a_txt <= e_txt
    return False


def evaluate_condition(condition: Dict[str, Any], context: Dict[str, Any]) -> bool:
    node = dict(condition or {})
    if not node:
        return False

    all_nodes = node.get("all")
    if isinstance(all_nodes, list):
        children = [item for item in all_nodes if isinstance(item, dict)]
        return bool(children) and all(evaluate_condition(child, context) for child in children)

    any_nodes = node.get("any")
    if isinstance(any_nodes, list):
        children = [item for item in any_nodes if isinstance(item, dict)]
        return bool(children) and any(evaluate_condition(child, context) for child in children)

    field = str(node.get("field") or "").strip()
    if not field:
        return False
    op = str(node.get("op") or "eq").strip().lower()
    expected = node.get("value")
    actual = context.get(field)
    return _compare(actual, op, expected)


class _FormatMap(dict):
    def __missing__(self, key: str) -> str:
        return "-"


def render_rule_message(rule: Dict[str, Any], context: Dict[str, Any]) -> str:
    template = str(rule.get("message_template") or "").strip()
    if not template:
        machine_id = str(context.get("machine_id") or "Machine").strip()
        status = str(context.get("status") or "normal").strip().upper()
        return f"{machine_id} matched rule '{rule.get('name') or rule.get('id')}'. Status: {status}."
    try:
        return template.format_map(_FormatMap(context))
    except Exception:
        return template


def evaluate_rules(
    context: Dict[str, Any],
    *,
    rules: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    rows = rules if rules is not None else load_rules()
    matches: List[Dict[str, Any]] = []
    for raw in rows or []:
        rule = _normalize_rule(raw if isinstance(raw, dict) else {})
        if not rule.get("id") or not rule.get("enabled", True):
            continue
        if evaluate_condition(rule.get("condition") or {}, context):
            matches.append(rule)
    return matches
