"""
STABLE Suggestion Engine
Context-aware dose suggestion against the STABLE cardiovascular dataset.
"""

import pandas as pd
import re
from dataclasses import dataclass, field
from typing import List, Optional


DANGER = "DANGER"
CAUTION = "CAUTION"
NOTE = "NOTE"


@dataclass
class SafetyTag:
    level: str
    source: str
    message: str

    def __repr__(self):
        return f"[{self.level}] {self.source}: {self.message}"


@dataclass
class DoseCard:
    phase: str
    dose_display: str
    dose_min_mg: Optional[float] = None
    dose_max_mg: Optional[float] = None
    frequency: str = ""
    timing: str = ""
    route: str = ""
    duration: str = ""
    administration: str = ""
    instruction: str = ""
    weight_based: bool = False
    tags: List[SafetyTag] = field(default_factory=list)
    renal_adjusted: bool = False

    def __repr__(self):
        t = f"  [{self.phase}] {self.dose_display}"
        if self.frequency:
            t += f"  |  freq: {self.frequency}"
        if self.tags:
            t += "  |  " + "; ".join(str(tg) for tg in self.tags)
        if self.renal_adjusted:
            t += "  ★ renal-adjusted"
        return t


@dataclass
class SuggestionResult:
    drug: str
    indication: str
    patient_summary: str
    cards: List[DoseCard] = field(default_factory=list)
    drug_level_tags: List[SafetyTag] = field(default_factory=list)
    available_indications: List[str] = field(default_factory=list)
    message: str = ""


class STABLESuggestionEngine:
    PHASE_ORDER = [
        "loading", "initial", "titrate", "regular", "maintenance",
        "target", "maximum", "repeat", "diagnostic", "test",
        "preoperative", "pregnancy-associated"
    ]

    def __init__(self, path):
        xl = pd.ExcelFile(path)
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

        # drop duplicate-named columns (fixes duplicate "Route" etc.)
        self.dose = self.dose.loc[:, ~self.dose.columns.duplicated()]
        self.renal = self.renal.loc[:, ~self.renal.columns.duplicated()]

        for df in (self.dose, self.renal):
            for c in df.select_dtypes("object").columns:
                df[c] = df[c].astype(str).str.strip()

    # ── helpers ──────────────────────────────────────────────────────────
    @staticmethod
    def _num(v):
        try:
            f = float(v)
            if f != f:
                return None
            return f
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _safe(v):
        if isinstance(v, pd.Series):
            v = v.iloc[0] if len(v) else None
        s = str(v).strip()
        return "" if s.lower() in ("nan", "none", "") else s

    @staticmethod
    def _age_match(row, age):
        lo = STABLESuggestionEngine._num(row.get("Age_Min_Years"))
        hi = STABLESuggestionEngine._num(row.get("Age_Max_Years"))
        if lo is None or hi is None:
            return True
        return lo <= age <= hi

    def _phase_sort_key(self, phase):
        p = phase.lower().strip()
        for i, known in enumerate(self.PHASE_ORDER):
            if known in p:
                return i
        return len(self.PHASE_ORDER)

    def get_drug_indications(self, drug):
        d = self.dose
        mask = d["Generic"].astype(str).str.lower() == drug.lower()
        vals = d.loc[mask, "Indication"].astype(str).str.strip().unique()
        return sorted(v for v in vals if v and v.lower() != "nan")

    def get_drugs(self):
        return sorted(self.dose["Generic"].astype(str).str.strip().unique())

   def get_routes(self):
    col = self.dose["Route"]
    if isinstance(col, pd.DataFrame):
        col = col.iloc[:, 0]
    col = col.astype(str).str.strip()
    return sorted(r for r in col.unique() if r and r.lower() != "nan")

    # ── row retrieval ────────────────────────────────────────────────────
    def _lookup(self, drug, indication, age, route):
        d = self.dose
        drug_mask = d["Generic"].astype(str).str.lower() == drug.lower()
        ind_l = indication.lower() if indication else ""
        if ind_l:
            ind_series = d["Indication"].astype(str).str.lower()
            first = re.escape(ind_l.split()[0]) if ind_l.split() else re.escape(ind_l)
            ind_mask = ind_series.str.contains(first, na=False, regex=True) | ind_series.isin([ind_l])
            m = drug_mask & ind_mask
        else:
            m = drug_mask
        cand = d[m]
        if route:
            r = cand[cand["Route"].astype(str).str.lower().str.contains(route.lower()[:2], na=False)]
            if len(r) > 0:
                cand = r
        cand = cand[cand.apply(lambda x: self._age_match(x, age), axis=1)]
        return cand

    # ── dose extraction ──────────────────────────────────────────────────
    def _extract_dose(self, row, weight_kg):
        single = self._num(row.get("Direct Dose mg(Single Strength)"))
        lo_m = self._num(row.get("Min Direct Dose mg(Multiple Strength)"))
        hi_m = self._num(row.get("Max  Direct Dose mg(Multiple Strength)"))

        if single is not None:
            return single, single, f"{single} mg", False
        if lo_m is not None and hi_m is not None:
            return lo_m, hi_m, f"{lo_m}–{hi_m} mg", False
        if lo_m is not None:
            return lo_m, lo_m, f"{lo_m} mg", False
        if hi_m is not None:
            return hi_m, hi_m, f"{hi_m} mg", False

        ws = self._num(row.get("Dose Per Weight mg(Single Strength)"))
        wlo = self._num(row.get("Dose Per Weight mg(Min Multiple Strength)"))
        whi = self._num(row.get("Dose Per Weight mg(Max Multiple Strength)"))
        if ws is not None or wlo is not None or whi is not None:
            per_lo = ws or wlo or whi
            per_hi = whi or ws or wlo
            if weight_kg and weight_kg > 0:
                mg_lo = round(per_lo * weight_kg, 1)
                mg_hi = round(per_hi * weight_kg, 1)
                disp = f"{per_lo}–{per_hi} mg/kg → {mg_lo}–{mg_hi} mg for {weight_kg} kg"
                if per_lo == per_hi:
                    disp = f"{per_lo} mg/kg → {mg_lo} mg for {weight_kg} kg"
                return mg_lo, mg_hi, disp, True
            else:
                disp = f"{per_lo}–{per_hi} mg/kg (enter weight to compute mg)"
                if per_lo == per_hi:
                    disp = f"{per_lo} mg/kg"
                return None, None, disp, True

        iu = self._num(row.get("Direct Dose(IU)"))
        iu_w = self._num(row.get("Dose Per weight(IU)"))
        if iu is not None:
            return iu, iu, f"{iu} IU", False
        if iu_w is not None:
            if weight_kg and weight_kg > 0:
                val = round(iu_w * weight_kg, 1)
                return val, val, f"{iu_w} IU/kg → {val} IU for {weight_kg} kg", True
            return None, None, f"{iu_w} IU/kg", True

        us = self._num(row.get("Single Dose(Unit)"))
        ulo = self._num(row.get("Min Single Dose(Unit)"))
        uhi = self._num(row.get("Max Single Dose(Unit)"))
        if us is not None:
            return us, us, f"{us} unit(s)", False
        if ulo is not None or uhi is not None:
            ulo = ulo or uhi
            uhi = uhi or ulo
            return ulo, uhi, f"{ulo}–{uhi} unit(s)", False

        return None, None, "see Instruction field", False

    def _extract_frequency(self, row):
        sf = self._safe(row.get("Single Frequency"))
        mnf = self._safe(row.get("Min Frequency "))
        mxf = self._safe(row.get("Max Frequency"))
        timing = self._safe(row.get("Timing"))
        parts = []
        if sf:
            parts.append(sf)
        elif mnf or mxf:
            parts.append(f"{mnf or '?'}–{mxf or '?'}")
        if timing:
            parts.append(f"per {timing.lower()}")
        return " ".join(parts) if parts else ""

    # ── safety annotations ───────────────────────────────────────────────
    def _annotate_drug_level(self, rows, comorbidities, coprescribed, pregnant):
        tags = []
        text_ci = " ".join(self._safe(r.get("Contraindiction")) for _, r in rows.iterrows()).lower()
        for c in comorbidities:
            if c.lower() in text_ci:
                tags.append(SafetyTag(DANGER, "contraindication",
                                      f"'{c}' listed as contraindication for this drug"))
        if pregnant:
            cats = {self._safe(r.get("Pregnancy Category")).upper() for _, r in rows.iterrows()}
            bad = cats & {"D", "Z", "X"}
            if bad:
                tags.append(SafetyTag(DANGER, "pregnancy",
                                      f"pregnancy category {bad} — contraindicated in pregnancy"))
            elif cats - {"", "NAN"}:
                tags.append(SafetyTag(CAUTION, "pregnancy",
                                      f"pregnancy category {cats - {'','NAN'}} — use with caution"))
        text_ddi = " ".join(self._safe(r.get("DDI")) for _, r in rows.iterrows()).lower()
        for d in coprescribed:
            if d.lower() in text_ddi:
                tags.append(SafetyTag(CAUTION, "drug interaction",
                                      f"interaction flagged with co-prescribed '{d}'"))
        text_di = " ".join(self._safe(r.get("Disease Interactions")) for _, r in rows.iterrows()).lower()
        for c in comorbidities:
            if c.lower() in text_di:
                tags.append(SafetyTag(CAUTION, "comorbidity",
                                      f"'{c}' listed as disease interaction"))
        return tags

    def _renal_cards(self, drug, crcl, indication):
        if crcl is None or crcl >= 90:
            return []
        r = self.renal[self.renal["Generic"].str.lower() == drug.lower()]
        if len(r) == 0:
            return []
        matched = []
        for _, row in r.iterrows():
            mn = self._num(row.get("Min CrCl"))
            mx = self._num(row.get("Max CrCl"))
            if mn is not None and mx is not None:
                if mn <= crcl <= mx:
                    matched.append(row)
            elif mn is not None and crcl >= mn:
                matched.append(row)
            elif mx is not None and crcl <= mx:
                matched.append(row)
        cards = []
        for row in matched:
            single = self._num(row.get("Direct Dose mg (Single Strength)"))
            lo_m = self._num(row.get("Min Direct Dose (Multiple Strength)"))
            hi_m = self._num(row.get("Max Direct Dose (Multiple Strength)"))
            if single is not None:
                disp = f"{single} mg (renal-adjusted)"
                d_lo, d_hi = single, single
            elif lo_m is not None or hi_m is not None:
                lo_m = lo_m or hi_m
                hi_m = hi_m or lo_m
                disp = f"{lo_m}–{hi_m} mg (renal-adjusted)"
                d_lo, d_hi = lo_m, hi_m
            else:
                disp = "see instruction (renal-adjusted)"
                d_lo = d_hi = None

            sf = self._safe(row.get("Single Frequency"))
            mnf = self._safe(row.get("Min Frequency (Multiple)"))
            mxf = self._safe(row.get("Max Frequency (Multiple)"))
            fu = self._safe(row.get("Frequency Unit"))
            freq_parts = []
            if sf:
                freq_parts.append(sf)
            elif mnf or mxf:
                freq_parts.append(f"{mnf or '?'}–{mxf or '?'}")
            if fu:
                freq_parts.append(f"per {fu.lower()}")
            freq_str = " ".join(freq_parts)

            mn_v = self._num(row.get("Min CrCl"))
            mx_v = self._num(row.get("Max CrCl"))
            bracket = f"CrCl {mn_v or '?'}–{mx_v or '?'} mL/min"

            card = DoseCard(
                phase=f"Renal ({bracket})",
                dose_display=disp,
                dose_min_mg=d_lo, dose_max_mg=d_hi,
                frequency=freq_str,
                administration=self._safe(row.get("Administration")),
                instruction=self._safe(row.get("Instruction")),
                duration=self._safe(row.get("Duration")),
                renal_adjusted=True,
                tags=[SafetyTag(NOTE, "renal", bracket)]
            )
            cards.append(card)
        return cards
