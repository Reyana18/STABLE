"""
STABLE Verifier - web interface for the STABLE rule engine.

Run locally:
    pip install streamlit pandas openpyxl
    streamlit run stable_app.py

Deploy a shareable link:
    push this file + stable_rule_engine.py + the .xlsx to a GitHub repo,
    then connect the repo at share.streamlit.io (free).
"""

import streamlit as st
import pandas as pd
from stable_rule_engine import STABLERuleEngine, BLOCK, WARN, INFO

DATA_FILE = "STABLE_age_ranged.xlsx"

st.set_page_config(page_title="STABLE Verifier", page_icon="💊", layout="centered")


@st.cache_resource
def load_engine():
    return STABLERuleEngine(DATA_FILE)


engine = load_engine()
dose_df = engine.dose

# dropdown option lists pulled from the dataset
def clean_opts(col):
    vals = dose_df[col].astype(str).str.strip().unique()
    return sorted(str(v) for v in vals if str(v).strip() and str(v).strip().lower() != "nan")

drugs = clean_opts("Generic")
indications = clean_opts("Indication")
routes = clean_opts("Route")

# ---------------- header ----------------
st.title("STABLE Verifier")
st.caption("Prescription dose checking against the STABLE cardiovascular dataset. "
           "Research and decision-support tool, not a substitute for clinical judgement.")

# ---------------- input form ----------------
with st.form("rx"):
    c1, c2 = st.columns(2)
    with c1:
        drug = st.selectbox("Drug (generic)", drugs,
                            index=drugs.index("Metoprolol") if "Metoprolol" in drugs else 0)
        age = st.number_input("Patient age (years)", min_value=0.0, max_value=120.0,
                              value=55.0, step=1.0)
        dose = st.number_input("Prescribed dose (mg)", min_value=0.0, value=50.0, step=1.0)
        weight = st.number_input("Weight (kg) — for weight-based drugs", min_value=0.0,
                                 value=0.0, step=1.0, help="Leave 0 if not applicable")
    with c2:
        indication = st.selectbox("Indication", indications,
                                  index=indications.index("Hypertension") if "Hypertension" in indications else 0)
        route = st.selectbox("Route", routes,
                             index=routes.index("Oral-PO") if "Oral-PO" in routes else 0)
        freq = st.number_input("Frequency (times per period)", min_value=0.0, value=1.0, step=1.0)
        crcl = st.number_input("Creatinine clearance (mL/min) — 0 = not provided",
                               min_value=0.0, value=0.0, step=1.0)

    c3, c4 = st.columns(2)
    with c3:
        comorbidities = st.text_input("Comorbidities (comma-separated)",
                                      placeholder="e.g. asthma, renal stenosis")
    with c4:
        coprescribed = st.text_input("Co-prescribed drugs (comma-separated)",
                                     placeholder="e.g. verapamil")
    pregnant = st.checkbox("Patient is pregnant")

    submitted = st.form_submit_button("Verify prescription", use_container_width=True)

# ---------------- run + display ----------------
if submitted:
    flags = engine.verify(
        drug=drug, indication=indication, age_years=age,
        dose_mg=dose if dose > 0 else None,
        route=route,
        freq_per_day=freq if freq > 0 else None,
        weight_kg=weight if weight > 0 else None,
        crcl=crcl if crcl > 0 else None,
        comorbidities=[c.strip() for c in comorbidities.split(",") if c.strip()],
        coprescribed=[c.strip() for c in coprescribed.split(",") if c.strip()],
        pregnant=pregnant,
    )

    has_block = any(f.severity == BLOCK for f in flags)
    has_warn = any(f.severity == WARN for f in flags)

    # top-level verdict
    if has_block:
        st.error("### ⛔ BLOCK — do not dispense without review")
    elif has_warn:
        st.warning("### ⚠️ CHECK — review before dispensing")
    else:
        st.success("### ✅ Within documented parameters")

    # expandable detail
    with st.expander("See detailed flags", expanded=True):
        for f in flags:
            if f.severity == BLOCK:
                st.error(f"**{f.rule}** — {f.message}")
            elif f.severity == WARN:
                st.warning(f"**{f.rule}** — {f.message}")
            else:
                st.info(f"**{f.rule}** — {f.message}")

    st.caption("STABLE Verifier flags deviations from documented dosing references. "
               "Final prescribing decisions remain the responsibility of the clinician.")
