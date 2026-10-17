# STABLE

STABLE is a dataset for auditing cardiovascular prescriptions. It consists of three tables that are linked by the drug's generic name (`Generic`). This repository holds the validation script for the dataset. The dataset files themselves are on Figshare.

## Dataset

The data files are deposited on Figshare:

- Private review link: https://figshare.com/s/3199979a0f2e96ca3cf7
- A DOI will replace this link once the record is published.

| File | Rows | Columns | Content |
|---|---|---|---|
| `indication_based_dosing.csv` | 1,260 | 37 | Dosing by drug, indication, age group, weight, dose type and route |
| `drug_safety_profile.csv` | 172 | 15 | One safety record per drug |
| `renal_adjustment_dosing.csv` | 88 | 23 | Renal dose adjustments, covering 36 drugs |
| `STABLE.xlsx` | 3 sheets | | The same three tables in one workbook |

The tables cover 172 cardiovascular drugs. Every file uses `Generic` as the join key. The Figshare record includes a README that describes every column.

## Validation script

`validate_stable.py` runs the automated checks described in the paper's Technical Validation section:

- required dosing fields are present
- there are no duplicate rows
- each minimum value is not greater than its paired maximum value
- every generic name in the safety and renal tables also appears in the dosing table

Text values in numeric columns, such as combination ratios like `10/20`, are reported as skipped, not as failures.

### How to run

1. Download the three CSV files from Figshare into one folder.
2. Install pandas:
