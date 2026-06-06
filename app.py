"""
STABLE Verifier - web interface for the STABLE rule engine.

Cascading version: selecting a generic drug filters the indication, route,
comorbidity and co-prescribed options down to what STABLE documents for THAT
drug, instead of showing the full global lists.

Run locally:
    pip install streamlit pandas openpyxl
    streamlit run app.py
"""

import re
import streamlit as st
import pandas as pd
from stable_rule_engine import STABLERuleEngine, BLOCK, WARN, INFO

DATA_FILE = "STABLE_age_ranged.xlsx"

st.set_page_config(page_title="STABLE Verifier", page_icon="🫀", layout="centered")

# ---------------- styling ----------------
st.markdown(
    """
    <style>
      .block-container { padding-top: 2.2rem; max-width: 960px; }
      h1 { font-weight: 800; letter-spacing: -0.5px; color: #0E2A40; }
      .stable-sub { color: #5A6B7A; font-size: 0.95rem; line-height: 1.5;
                    margin-top: -0.4rem; margin-bottom: 0.4rem; }
      .stable-badges { margin: 0.6rem 0 1.2rem 0; }
      .stable-badge { display: inline-block; background: #EEF3F8; color: #0E5A8A;
                      border: 1px solid #D4E0EC; border-radius: 999px;
                      padding: 3px 12px; font-size: 0.78rem; font-weight: 600;
                      margin-right: 6px; margin-bottom: 6px; }
      .stable-affil { color: #7A8896; font-size: 0.8rem; margin-bottom: 0.2rem; }
      .sec-head { display:flex; align-items:center; gap:8px; font-weight:700;
                  font-size:0.9rem; color:#0E5A8A; text-transform:uppercase;
                  letter-spacing:0.6px; margin:1.1rem 0 0.4rem;
                  padding-bottom:6px; border-bottom:2px solid #D4E0EC; }
      .sec-head .ico { font-size:1.1rem; }
      .verdict { border-radius: 14px; padding: 1.1rem 1.3rem; margin: 0.6rem 0 1rem;
                 font-size: 1.15rem; font-weight: 700; }
      .v-block { background: #FDECEC; color: #8A1C1C; border: 1px solid #F3C9C9; }
      .v-warn  { background: #FFF6E5; color: #8A5A00; border: 1px solid #F3E0B0; }
      .v-ok    { background: #EAF7EE; color: #1C6B33; border: 1px solid #BFE6CB; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def load_engine():
    return STABLERuleEngine(DATA_FILE)


engine = load_engine()
dose_df = engine.dose


# ---------------- helpers ----------------
def first_col(df, *cands):
    for c in cands:
        if c in df.columns:
            return c
    return None


def clean_list(values):
    out = set()
    for v in values:
        s = str(v).strip()
        if s and s.lower() != "nan":
            out.add(s)
    return sorted(out)


def split_terms(series):
    """Parse free-text clinical columns into discrete option terms.
    Source columns are prose with newlines/brand names, so this is best-effort."""
    terms = set()
    for v in series.dropna():
        s = str(v).strip()
        if not s or s.lower() == "nan":
            continue
        for part in re.split(r"[\n\r;,/|]+", s):
            p = part.strip(" .:")
            if p and p.lower() != "nan" and 1 < len(p) < 40:
                terms.add(p)
    return sorted(terms)


GEN_COL = first_col(dose_df, "Generic")
IND_COL = first_col(dose_df, "Indication")
ROUTE_COL = first_col(dose_df, "Route")
CONTRA_COL = first_col(dose_df, "Contraindication", "Contraindiction")
DISEASE_COL = first_col(dose_df, "Disease Interactions", "Disease Interaction")
DDI_COL = first_col(dose_df, "DDI")

drugs = clean_list(dose_df[GEN_COL].unique())
n_drugs = len(drugs)
n_ind = dose_df[IND_COL].nunique()
n_rows = len(dose_df)


@st.cache_data
def options_for_drug(drug):
    rows = dose_df[dose_df[GEN_COL].astype(str).str.lower() == drug.lower()]
    inds = clean_list(rows[IND_COL].unique()) if IND_COL else []
    routes = clean_list(rows[ROUTE_COL].unique()) if ROUTE_COL else []
    comorbid = []
    if CONTRA_COL:
        comorbid += split_terms(rows[CONTRA_COL])
    if DISEASE_COL:
        comorbid += split_terms(rows[DISEASE_COL])
    comorbid = sorted(set(comorbid))
    ddi = split_terms(rows[DDI_COL]) if DDI_COL else []
    return inds, routes, comorbid, ddi


# ---------------- header ----------------
st.title("STABLE Verifier")
st.markdown(
    '<div class="stable-affil">AIMS Lab · IRIIC · United International University, Dhaka</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="stable-sub">Prescription dose checking against the STABLE cardiovascular '
    "dataset. Research and decision-support tool, not a substitute for clinical judgement.</div>",
    unsafe_allow_html=True,
)
st.markdown(
    f'<div class="stable-badges">'
    f'<span class="stable-badge">{n_drugs} generic drugs</span>'
    f'<span class="stable-badge">{n_ind} indications</span>'
    f'<span class="stable-badge">{n_rows} dosing rows</span>'
    f'<span class="stable-badge">8 rules</span>'
    f"</div>",
    unsafe_allow_html=True,
)

# ---------------- reactive inputs (NO form, so cascading works) ----------------
st.markdown('<div class="sec-head"><span class="ico">🫀</span>Drug &amp; Indication</div>',
            unsafe_allow_html=True)
c1, c2 = st.columns(2)
with c1:
    drug = st.selectbox("Drug (generic)", drugs,
                        index=drugs.index("Metoprolol") if "Metoprolol" in drugs else 0)

inds, routes, comorbid_opts, ddi_opts = options_for_drug(drug)

with c2:
    indication = st.selectbox("Indication (documented for this drug)", inds if inds else ["—"])

st.markdown('<div class="sec-head"><span class="ico">👤</span>Patient</div>', unsafe_allow_html=True)
c1, c2 = st.columns(2)
with c1:
    age = st.number_input("Age (years)", min_value=0.0, max_value=120.0, value=55.0, step=1.0)
    pregnant = st.checkbox("Patient is pregnant")
with c2:
    weight = st.number_input("Weight (kg) — for weight-based drugs", min_value=0.0,
                             value=0.0, step=1.0, help="Leave 0 if not applicable")

st.markdown('<div class="sec-head"><span class="ico">💊</span>Dose &amp; Route</div>',
            unsafe_allow_html=True)
c1, c2 = st.columns(2)
with c1:
    dose = st.number_input("Prescribed dose (mg)", min_value=0.0, value=50.0, step=1.0)
    freq = st.number_input("Frequency (times per period)", min_value=0.0, value=1.0, step=1.0)
with c2:
    route = st.selectbox("Route (documented for this drug)", routes if routes else ["—"])
    crcl = st.number_input("Creatinine clearance (mL/min) — 0 = not provided",
                           min_value=0.0, value=0.0, step=1.0)

st.markdown('<div class="sec-head"><span class="ico">🧪</span>Clinical Context</div>',
            unsafe_allow_html=True)
c1, c2 = st.columns(2)
with c1:
    comorbidities = st.multiselect(
        "Comorbidities (documented for this drug)",
        comorbid_opts,
        help="Parsed from STABLE contraindication / disease-interaction text for the "
             "selected drug. Source is free text, so options are best-effort; add others below.")
    extra_com = st.text_input("Other comorbidity (optional, comma-separated)")
with c2:
    coprescribed = st.multiselect(
        "Co-prescribed drugs (documented interactions for this drug)",
        ddi_opts,
        help="Parsed from STABLE DDI text for the selected drug.")
    extra_ddi = st.text_input("Other co-prescribed drug (optional, comma-separated)")

comorbidities = list(comorbidities) + [c.strip() for c in extra_com.split(",") if c.strip()]
coprescribed = list(coprescribed) + [c.strip() for c in extra_ddi.split(",") if c.strip()]

st.markdown("<br>", unsafe_allow_html=True)
submitted = st.button("Verify prescription", use_container_width=True, type="primary")


# ---------------- run + display ----------------
if submitted:
    if indication == "—" or route == "—":
        st.warning("This drug has no documented indication or route in STABLE; cannot verify.")
    else:
        flags = engine.verify(
            drug=drug, indication=indication, age_years=age,
            dose_mg=dose if dose > 0 else None,
            route=route,
            freq_per_day=freq if freq > 0 else None,
            weight_kg=weight if weight > 0 else None,
            crcl=crcl if crcl > 0 else None,
            comorbidities=comorbidities,
            coprescribed=coprescribed,
            pregnant=pregnant,
        )

        has_block = any(f.severity == BLOCK for f in flags)
        has_warn = any(f.severity == WARN for f in flags)

        if has_block:
            st.markdown('<div class="verdict v-block">⛔ BLOCK — do not dispense without review</div>',
                        unsafe_allow_html=True)
        elif has_warn:
            st.markdown('<div class="verdict v-warn">⚠️ CHECK — review before dispensing</div>',
                        unsafe_allow_html=True)
        else:
            st.markdown('<div class="verdict v-ok">✅ Within documented parameters</div>',
                        unsafe_allow_html=True)

        with st.expander("See detailed flags", expanded=True):
            for f in flags:
                if f.severity == BLOCK:
                    st.error(f"**{f.rule}** — {f.message}")
                elif f.severity == WARN:
                    st.warning(f"**{f.rule}** — {f.message}")
                else:
                    st.info(f"**{f.rule}** — {f.message}")

        try:
            matched = engine._lookup(drug, indication, age, route)
            with st.expander(f"Matched STABLE reference rows ({len(matched)})", expanded=False):
                if len(matched):
                    st.dataframe(matched, use_container_width=True, hide_index=True)
                else:
                    st.write("No reference row matched this composite key.")
        except Exception:
            pass

        st.caption("STABLE Verifier flags deviations from documented dosing references. "
                   "Final prescribing decisions remain the responsibility of the clinician.")
