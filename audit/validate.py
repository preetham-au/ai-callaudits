"""Grade the engine against the 20 hand-audited 27-Aug calls.

python -m audit.validate              # fetch, audit, compare
python -m audit.validate --fixture    # (re)write the de-identified label file

Agreement is measured per axis as the humans record it: did the reviewer write
*anything* in `Verfication Error` / `Dispostion Error`, and did we. Their exact
wording is not compared — two auditors phrase the same finding differently.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from .data import ROOT
from .run import run

SHEET = ROOT / "data" / "ground_truth" / "human_audits_2026-08-27.csv"
FIXTURE = ROOT / "tests" / "ground_truth_labels_2026-08-27.csv"

# Reviewers used '' in the first dozen rows and 'NA' in the rest for "clean".
CLEAN = {"", "na", "n/a", "-", "nil", "none"}


def _flag(cell: str) -> bool:
    return (cell or "").strip().lower() not in CLEAN


def human_labels() -> list[dict]:
    src = FIXTURE if FIXTURE.exists() and not SHEET.exists() else SHEET
    with open(src, encoding="utf-8-sig", newline="") as f:
        return [{"interaction_id": int(r["interaction_id"]),
                 "verification_error": (r.get("Verfication Error") or "").strip(),
                 "disposition_error": (r.get("Dispostion Error") or "").strip()}
                for r in csv.DictReader(f) if (r.get("interaction_id") or "").strip().isdigit()]


def write_fixture():
    """interaction_id + the two verdict columns only — no transcript, no phone,
    no policy number — so the regression set can be committed."""
    rows = human_labels()
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    with open(FIXTURE, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, ["interaction_id", "Verfication Error", "Dispostion Error"])
        w.writeheader()
        for r in rows:
            w.writerow({"interaction_id": r["interaction_id"],
                        "Verfication Error": r["verification_error"] or "NA",
                        "Dispostion Error": r["disposition_error"] or "NA"})
    print(f"wrote {FIXTURE} ({len(rows)} rows, de-identified)")


def _axis(name, pairs):
    tp = sum(h and m for h, m in pairs)
    fp = sum((not h) and m for h, m in pairs)
    fn = sum(h and (not m) for h, m in pairs)
    tn = sum((not h) and (not m) for h, m in pairs)
    n = len(pairs)
    return {"axis": name, "n": n, "agree": tp + tn, "agreement": round((tp + tn) / n, 3) if n else None,
            "human_flagged": tp + fn, "engine_flagged": tp + fp,
            "true_pos": tp, "false_pos": fp, "false_neg": fn, "true_neg": tn}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", action="store_true")
    ap.add_argument("--no-llm", action="store_true")
    a = ap.parse_args()
    if a.fixture:
        write_fixture()
        return

    hum = human_labels()
    ids = [h["interaction_id"] for h in hum]
    # These are 27-Aug calls, so they must be fetched by id, not by date.
    recs = {r["interaction_id"]: r for r in run("2026-08-27", ids, llm=not a.no_llm, save_db=False)}

    # Only the variable axis is graded now; the human sheet's Dispostion Error
    # column is still parsed and echoed, so a later disposition pass can be
    # graded against it without re-reading the workbook.
    ver, detail = [], []
    for h in hum:
        r = recs.get(h["interaction_id"])
        if not r:
            print(f"  !! {h['interaction_id']} not found in Metabase")
            continue
        mv = bool(r["verification_error"]) or any(
            v["verdict"] == "wrong" for v in r["variables"])
        ver.append((_flag(h["verification_error"]), mv))
        detail.append({"id": h["interaction_id"], "turns": r["turns"],
                       "assigned": r["disposition"], "verdict": r["verdict"],
                       "human_ver": h["verification_error"] or "NA", "engine_ver": r["verification_error"] or "NA",
                       "human_disp": h["disposition_error"] or "NA"})

    print(json.dumps({"per_axis": [_axis("verification", ver)],
                      "calls": detail}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
