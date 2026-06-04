"""
STABLE Verifier - web interface for the STABLE rule engine.

Run locally:
    pip install streamlit pandas openpyxl
    streamlit run app.py

Deploy:
    push app.py + stable_rule_engine.py + STABLE_age_ranged.xlsx
    + .streamlit/config.toml  to a GitHub repo, connect at share.streamlit.io
"""

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
      .stable-badges { margin: 0.6rem 0 1.4rem 0; }
      .stable-badge { display: inline-block; background: #EEF3F8; color: #0E5A8A;
                      border: 1px solid #D4E0EC; border-radius: 999px;
                      padding: 3px 12px; font-size: 0.78rem; font-weight: 600;
                      margin-right: 6px; margin-bottom: 6px; }
      .stable-affil { color: #7A8896; font-size: 0.8rem; margin-bottom: 0.2rem; }
      .stable-banner { display: flex; align-items: center; gap: 14px;
                       background: linear-gradient(90deg, #0E2A40 0%, #0E5A8A 100%);
                       border-radius: 14px; padding: 18px 22px; margin-bottom: 1.1rem; }
      .stable-mark { font-size: 1.9rem; line-height: 1; }
      .stable-word { color: #FFFFFF; font-weight: 800; font-size: 1.55rem;
                     letter-spacing: -0.5px; }
      .stable-word small { display: block; color: #Bcd6ea; color: #B8D2E8;
                           font-weight: 500; font-size: 0.72rem; letter-spacing: 0.3px;
                           margin-top: 2px; }
      .stable-accent { height: 4px; width: 60px; background: #1FB6A6;
                       border-radius: 4px; margin: 0.2rem 0 1rem; }
      .stable-logorow { display: flex; align-items: center; gap: 18px;
                        margin-bottom: 0.8rem; }
      .stable-logorow img { height: 38px; opacity: 0.9; }
      div[data-testid="stForm"] { background: #FBFCFD; border: 1px solid #E3EAF1;
                                  border-radius: 14px; padding: 1.4rem 1.4rem 0.6rem; }
      .stButton button, .stForm button { border-radius: 10px; font-weight: 600; }
      .verdict { border-radius: 14px; padding: 1.1rem 1.3rem; margin: 0.6rem 0 1rem;
                 font-size: 1.15rem; font-weight: 700; }
      .v-block { background: #FDECEC; color: #8A1C1C; border: 1px solid #F3C9C9; }
      .v-warn  { background: #FFF6E5; color: #8A5A00; border: 1px solid #F3E0B0; }
      .v-ok    { background: #EAF7EE; color: #1C6B33; border: 1px solid #BFE6CB; }
      .sec-head { display:flex; align-items:center; gap:8px; font-weight:700;
                  font-size:0.9rem; color:#0E5A8A; text-transform:uppercase;
                  letter-spacing:0.6px; margin:0.4rem 0 0.2rem;
                  padding-bottom:6px; border-bottom:2px solid #D4E0EC; }
      .sec-head .ico { font-size:1.1rem; }
      .sec-gap { margin-top:1.1rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def load_engine():
    return STABLERuleEngine(DATA_FILE)


engine = load_engine()
dose_df = engine.dose


# dropdown option lists pulled from the dataset (robust to numeric/blank/nan)
def clean_opts(col):
    vals = dose_df[col].astype(str).str.strip().unique()
    return sorted(str(v) for v in vals if str(v).strip() and str(v).strip().lower() != "nan")


drugs = clean_opts("Generic")
indications = clean_opts("Indication")
routes = clean_opts("Route")

# dataset summary counts for badges (derived live, not hardcoded)
n_drugs = len(drugs)
n_ind = len(indications)
n_rows = len(dose_df)


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


# ---------------- input form ----------------
def sec(icon, label, gap=True):
    cls = "sec-head sec-gap" if gap else "sec-head"
    st.markdown(f'<div class="{cls}"><span class="ico">{icon}</span>{label}</div>',
                unsafe_allow_html=True)


with st.form("rx"):
    sec("🫀", "Drug & Indication", gap=False)
    c1, c2 = st.columns(2)
    with c1:
        drug = st.selectbox("Drug (generic)", drugs,
                            index=drugs.index("Metoprolol") if "Metoprolol" in drugs else 0)
    with c2:
        indication = st.selectbox("Indication", indications,
                                  index=indications.index("Hypertension") if "Hypertension" in indications else 0)

    sec("👤", "Patient")
    c1, c2 = st.columns(2)
    with c1:
        age = st.number_input("Age (years)", min_value=0.0, max_value=120.0,
                              value=55.0, step=1.0)
        pregnant = st.checkbox("Patient is pregnant")
    with c2:
        weight = st.number_input("Weight (kg) — for weight-based drugs", min_value=0.0,
                                 value=0.0, step=1.0, help="Leave 0 if not applicable")

    sec("💊", "Dose & Route")
    c1, c2 = st.columns(2)
    with c1:
        dose = st.number_input("Prescribed dose (mg)", min_value=0.0, value=50.0, step=1.0)
        freq = st.number_input("Frequency (times per period)", min_value=0.0, value=1.0, step=1.0)
    with c2:
        route = st.selectbox("Route", routes,
                             index=routes.index("Oral-PO") if "Oral-PO" in routes else 0)
        crcl = st.number_input("Creatinine clearance (mL/min) — 0 = not provided",
                               min_value=0.0, value=0.0, step=1.0)

    sec("🧪", "Clinical Context")
    c1, c2 = st.columns(2)
    with c1:
        comorbidities = st.text_input("Comorbidities (comma-separated)",
                                      placeholder="e.g. asthma, renal stenosis")
    with c2:
        coprescribed = st.text_input("Co-prescribed drugs (comma-separated)",
                                     placeholder="e.g. verapamil")

    st.markdown('<div class="sec-gap"></div>', unsafe_allow_html=True)
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

    # top-level verdict (styled card)
    if has_block:
        st.markdown('<div class="verdict v-block">⛔ BLOCK — do not dispense without review</div>',
                    unsafe_allow_html=True)
    elif has_warn:
        st.markdown('<div class="verdict v-warn">⚠️ CHECK — review before dispensing</div>',
                    unsafe_allow_html=True)
    else:
        st.markdown('<div class="verdict v-ok">✅ Within documented parameters</div>',
                    unsafe_allow_html=True)

    # detailed flags
    with st.expander("See detailed flags", expanded=True):
        for f in flags:
            if f.severity == BLOCK:
                st.error(f"**{f.rule}** — {f.message}")
            elif f.severity == WARN:
                st.warning(f"**{f.rule}** — {f.message}")
            else:
                st.info(f"**{f.rule}** — {f.message}")

    # transparency: which STABLE rows drove the verdict
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
