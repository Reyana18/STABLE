"""
STABLE Rule Engine
A small forward-chaining production-rule engine that runs the rule base in
stable_rules.json against a patient context.

The JSON holds the knowledge (the rules). This file is the inference engine:
it loads the rules, matches each rule's `when` conditions against the patient
facts, and fires the `then` action of every rule that matches.

Run it directly:
    python rule_engine.py

Use it in your app:
    from rule_engine import RuleEngine
    eng = RuleEngine("stable_rules.json")
    result = eng.run({"drug": "Metoprolol", "indication": "Hypertension",
                      "age": 55, "route": "Oral-PO", "crcl": 45,
                      "comorbidities": ["diabetes"], "coprescribed": ["verapamil"]})
"""

import json


def rclass(r):
    r = str(r).lower()
    if any(x in r for x in ["intraven", "iv", "infus", "bolus", "ivp"]): return "iv"
    if "subcut" in r or r.strip() == "sc": return "sc"
    if "subling" in r or "lingual" in r: return "sl"
    if "intramasc" in r or "intramus" in r or r.strip() == "im": return "im"
    if "patch" in r or "topical" in r or "ointment" in r: return "topical"
    if "oral" in r or "po" in r: return "oral"
    return "other"


class RuleEngine:
    def __init__(self, path="stable_rules.json"):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.rules = data["rules"]
        self.meta = data.get("meta", {})

    # ---- condition matching ----
    def _match_field(self, field, cond, ctx):
        v = ctx.get(field)
        # numeric range: {"min": x, "max": y}
        if isinstance(cond, dict) and ("min" in cond or "max" in cond):
            if v is None:
                return False
            try:
                v = float(v)
            except (ValueError, TypeError):
                return False
            if "min" in cond and v < cond["min"]:
                return False
            if "max" in cond and v > cond["max"]:
                return False
            return True
        # list membership: {"any_of": [...]}
        if isinstance(cond, dict) and "any_of" in cond:
            patient = [str(x).strip().lower() for x in (v or [])]
            if not patient:
                return False
            for tokn in cond["any_of"]:
                for p in patient:
                    if p and (p in tokn or tokn in p):
                        return True
            return False
        # boolean
        if isinstance(cond, bool):
            return bool(v) == cond
        # string
        if v is None:
            return False
        v, cs = str(v).strip().lower(), str(cond).strip().lower()
        if field == "indication":          # lenient: substring either way
            return cs in v or v in cs
        return v == cs                       # exact (drug, route_class, etc.)

    def _matches(self, when, ctx):
        return all(self._match_field(f, c, ctx) for f, c in when.items())

    # ---- forward-chaining pass ----
    def run(self, ctx):
        ctx = dict(ctx)
        if "route" in ctx and "route_class" not in ctx:
            ctx["route_class"] = rclass(ctx["route"])
        suggestions, flags, fired = [], [], []
        for rule in self.rules:
            if self._matches(rule.get("when", {}), ctx):
                fired.append(rule["id"])
                then = rule["then"]
                (suggestions if then.get("action") == "suggest" else flags).append(then)
        return {"suggestions": suggestions, "flags": flags, "fired": fired}


# ---- standalone test ----
if __name__ == "__main__":
    eng = RuleEngine("stable_rules.json")
    print(f"Loaded {len(eng.rules)} rules.\n")

    context = {
        "drug": "Metoprolol", "indication": "Hypertension",
        "age": 55, "route": "Oral-PO", "crcl": 45,
        "comorbidities": ["diabetes"], "coprescribed": ["verapamil"],
        "pregnant": False,
    }
    print("Patient context:", context, "\n")
    out = eng.run(context)

    if out["flags"]:
        print("FLAGS")
        for f in out["flags"]:
            print(f"  [{f['level']}] {f['source']}: {f['message']}")
        print()
    print("SUGGESTED DOSES")
    for s in out["suggestions"]:
        line = f"  [{s['phase']}] {s['dose_display']}"
        if s.get("frequency"):
            line += f"  |  {s['frequency']}"
        print(line)
    print(f"\nFired {len(out['fired'])} rules: {out['fired']}")
