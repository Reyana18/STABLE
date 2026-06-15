"""
STABLE Suggestion Engine
Context-aware dose suggestion against the STABLE cardiovascular dataset.

Surfaces all documented dosing options for a drug-indication-patient
combination, consolidated per phase and annotated with safety tags drawn
from the same dataset rows. Suggests and flags; never blocks.
"""

import pandas as pd
import re
from dataclasses import dataclass, field
from typing import List, Optional
from collections import OrderedDict


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
    freq_min: Optional[float] = None
    freq_max: Optional[float] = None
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
            t += f"  |  {self.frequency}"
        if self.renal_adjusted:
            t += "  \u2605 renal-adjusted"
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
        for df in (self.dose, self.renal):
            for c in df.columns:
                if df[c].dtype == object or str(df[c].dtype) == "string":
                    df[c] = df[c].astype(str).str.strip()

    # ── helpers ──
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
        s = str(v).strip()
        return "" if s.lower() in ("nan", "none", "") else s

    @staticmethod
    def _fmtn(x):
        return f"{x:g}"

    def _fmt_freq(self, fmin, fmax, timing):
        parts = []
        if fmin is not None and fmax is not None:
            n = self._fmtn(fmin) if fmin == fmax else f"{self._fmtn(fmin)}\u2013{self._fmtn(fmax)}"
            parts.append(n + "\u00d7")
        if timing:
            parts.append(f"per {timing.lower()}")
        return " ".join(parts)

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

    def get_drugs(self):
        vals = self.dose["Generic"].dropna().astype(str).str.strip().unique()
        return sorted(v for v in vals if v and v.lower() not in ("nan", "none", ""))

    def get_routes(self):
        vals = self.dose["Route"].dropna().astype(str).str.strip().unique()
        return sorted(v for v in vals if v and v.lower() not in ("nan", "none", ""))

    def get_drug_indications(self, drug):
        d = self.dose
        mask = d["Generic"].astype(str).str.lower() == drug.lower()
        vals = d.loc[mask, "Indication"].dropna().astype(str).str.strip().unique()
        return sorted(v for v in vals if v and v.lower() not in ("nan", "none", ""))

    # ── retrieval ──
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

    # ── dose extraction ──
    def _extract_dose(self, row, weight_kg):
        f = self._fmtn
        single = self._num(row.get("Direct Dose mg(Single Strength)"))
        lo_m = self._num(row.get("Min Direct Dose mg(Multiple Strength)"))
        hi_m = self._num(row.get("Max  Direct Dose mg(Multiple Strength)"))
        if single is not None:
            return single, single, f"{f(single)} mg", False
        if lo_m is not None and hi_m is not None:
            return lo_m, hi_m, f"{f(lo_m)}\u2013{f(hi_m)} mg", False
        if lo_m is not None:
            return lo_m, lo_m, f"{f(lo_m)} mg", False
        if hi_m is not None:
            return hi_m, hi_m, f"{f(hi_m)} mg", False

        ws = self._num(row.get("Dose Per Weight mg(Single Strength)"))
        wlo = self._num(row.get("Dose Per Weight mg(Min Multiple Strength)"))
        whi = self._num(row.get("Dose Per Weight mg(Max Multiple Strength)"))
        if ws is not None or wlo is not None or whi is not None:
            per_lo = ws if ws is not None else (wlo if wlo is not None else whi)
            per_hi = whi if whi is not None else (ws if ws is not None else wlo)
            if weight_kg and weight_kg > 0:
                mg_lo = round(per_lo * weight_kg, 1)
                mg_hi = round(per_hi * weight_kg, 1)
                if per_lo == per_hi:
                    disp = f"{f(per_lo)} mg/kg \u2192 {f(mg_lo)} mg"
                else:
                    disp = f"{f(per_lo)}\u2013{f(per_hi)} mg/kg \u2192 {f(mg_lo)}\u2013{f(mg_hi)} mg"
                return mg_lo, mg_hi, disp, True
            disp = f"{f(per_lo)} mg/kg" if per_lo == per_hi else f"{f(per_lo)}\u2013{f(per_hi)} mg/kg"
            return None, None, disp + " (enter weight)", True

        iu = self._num(row.get("Direct Dose(IU)"))
        iu_w = self._num(row.get("Dose Per weight(IU)"))
        if iu is not None:
            return iu, iu, f"{f(iu)} IU", False
        if iu_w is not None:
            if weight_kg and weight_kg > 0:
                val = round(iu_w * weight_kg, 1)
                return val, val, f"{f(iu_w)} IU/kg \u2192 {f(val)} IU", True
            return None, None, f"{f(iu_w)} IU/kg", True

        us = self._num(row.get("Single Dose(Unit)"))
        ulo = self._num(row.get("Min Single Dose(Unit)"))
        uhi = self._num(row.get("Max Single Dose(Unit)"))
        if us is not None:
            return us, us, f"{f(us)} unit(s)", False
        if ulo is not None or uhi is not None:
            ulo = ulo if ulo is not None else uhi
            uhi = uhi if uhi is not None else ulo
            return ulo, uhi, f"{f(ulo)}\u2013{f(uhi)} unit(s)", False
        return None, None, "see instruction", False

    def _extract_frequency(self, row):
        sf = self._num(row.get("Single Frequency"))
        mnf = self._num(row.get("Min Frequency "))
        mxf = self._num(row.get("Max Frequency"))
        timing = self._safe(row.get("Timing"))
        if sf is not None:
            fmin = fmax = sf
        elif mnf is not None or mxf is not None:
            fmin = mnf if mnf is not None else mxf
            fmax = mxf if mxf is not None else mnf
        else:
            fmin = fmax = None
        return self._fmt_freq(fmin, fmax, timing), fmin, fmax, timing

    # ── consolidation ──
    def _consolidate(self, cards):
        groups = OrderedDict()
        for c in cards:
            key = (c.phase.lower().strip(), c.weight_based)
            groups.setdefault(key, []).append(c)

        def uniq(seq):
            out = []
            for x in seq:
                if x and x not in out:
                    out.append(x)
            return out

        merged = []
        for (_pl, wb), group in groups.items():
            if len(group) == 1:
                merged.append(group[0])
                continue
            mins = [c.dose_min_mg for c in group if c.dose_min_mg is not None]
            maxs = [c.dose_max_mg for c in group if c.dose_max_mg is not None]
            if mins and maxs:
                lo, hi = min(mins), max(maxs)
                base = f"{self._fmtn(lo)} mg" if lo == hi else f"{self._fmtn(lo)}\u2013{self._fmtn(hi)} mg"
                disp = base + (" (weight-based)" if wb else "")
            else:
                disp = group[0].dose_display
            fmins = [c.freq_min for c in group if c.freq_min is not None]
            fmaxs = [c.freq_max for c in group if c.freq_max is not None]
            timing = group[0].timing
            freq = self._fmt_freq(min(fmins), max(fmaxs), timing) if fmins and fmaxs else group[0].frequency
            merged.append(DoseCard(
                phase=group[0].phase, dose_display=disp,
                dose_min_mg=(min(mins) if mins else None),
                dose_max_mg=(max(maxs) if maxs else None),
                frequency=freq, timing=timing, route=group[0].route,
                duration="; ".join(uniq(c.duration for c in group)),
                administration="; ".join(uniq(c.administration for c in group)),
                instruction="; ".join(uniq(c.instruction for c in group)),
                weight_based=wb, tags=group[0].tags,
            ))
        return merged

    # ── safety annotations ──
    def _annotate_drug_level(self, rows, comorbidities, coprescribed, pregnant):
        tags = []
        text_ci = " ".join(self._safe(r.get("Contraindiction")) for _, r in rows.iterrows()).lower()
        for c in comorbidities:
            if c.lower() in text_ci:
                tags.append(SafetyTag(DANGER, "contraindication", f"'{c}' listed as a contraindication"))
        if pregnant:
            cats = {self._safe(r.get("Pregnancy Category")).upper() for _, r in rows.iterrows()}
            bad = cats & {"D", "Z", "X"}
            if bad:
                tags.append(SafetyTag(DANGER, "pregnancy", f"category {bad} \u2014 contraindicated in pregnancy"))
            elif cats - {"", "NAN"}:
                tags.append(SafetyTag(CAUTION, "pregnancy", f"category {cats - {'', 'NAN'}} \u2014 use with caution"))
        text_ddi = " ".join(self._safe(r.get("DDI")) for _, r in rows.iterrows()).lower()
        for d in coprescribed:
            if d.lower() in text_ddi:
                tags.append(SafetyTag(CAUTION, "drug interaction", f"interaction with co-prescribed '{d}'"))
        text_di = " ".join(self._safe(r.get("Disease Interactions")) for _, r in rows.iterrows()).lower()
        for c in comorbidities:
            if c.lower() in text_di:
                tags.append(SafetyTag(CAUTION, "comorbidity", f"'{c}' listed as a disease interaction"))
        return tags

    def _renal_cards(self, drug, crcl):
        if crcl is None or crcl >= 90:
            return []
        r = self.renal[self.renal["Generic"].str.lower() == drug.lower()]
        if len(r) == 0:
            return []
        f = self._fmtn
        cards = []
        for _, row in r.iterrows():
            mn = self._num(row.get("Min CrCl"))
            mx = self._num(row.get("Max CrCl"))
            ok = ((mn is not None and mx is not None and mn <= crcl <= mx)
                  or (mn is not None and mx is None and crcl >= mn)
                  or (mx is not None and mn is None and crcl <= mx))
            if not ok:
                continue
            single = self._num(row.get("Direct Dose mg (Single Strength)"))
            lo_m = self._num(row.get("Min Direct Dose (Multiple Strength)"))
            hi_m = self._num(row.get("Max Direct Dose (Multiple Strength)"))
            if single is not None:
                disp, d_lo, d_hi = f"{f(single)} mg (renal-adjusted)", single, single
            elif lo_m is not None or hi_m is not None:
                lo_m = lo_m if lo_m is not None else hi_m
                hi_m = hi_m if hi_m is not None else lo_m
                disp, d_lo, d_hi = f"{f(lo_m)}\u2013{f(hi_m)} mg (renal-adjusted)", lo_m, hi_m
            else:
                disp, d_lo, d_hi = "see instruction (renal-adjusted)", None, None
            bracket = f"CrCl {f(mn) if mn is not None else '?'}\u2013{f(mx) if mx is not None else '?'} mL/min"
            cards.append(DoseCard(
                phase=f"Renal ({bracket})", dose_display=disp,
                dose_min_mg=d_lo, dose_max_mg=d_hi,
                administration=self._safe(row.get("Administration")),
                instruction=self._safe(row.get("Instruction")),
                duration=self._safe(row.get("Duration")),
                renal_adjusted=True, tags=[SafetyTag(NOTE, "renal", bracket)],
            ))
        return cards

    # ── main ──
    def suggest(self, drug, indication, age_years, weight_kg=None, route=None,
                crcl=None, comorbidities=None, coprescribed=None, pregnant=False):
        comorbidities = comorbidities or []
        coprescribed = coprescribed or []
        result = SuggestionResult(drug=drug, indication=indication, patient_summary="")
        parts = [f"age {self._fmtn(age_years)}y"]
        if weight_kg:
            parts.append(f"{self._fmtn(weight_kg)} kg")
        if crcl is not None:
            parts.append(f"CrCl {self._fmtn(crcl)}")
        if pregnant:
            parts.append("pregnant")
        result.patient_summary = ", ".join(parts)
        result.available_indications = self.get_drug_indications(drug)

        rows = self._lookup(drug, indication, age_years, route)
        if len(rows) == 0:
            if result.available_indications:
                result.message = (f"No documented dosing for {drug} in '{indication}' at this "
                                  f"age/route. This drug covers: "
                                  f"{', '.join(result.available_indications[:8])}.")
            else:
                result.message = f"No STABLE data found for '{drug}'."
            result.cards.extend(self._renal_cards(drug, crcl))
            return result

        result.drug_level_tags = self._annotate_drug_level(rows, comorbidities, coprescribed, pregnant)
        for _, row in rows.iterrows():
            phase = self._safe(row.get("Type of Doses")) or "Unspecified"
            d_lo, d_hi, disp, wb = self._extract_dose(row, weight_kg)
            fdisp, fmin, fmax, timing = self._extract_frequency(row)
            result.cards.append(DoseCard(
                phase=phase, dose_display=disp, dose_min_mg=d_lo, dose_max_mg=d_hi,
                frequency=fdisp, freq_min=fmin, freq_max=fmax, timing=timing,
                route=self._safe(row.get("Route")), duration=self._safe(row.get("Duration")),
                administration=self._safe(row.get("Administration")),
                instruction=self._safe(row.get("Instruction")), weight_based=wb,
            ))
        result.cards = self._consolidate(result.cards)
        result.cards.sort(key=lambda c: self._phase_sort_key(c.phase))
        result.cards.extend(self._renal_cards(drug, crcl))
        if not result.cards:
            result.message = "No dose options resolved for this combination."
        return result


if __name__ == "__main__":
    import warnings; warnings.filterwarnings("ignore")
    eng = STABLESuggestionEngine("STABLE_age_ranged.xlsx")
    print("=== Metoprolol / Hypertension / age 55 / CrCl 45 ===")
    r = eng.suggest("Metoprolol", "Hypertension", 55, weight_kg=80, route="Oral-PO",
                     crcl=45, comorbidities=["diabetes"], coprescribed=["verapamil"])
    print("Patient:", r.patient_summary)
    for t in r.drug_level_tags:
        print(" ", t)
    for c in r.cards:
        print(c)
        if c.instruction:
            print("      instruction:", c.instruction[:80])
