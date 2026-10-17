"""Technical validation checks for the STABLE dataset.

Usage:
    python validate_stable.py <folder containing the three STABLE CSV files>

Runs the automated checks described in the Technical Validation section:
required fields, duplicate rows, minimum <= maximum order for paired
numeric fields, and cross-table matching of generic names.
Text values in numeric columns (e.g. combination ratios such as 10/20)
are reported as skipped, not as failures.
"""
import sys
from pathlib import Path

import pandas as pd

DOSING = "indication_based_dosing.csv"
SAFETY = "drug_safety_profile.csv"
RENAL = "renal_adjustment_dosing.csv"

REQUIRED_DOSING = ["Generic", "Indication", "Age Group", "Type of Doses", "Route"]

PAIRS = {
    DOSING: [
        ("Min Direct Dose mg(Multiple Strength)", "Max Direct Dose mg(Multiple Strength)"),
        ("Dose Per Weight mg(Min Multiple Strength)", "Dose Per Weight mg(Max Multiple Strength)"),
        ("Min Single Dose(Unit)", "Max Single Dose(Unit)"),
        ("Min Frequency", "Max Frequency"),
        ("Age_Min_Years_Inclusive", "Age_Max_Years_Exclusive"),
        ("Weight_Min_Kg_Inclusive", "Weight_Max_Kg_Exclusive"),
    ],
    RENAL: [
        ("Min CrCl", "Max CrCl"),
        ("Min GFR", "Max GFR"),
        ("Min Direct Dose (Multiple Strength)", "Max Direct Dose (Multiple Strength)"),
        ("Min Frequency", "Max Frequency"),
    ],
}


def check_pairs(df, name, pairs, id_col):
    failures, skipped = [], 0
    for lo_col, hi_col in pairs:
        lo = pd.to_numeric(df[lo_col], errors="coerce")
        hi = pd.to_numeric(df[hi_col], errors="coerce")
        both_present = df[lo_col].notna() & df[hi_col].notna()
        numeric = lo.notna() & hi.notna()
        skipped += int((both_present & ~numeric).sum())
        bad = numeric & (lo > hi)
        for idx in df.index[bad]:
            failures.append(f"{name} {df.at[idx, id_col]}: {lo_col}={lo[idx]} > {hi_col}={hi[idx]}")
    return failures, skipped


def main(folder):
    folder = Path(folder)
    d = pd.read_csv(folder / DOSING, dtype=str)
    s = pd.read_csv(folder / SAFETY, dtype=str)
    r = pd.read_csv(folder / RENAL, dtype=str)
    problems = 0

    print(f"Rows: dosing {len(d)}, safety {len(s)}, renal {len(r)}")
    print(f"Generics: dosing {d['Generic'].nunique()}, safety {s['Generic'].nunique()}, renal {r['Generic'].nunique()}")

    for col in REQUIRED_DOSING:
        n = int(d[col].isna().sum())
        problems += n
        print(f"[required] dosing '{col}' empty: {n}")

    for name, df, idc in [(DOSING, d, "Dosing_Record_ID"), (RENAL, r, "Renal_Adjustment_Record_ID")]:
        dup = int(df.drop(columns=[idc]).duplicated().sum())
        problems += dup
        print(f"[duplicates] {name}: {dup}")

    for name, df, idc in [(DOSING, d, "Dosing_Record_ID"), (RENAL, r, "Renal_Adjustment_Record_ID")]:
        fails, skipped = check_pairs(df, name, PAIRS[name], idc)
        problems += len(fails)
        print(f"[min<=max] {name}: {len(fails)} violations, {skipped} text-valued pairs skipped")
        for f in fails:
            print("   ", f)

    dosing_generics = set(d["Generic"])
    for name, df in [(SAFETY, s), (RENAL, r)]:
        missing = sorted(set(df["Generic"]) - dosing_generics)
        problems += len(missing)
        print(f"[cross-table] {name} generics not in dosing table: {len(missing)} {missing}")

    print("PASS" if problems == 0 else f"{problems} issue(s) found")
    return 0 if problems == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
