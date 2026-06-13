"""
STABLE Dose Advisor — context-aware dose suggestion tool.

Run locally:
    pip install streamlit pandas openpyxl
    streamlit run app.py

Deploy:
    push this file + stable_suggestion_engine.py + STABLE_age_ranged.xlsx
    to a GitHub repo, then connect at share.streamlit.io.
"""

import streamlit as st
import pandas as pd
from stable_suggestion_engine import (
    STABLESuggestionEngine, DANGER, CAUTION, NOTE
)

DATA_FILE = "STABLE_age_ranged.xlsx"

st.set_page_config(
    page_title="STABLE Dose Advisor",
    page_icon="💊",
    layout="wide"
)

# ── load engine ──────────────────────────────────────────────────────────
@st.cache_resource
def load_engine():
    return STABLESuggestionEngine(DATA_FILE)

engine = load_engine()


# ── custom CSS ───────────────────────────────────────────────────────────
st.markdown("""
<style>
.card {
    background: #f8f9fb; border: 1px solid #dde3ea; border-radius: 10px;
    padding: 16px 20px; margin-bottom: 10px;
}
.card-renal {
    background: #fff8e1; border: 1px solid #ffe082; border-radius: 10px;
    padding: 16px 20px; margin-bottom: 10px;
}
.phase-label {
    font-size: 13px; font-weight: 700; color: #0e5a8a;
    text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px;
}
.dose-big { font-size: 22px; font-weight: 700; color: #1a1a2e; }
.freq-line { font-size: 14px; color: #555; margin-top: 2px; }
.tag-danger {
    display: inline-block; background: #fdecea; color: #b71c1c;
    border-radius: 4px; padding: 2px 8px; font-size: 12px; font-weight: 600;
    margin-right: 4px; margin-top: 4px;
}
.tag-caution {
    display: inline-block; background: #fff3e0; color: #e65100;
    border-radius: 4px; padding: 2px 8px; font-size: 12px; font-weight: 600;
    margin-right: 4px; margin-top: 4px;
}
.tag-note {
    display: inline-block; background: #e3f2fd; color: #0d47a1;
    border-radius: 4px; padding: 2px 8px; font-size: 12px; font-weight: 600;
    margin-right: 4px; margin-top: 4px;
}
</style>
""", unsafe_allow_html=True)


# ── header ───────────────────────────────────────────────────────────────
st.title("💊 STABLE Dose Advisor")
st.caption(
    "Context-aware dose suggestions for cardiovascular drugs, drawn from the "
    "STABLE dataset. Research and decision-support tool — not a substitute "
    "for clinical judgement."
)

# ── sidebar: patient + clinical context ──────────────────────────────────
with st.sidebar:
    st.header("1 · Patient context")
    age = st.number_input("Age (years)", 0.0, 120.0, 55.0, step=1.0)
    weight = st.number_input("Weight (kg)", 0.0, 300.0, 70.0, step=1.0,
                              help="Used for weight-based dose calculation")
    pregnant = st.checkbox("Pregnant")
    crcl = st.number_input("CrCl (mL/min) — 0 = not provided",
                            0.0, 300.0, 0.0, step=1.0)

    st.header("2 · Clinical context")
    comorbidities = st.text_input("Comorbidities (comma-separated)",
                                   placeholder="e.g. diabetes, asthma")
    coprescribed = st.text_input("Current medications (comma-separated)",
                                  placeholder="e.g. verapamil, digoxin")

# ── main area: drug + indication ─────────────────────────────────────────
st.header("3 · Select drug and indication")

drugs = engine.get_drugs()
col1, col2, col3 = st.columns([2, 2, 1])
with col1:
    drug = st.selectbox("Drug (generic)", drugs,
                         index=drugs.index("Metoprolol") if "Metoprolol" in drugs else 0)

# constrain indication list to what this drug covers
available_ind = engine.get_drug_indications(drug)
with col2:
    if available_ind:
        indication = st.selectbox(
            "Indication",
            available_ind,
            index=available_ind.index("Hypertension") if "Hypertension" in available_ind else 0
        )
    else:
        indication = st.text_input("Indication", "")

routes = engine.get_routes()
with col3:
    route = st.selectbox("Route", routes,
                          index=routes.index("Oral-PO") if "Oral-PO" in routes else 0)

# ── run ──────────────────────────────────────────────────────────────────
if st.button("Show dose suggestions", type="primary", use_container_width=True):
    result = engine.suggest(
        drug=drug,
        indication=indication,
        age_years=age,
        weight_kg=weight if weight > 0 else None,
        route=route,
        crcl=crcl if crcl > 0 else None,
        comorbidities=[c.strip() for c in comorbidities.split(",") if c.strip()],
        coprescribed=[c.strip() for c in coprescribed.split(",") if c.strip()],
        pregnant=pregnant,
    )

    st.markdown(f"**Patient:** {result.patient_summary}")
    st.markdown(f"**Drug:** {result.drug} — **Indication:** {result.indication}")

    # drug-level safety tags (shown once, above the cards)
    if result.drug_level_tags:
        st.markdown("---")
        for tag in result.drug_level_tags:
            if tag.level == DANGER:
                st.error(f"⛔ **{tag.source}** — {tag.message}")
            elif tag.level == CAUTION:
                st.warning(f"⚠️ **{tag.source}** — {tag.message}")
            else:
                st.info(f"ℹ️ **{tag.source}** — {tag.message}")

    if result.message:
        st.info(result.message)

    # dose cards
    if result.cards:
        st.markdown("---")
        st.subheader("Documented dose options")

        for card in result.cards:
            css_class = "card-renal" if card.renal_adjusted else "card"
            renal_star = " ★ renal-adjusted" if card.renal_adjusted else ""

            tag_html = ""
            for t in card.tags:
                cls = {"DANGER": "tag-danger", "CAUTION": "tag-caution"}.get(t.level, "tag-note")
                tag_html += f'<span class="{cls}">{t.source}: {t.message}</span>'

            extra_lines = []
            if card.route:
                extra_lines.append(f"Route: {card.route}")
            if card.duration:
                extra_lines.append(f"Duration: {card.duration}")
            if card.administration:
                extra_lines.append(f"Administration: {card.administration}")
            if card.instruction:
                extra_lines.append(f"Instruction: {card.instruction}")
            extra_html = "<br>".join(
                f'<span style="font-size:13px;color:#666">{l}</span>' for l in extra_lines
            )

            html = f"""
            <div class="{css_class}">
                <div class="phase-label">{card.phase}{renal_star}</div>
                <div class="dose-big">{card.dose_display}</div>
                <div class="freq-line">{card.frequency}</div>
                {f'<div style="margin-top:6px">{extra_html}</div>' if extra_html else ''}
                {f'<div style="margin-top:6px">{tag_html}</div>' if tag_html else ''}
            </div>
            """
            st.markdown(html, unsafe_allow_html=True)
    else:
        st.warning("No dose options found for this combination.")

    st.caption(
        "Every value traces to a STABLE dataset row. "
        "Final prescribing decisions remain the clinician's responsibility."
    )
