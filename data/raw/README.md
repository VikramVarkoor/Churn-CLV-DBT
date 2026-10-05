# data/raw

This folder is git-ignored. It holds the raw dataset file, which is not committed to the repo.

Source: UCI Online Retail II, https://archive.ics.uci.edu/dataset/502/online+retail+ii
License: CC BY 4.0

## How to populate this folder

The dataset was downloaded manually because the build sandbox used to develop this project could
not reach archive.ics.uci.edu (outbound network policy blocked it; verified by a direct curl test
on 2026-10-05, HTTP CONNECT tunnel rejected).

Steps:
1. Go to https://archive.ics.uci.edu/dataset/502/online+retail+ii and download the dataset
   (an .xlsx file with two sheets, "Year 2009-2010" and "Year 2010-2011").
2. Save it here as `data/raw/online_retail_II.xlsx`.
3. Run `python3 python/audit.py` from the repo root. It reads this file, combines both sheets,
   writes a cleaned copy to `data/raw/online_retail_ii_combined.parquet` (also git-ignored), and
   prints the Phase 0 audit numbers (section 3 of the project brief).
