"""
STABLE Rule Engine
Deterministic prescription verification against the STABLE dataset.

Usage:
    engine = STABLERuleEngine("STABLE.xlsx")
    result = engine.verify(
        drug="Metoprolol", indication="Hypertension", age_years=70,
        dose_mg=200, route="Oral-PO", freq_per_day=1,
        crcl=None, comorbidities=[], coprescribed=[], pregnant=False
    )
    for f in result: print(f)
"""

import pandas as pd
import re


# severity tiers
BLOCK = "BLOCK"
WARN = "WARN"
INFO = "INFO"


class Flag:
    def __init__(self, rule, severity, message):
        self.rule = rule
        self.severity = severity
        self.message = message

    def __repr__(self):
        return f"[{self.severity}] {self.rule}: {self.message}"


class STABLERuleEngine:
    def __init__(self, path):
        xl = pd.ExcelFile(path)
        # auto-detect sheets: dosing = has 'Indication', renal = has 'CrCl'
        dose_sheet = renal_sheet = None
        for s in xl.sheet_names:
            cols = pd.read_excel(path, sheet_name=s, nrows=0).columns
            if any("CrCl" in str(c) for c in cols):
                renal_sheet = s
            elif any("Indication" in str(c) for c in cols):
                dose_sheet = s
        dose_sheet = dose_sheet or xl.sheet_names[0]
        renal_sheet = renal_sheet or (xl.sheet_names[1] if len(xl.sheet_names) > 1 else xl.sheet_names[0])
        self.dose = pd.read_excel(path, sheet_name=dose_sheet)
        self.renal = pd.read_excel(path, sheet_name=renal_sheet)
        for df in (self.dose, self.renal):
            for c in df.select_dtypes("object").columns:
                df[c] = df[c].astype(str).str.strip()

    # ---------- helpers ----------
    @staticmethod
    def _num(v):
        try:
            return float(v)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _age_match(row, age):
        lo = STABLERuleEngine._num(row.get("Age_Min_Years"))
        hi = STABLERuleEngine._num(row.get("Age_Max_Years"))
        if lo is None or hi is None:
            return True  # no age band recorded -> do not exclude
        return lo <= age < hi

    def _lookup(self, drug, indication, age, route):
        """Return candidate rows matching the composite key (loose on dose phase)."""
        d = self.dose
        ind_series = d["Indication"].astype(str).str.lower()
        ind_l = indication.lower()
        first = re.escape(ind_l.split()[0]) if ind_l.split() else re.escape(ind_l)
        # match if dataset indication contains the query's first word, or query contains the row text
        ind_mask = ind_series.str.contains(first, na=False, regex=True)
        ind_mask = ind_mask | ind_series.isin([ind_l])
        m = (d["Generic"].astype(str).str.lower() == drug.lower()) & ind_mask
        cand = d[m]
        if route:
            r = cand[cand["Route"].str.lower().str.contains(route.lower()[:2], na=False)]
            if len(r) > 0:
                cand = r
        cand = cand[cand.apply(lambda x: self._age_match(x, age), axis=1)]
        return cand

    # ---------- rules ----------
    def _rule_dose(self, rows, dose_mg, weight_kg, flags):
        if dose_mg is None:
            return
        lo, hi = float("inf"), 0.0
        for _, r in rows.iterrows():
            for c in ["Direct Dose mg(Single Strength)",
                      "Min Direct Dose mg(Multiple Strength)",
                      "Max  Direct Dose mg(Multiple Strength)"]:
                v = self._num(r.get(c))
                if v is not None:
                    lo, hi = min(lo, v), max(hi, v)
            # weight-based
            if weight_kg:
                for c in ["Dose Per Weight mg(Single Strength)",
                          "Dose Per Weight mg(Min Multiple Strength)",
                          "Dose Per Weight mg(Max Multiple Strength)"]:
                    v = self._num(r.get(c))
                    if v is not None:
                        lo, hi = min(lo, v * weight_kg), max(hi, v * weight_kg)
        if hi == 0:
            flags.append(Flag("dose", INFO, "no numeric dose reference for this scenario"))
            return
        if dose_mg > hi:
            sev = BLOCK if dose_mg > hi * 1.5 else WARN
            flags.append(Flag("dose", sev,
                              f"dose {dose_mg} mg exceeds documented max {hi} mg"))
        elif dose_mg < lo:
            flags.append(Flag("dose", WARN,
                              f"dose {dose_mg} mg below documented min {lo} mg"))

    def _rule_frequency(self, rows, freq, flags):
        if freq is None:
            return
        hi = 0
        for _, r in rows.iterrows():
            for c in ["Single Frequency", "Max Frequency"]:
                v = self._num(r.get(c))
                if v is not None:
                    hi = max(hi, v)
        if hi and freq > hi:
            flags.append(Flag("frequency", WARN,
                              f"frequency {freq}/period exceeds documented max {hi}"))

    def _rule_route(self, rows, route, flags):
        if not route:
            return
        allowed = set()
        for _, r in rows.iterrows():
            allowed.add(str(r.get("Route", "")).lower())
        if allowed and not any(route.lower()[:2] in a for a in allowed):
            flags.append(Flag("route", WARN,
                              f"route '{route}' not documented; allowed: {sorted(allowed)}"))

    def _rule_contraindication(self, rows, comorbidities, flags):
        text = " ".join(str(r.get("Contraindiction", "")) for _, r in rows.iterrows()).lower()
        for c in comorbidities:
            if c.lower() in text:
                flags.append(Flag("contraindication", BLOCK,
                                  f"'{c}' listed as contraindication"))

    def _rule_disease_interaction(self, rows, comorbidities, flags):
        text = " ".join(str(r.get("Disease Interactions", "")) for _, r in rows.iterrows()).lower()
        for c in comorbidities:
            if c.lower() in text:
                flags.append(Flag("disease_interaction", WARN,
                                  f"comorbidity '{c}' may make drug unsafe"))

    def _rule_ddi(self, rows, coprescribed, flags):
        text = " ".join(str(r.get("DDI", "")) for _, r in rows.iterrows()).lower()
        for d in coprescribed:
            if d.lower() in text:
                flags.append(Flag("ddi", WARN,
                                  f"co-prescribed '{d}' flagged as interaction"))

    def _rule_pregnancy(self, rows, pregnant, flags):
        if not pregnant:
            return
        cats = {str(r.get("Pregnancy Category", "")).strip().upper()
                for _, r in rows.iterrows()}
        if cats & {"D", "Z", "X"}:
            flags.append(Flag("pregnancy", BLOCK,
                              f"pregnancy category {cats & {'D','Z','X'}} - contraindicated"))

    def _rule_renal(self, drug, crcl, flags):
        if crcl is None:
            return
        r = self.renal[self.renal["Generic"].str.lower() == drug.lower()]
        if len(r) == 0:
            return  # no renal data for this drug
        # if drug has renal entries and CrCl is reduced, require attention
        if crcl < 60:
            flags.append(Flag("renal", WARN,
                              f"CrCl {crcl} mL/min - renal adjustment exists for {drug}; "
                              f"verify reduced dose applied"))

    # ---------- main ----------
    def verify(self, drug, indication, age_years, dose_mg=None, route=None,
               freq_per_day=None, weight_kg=None, crcl=None,
               comorbidities=None, coprescribed=None, pregnant=False):
        comorbidities = comorbidities or []
        coprescribed = coprescribed or []
        flags = []

        rows = self._lookup(drug, indication, age_years, route)
        if len(rows) == 0:
            flags.append(Flag("lookup", INFO,
                              f"no STABLE reference row for {drug} / {indication} / age {age_years}"))
            # still run renal + pregnancy which don't need the row
            self._rule_renal(drug, crcl, flags)
            return self._sort(flags)

        self._rule_dose(rows, dose_mg, weight_kg, flags)
        self._rule_frequency(rows, freq_per_day, flags)
        self._rule_route(rows, route, flags)
        self._rule_contraindication(rows, comorbidities, flags)
        self._rule_disease_interaction(rows, comorbidities, flags)
        self._rule_ddi(rows, coprescribed, flags)
        self._rule_pregnancy(rows, pregnant, flags)
        self._rule_renal(drug, crcl, flags)

        if not flags:
            flags.append(Flag("ok", INFO, "prescription within documented parameters"))
        return self._sort(flags)

    @staticmethod
    def _sort(flags):
        order = {BLOCK: 0, WARN: 1, INFO: 2}
        return sorted(flags, key=lambda f: order[f.severity])


if __name__ == "__main__":
    eng = STABLERuleEngine("STABLE_age_ranged.xlsx")
    print("=== Metoprolol 200mg HTN, age 70 (likely over max) ===")
    for f in eng.verify("Metoprolol", "Hypertension", 70, dose_mg=200,
                         route="Oral-PO", freq_per_day=1):
        print(" ", f)
