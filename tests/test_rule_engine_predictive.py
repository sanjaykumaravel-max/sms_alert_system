from __future__ import annotations

from datetime import datetime, timedelta

from src.predictive_layer import predict_machine_risk
from src.rule_engine import evaluate_rules


def test_predictive_risk_goes_high_for_hour_overdue_machine() -> None:
    machine = {
        "id": "EX-99",
        "name": "Excavator",
        "hours": "1260",
        "next_due_hours": "1200",
        "hour_overdue_after_hours": "5",
        "status": "normal",
    }
    risk = predict_machine_risk(machine)
    assert int(risk.get("risk_score", 0)) >= 65
    assert str(risk.get("risk_level")) in {"high", "critical"}


def test_rule_engine_matches_nested_conditions() -> None:
    rules = [
        {
            "id": "r1",
            "name": "Overdue and high risk",
            "enabled": True,
            "severity": "critical",
            "condition": {
                "all": [
                    {"field": "status", "op": "eq", "value": "overdue"},
                    {
                        "any": [
                            {"field": "risk_score", "op": "gte", "value": 70},
                            {"field": "days_to_due", "op": "lt", "value": 0},
                        ]
                    },
                ]
            },
        }
    ]
    context = {
        "machine_id": "JC-01",
        "status": "overdue",
        "risk_score": 72,
        "days_to_due": -1,
    }
    matches = evaluate_rules(context, rules=rules)
    assert len(matches) == 1
    assert matches[0]["id"] == "r1"
