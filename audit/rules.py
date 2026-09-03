"""Deterministic checks. Everything a regex can decide is decided here so the
4B judge only ever sees the residue.

The engine grades ONE axis: did the agent say each injected value, and say it
right. Flow and disposition are no longer verified. `detect_flow`/`flow_rows`
survive because `check_variables` needs them to know how far the call actually
got -- without that gate, a call that died in the greeting reports six 'missed'
variables it never had the chance to say. They decide reachability, nothing else:
nothing is scored, flagged or reported on the strength of a flow step.

The feed already supplies numbers as English words ("six thousand eight hundred
twenty six"), so both sides of every comparison are parsed to an integer and the
integers are compared. That survives the reformatting the agent does out loud
(hyphens, "and", extra spaces) without needing to model it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Indic digits appear in transcripts wherever the agent leaked a numeral.
_INDIC_DIGITS = str.maketrans("०१२३४५६७८९௦௧௨௩௪௫௬௭௮௯", "01234567890123456789")

_UNITS = {
    "zero": 0, "oh": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19,
}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50,
         "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_SCALES = {"hundred": 100, "thousand": 1000, "lakh": 100000, "lakhs": 100000,
           "crore": 10000000, "crores": 10000000}
_NUMWORDS = set(_UNITS) | set(_TENS) | set(_SCALES) | {"and"}

# Only 1..31 are needed: these decide whether a *date* was spoken, and dates are
# the one place the agent still slips into the local script.
_HI_DAYS = {
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5, "छह": 6, "छः": 6, "सात": 7,
    "आठ": 8, "नौ": 9, "दस": 10, "ग्यारह": 11, "बारह": 12, "तेरह": 13, "चौदह": 14, "पंद्रह": 15,
    "सोलह": 16, "सत्रह": 17, "अठारह": 18, "उन्नीस": 19, "बीस": 20, "इक्कीस": 21, "बाईस": 22,
    "तेईस": 23, "चौबीस": 24, "पच्चीस": 25, "छब्बीस": 26, "सत्ताईस": 27, "अट्ठाईस": 28,
    "उनतीस": 29, "तीस": 30, "इकतीस": 31,
}
_TA_DAYS = {
    "ஒன்று": 1, "ஒன்னு": 1, "இரண்டு": 2, "ரெண்டு": 2, "மூன்று": 3, "மூணு": 3, "நான்கு": 4,
    "நாலு": 4, "ஐந்து": 5, "அஞ்சு": 5, "ஆறு": 6, "ஏழு": 7, "எட்டு": 8, "ஒன்பது": 9,
    "பத்து": 10, "பதினொன்று": 11, "பன்னிரண்டு": 12, "இருபது": 20, "முப்பது": 30,
}
_LOCAL_DAYS = {**_HI_DAYS, **_TA_DAYS}

_MONTH_NAMES = dict(enumerate(
    "january february march april may june july august september october november december".split(), 1))
_MONTHS = {m: i for i, m in _MONTH_NAMES.items()}
_MONTHS.update({m[:3]: i for m, i in list(_MONTHS.items())})
_MONTHS["sept"] = 9

# The prompt forbids local-script months, but they do occur ("चार अगस्त"), and a
# date spoken in Devanagari is still a date whose value has to be checked.
_LOCAL_MONTHS = {
    "जनवरी": 1, "फरवरी": 2, "मार्च": 3, "अप्रैल": 4, "मई": 5, "जून": 6, "जुलाई": 7,
    "अगस्त": 8, "सितंबर": 9, "सितम्बर": 9, "अक्टूबर": 10, "अक्तूबर": 10, "नवंबर": 11,
    "नवम्बर": 11, "दिसंबर": 12, "दिसम्बर": 12,
    "ஜனவரி": 1, "பிப்ரவரி": 2, "மார்ச்": 3, "ஏப்ரல்": 4, "மே": 5, "ஜூன்": 6, "ஜூலை": 7,
    "ஆகஸ்ட்": 8, "செப்டம்பர்": 9, "அக்டோபர்": 10, "நவம்பர்": 11, "டிசம்பர்": 12,
}

ABSENT = {"", "null", "none", "na", "n/a", "nil", "-", "0", "0.0", "0.00", "zero"}
_REG_PLACEHOLDERS = {"", "NEW", "NEWVEHICLE", "NEWCAR", "NEWBIKE", "NA", "NIL", "NONE", "NULL",
                     "TBD", "PENDING", "APPLIED", "APPLIEDFOR", "TEMP", "TEMPORARY", "TEMPREG",
                     "TEST", "DUMMY", "UNKNOWN", "XXXX", "XXXXXX", "0", "00", "000"}
_NAME_PLACEHOLDERS = {"unknown", "na", "n/a", "test", "customer", "user", "null", "none"}


def present(v) -> bool:
    """The feed sends missing values as the literal string "null"."""
    return str(v or "").strip().lower() not in ABSENT


def words_to_num(text: str) -> int | None:
    """'six thousand eight hundred twenty six' -> 6826. None if not parseable."""
    toks = [t for t in re.split(r"[\s\-]+", text.strip().lower()) if t and t != "and"]
    if not toks or any(t not in _NUMWORDS for t in toks):
        return None
    total = cur = 0
    seen = False
    for t in toks:
        if t in _UNITS:
            cur += _UNITS[t]; seen = True
        elif t in _TENS:
            cur += _TENS[t]; seen = True
        elif t == "hundred":
            cur = (cur or 1) * 100; seen = True
        else:
            total += (cur or 1) * _SCALES[t]; cur = 0; seen = True
    return total + cur if seen else None


def to_int(raw) -> int | None:
    """The feed is inconsistent: CONTRACT says values arrive as English words
    ("eighty five"), and some do, but most rows carry plain digits ("85").
    Accept either — the comparison is on the integer."""
    s = str(raw or "").strip().replace(",", "")
    if re.fullmatch(r"\d+(\.0+)?", s):
        return int(float(s))
    return words_to_num(s)


_TOKEN_RE = re.compile(r"[A-Za-zऀ-ॿ஀-௿]+|\d+")


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.translate(_INDIC_DIGITS).replace("-", " "))


def number_runs(text: str) -> list[tuple[int, int, int]]:
    """Every number in the text as (value, start_token, end_token_exclusive).

    Covers English number words, bare digits and local-script day words, so a
    value spoken any of those three ways is still found.
    """
    toks = _tokens(text)
    low = [t.lower() for t in toks]
    out, i = [], 0
    while i < len(low):
        t = low[i]
        if t in _NUMWORDS and t != "and":
            j = i
            while j < len(low) and low[j] in _NUMWORDS:
                j += 1
            while j > i and low[j - 1] == "and":
                j -= 1
            val = words_to_num(" ".join(low[i:j]))
            if val is not None:
                out.append((val, i, j))
            i = j
        elif t.isdigit():
            out.append((int(t), i, i + 1)); i += 1
        elif toks[i] in _LOCAL_DAYS:
            out.append((_LOCAL_DAYS[toks[i]], i, i + 1)); i += 1
        else:
            i += 1
    return out


def _near(toks: list[str], end: int, words: set[str], span: int = 5) -> bool:
    return any(t.lower().strip(".,") in words for t in toks[end:end + span])


# ---------------------------------------------------------------- expectations

def expected_spoken(name: str, raw: str) -> str | None:
    """The form the agent is supposed to say, for display next to the verdict."""
    raw = str(raw).strip()
    if name == "reg_no":
        return spoken_reg(raw)
    if name == "red":
        d = parse_red(raw)
        return f"{_num_word(d[0])} {_MONTH_NAMES[d[1]].capitalize()}" if d else None
    n = to_int(raw)
    if name in ("ncb", "dtd"):
        return f"{words_of(n) if n is not None else raw} percent"
    if name == "premium":
        return f"{words_of(n) if n is not None else raw} rupees"
    return raw


_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
         "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
         "eighteen", "nineteen"]
_TENW = {20: "twenty", 30: "thirty", 40: "forty", 50: "fifty", 60: "sixty", 70: "seventy",
         80: "eighty", 90: "ninety"}


def _num_word(n: int) -> str:
    if n < 20:
        return _ONES[n]
    return _TENW[n // 10 * 10] + ("-" + _ONES[n % 10] if n % 10 else "")


def words_of(n: int) -> str:
    """Indian-style, matching how the agent reads a premium: 91894 ->
    'ninety-one thousand eight hundred ninety-four'."""
    if n < 100:
        return _num_word(n)
    for scale, word in ((10000000, "crore"), (100000, "lakh"), (1000, "thousand"), (100, "hundred")):
        if n >= scale:
            head = words_of(n // scale) + " " + word
            rest = n % scale
            return head + (" " + words_of(rest) if rest else "")
    return _num_word(n)


def spoken_reg(raw: str) -> str:
    """OD-27-C-4962 -> 'O-D two-seven C four-nine-six-two'."""
    clean = re.sub(r"[^A-Za-z0-9]", "", raw).upper()
    groups = re.findall(r"[A-Z]+|[0-9]+", clean)
    out = []
    for g in groups:
        out.append("-".join(c if c.isalpha() else _ONES[int(c)] for c in g))
    return " ".join(out)


def parse_red(raw: str) -> tuple[int, int] | None:
    """(day, month) from the shapes the feed actually uses.

    Live data is `01-Sep` / `02-Sep` (day-first, abbreviated month), not the
    `M/D/YYYY` the prompt still describes. Numeric slash forms are read
    month-first per the prompt, with a day-first fallback when the first field
    cannot be a month.
    """
    raw = str(raw).strip()
    m = re.match(r"^(\d{1,2})[-/\s]([A-Za-z]{3,})", raw)
    if m and m.group(2).lower()[:3] in _MONTHS:
        return int(m.group(1)), _MONTHS[m.group(2).lower()[:3]]
    m = re.match(r"^([A-Za-z]{3,})[-/\s](\d{1,2})", raw)
    if m and m.group(1).lower()[:3] in _MONTHS:
        return int(m.group(2)), _MONTHS[m.group(1).lower()[:3]]
    # 'Friday, August 21, 2026' and other long forms.
    m = re.search(r"([A-Za-z]{3,})\s+(\d{1,2})\b", raw)
    if m and m.group(1).lower()[:3] in _MONTHS:
        return int(m.group(2)), _MONTHS[m.group(1).lower()[:3]]
    m = re.search(r"\b(\d{1,2})\s+([A-Za-z]{3,})", raw)
    if m and m.group(2).lower()[:3] in _MONTHS:
        return int(m.group(1)), _MONTHS[m.group(2).lower()[:3]]
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", raw)
    if m:
        return int(m.group(3)), int(m.group(2))
    m = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})", raw)
    if m:
        # Day-first. The prompt documents M/D/YYYY, but the live feed sends
        # 08-09-2026 for a policy the agent correctly reads as "eight
        # September", so the prompt is wrong about its own data.
        a, b = int(m.group(1)), int(m.group(2))
        return (a, b) if b <= 12 else (b, a)
    return None


def reg_valid(raw: str) -> bool:
    clean = re.sub(r"[^A-Za-z0-9]", "", str(raw or "")).upper()
    return (clean not in _REG_PLACEHOLDERS and len(clean) >= 6
            and sum(c.isdigit() for c in clean) >= 4)


def name_valid(raw: str) -> bool:
    return present(raw) and str(raw).strip().lower() not in _NAME_PLACEHOLDERS


# ------------------------------------------------------------ variable finding

_PCT = {"percent", "%", "प्रतिशत"}
_RUP = {"rupees", "rupee", "rs", "रुपये", "रुपए", "रूपये", "ரூபாய்"}
_NCB_CUE = {"ncb", "एन", "n"}
_DTD_CUE = {"de", "detariff", "tariff", "discount"}


def _find_money(turns, expect: int):
    """Return (verdict, turn_index, evidence). 'wrong' only when some *other*
    amount was quoted as the premium — silence is 'missed', not misinformation.
    """
    other = None
    for i, t in enumerate(turns):
        if t["role"] != "assistant":
            continue
        toks = _tokens(t["content"])
        for val, s, e in number_runs(t["content"]):
            if not _near(toks, e, _RUP):
                continue
            if val == expect:
                return "ok", i, _evidence(t["content"], toks, s, e)
            if other is None and val > 100:
                other = ("wrong", i, _evidence(t["content"], toks, s, e))
    return other or ("missed", None, None)


def _find_percent(turns, expect: int, cue: set[str]):
    other = None
    for i, t in enumerate(turns):
        if t["role"] != "assistant":
            continue
        toks = _tokens(t["content"])
        low = [x.lower() for x in toks]
        for val, s, e in number_runs(t["content"]):
            if not _near(toks, e, _PCT, span=2):
                continue
            # NCB and DTD both read "<n> percent"; the following words say which.
            tail = set(low[e:e + 6])
            if cue is _NCB_CUE and (tail & _DTD_CUE):
                continue
            if cue is _DTD_CUE and not (tail & _DTD_CUE):
                continue
            if val == expect:
                return "ok", i, _evidence(t["content"], toks, s, e)
            if other is None:
                other = ("wrong", i, _evidence(t["content"], toks, s, e))
    return other or ("missed", None, None)


def _find_date(turns, day: int, month: int):
    other = None
    for i, t in enumerate(turns):
        if t["role"] != "assistant":
            continue
        toks = _tokens(t["content"])
        low = [x.lower() for x in toks]
        for j, w in enumerate(low):
            mon = _LOCAL_MONTHS.get(toks[j])
            if not mon and len(w) >= 3:
                mon = _MONTHS.get(w) or _MONTHS.get(w[:3])
            if not mon:
                continue
            for val, s, e in number_runs(t["content"]):
                if not (e == j or s == j + 1) or not 1 <= val <= 31:
                    continue
                if (val, mon) == (day, month):
                    return "ok", i, _evidence(t["content"], toks, min(s, j), max(e, j + 1))
                if other is None:
                    other = ("wrong", i, _evidence(t["content"], toks, min(s, j), max(e, j + 1)))
    return other or ("missed", None, None)


def _find_reg(turns, raw: str):
    want = re.sub(r"[^A-Z0-9]", "", raw.upper())
    for i, t in enumerate(turns):
        if t["role"] != "assistant":
            continue
        text = t["content"].translate(_INDIC_DIGITS)
        # 'T-N nine-one A-Y' -> 'TN91AY': digit words become digits, then all
        # separators drop away, so hyphen/space noise cannot cause a miss.
        canon = re.sub(r"\b(" + "|".join(_ONES[:10]) + r")\b",
                       lambda m: str(_ONES.index(m.group(1))), text, flags=re.I)
        canon = re.sub(r"[^A-Za-z0-9]", "", canon).upper()
        if want in canon:
            return "ok", i, _snippet(t["content"])
    return "missed", None, None


def _find_text(turns, raw: str):
    """make / model / customer_name: significant tokens present, case-blind."""
    want = [w for w in re.split(r"[^A-Za-z0-9]+", str(raw)) if len(w) > 2]
    if not want:
        want = [w for w in re.split(r"[^A-Za-z0-9]+", str(raw)) if w]
    for i, t in enumerate(turns):
        if t["role"] != "assistant":
            continue
        low = t["content"].lower()
        hit = [w for w in want if w.lower() in low]
        if hit and len(hit) >= max(1, len(want) // 2):
            return "ok", i, _snippet(t["content"])
    return "missed", None, None


def _snippet(text: str, n: int = 160) -> str:
    text = " ".join(text.split())
    return text[:n] + ("…" if len(text) > n else "")


def _evidence(text: str, toks: list[str], s: int, e: int) -> str:
    win = toks[max(0, s - 5):e + 5]
    return " ".join(win)


# ------------------------------------------------------------------- the flow

FLOW_STEPS = [
    ("step1", "Identity & greeting"),
    ("step2", "Disclosure + vehicle/expiry anchor"),
    ("step3", "Discount + premium"),
    ("step4", "Payment link"),
    ("step5", "Objection / routing"),
]

_MARKERS = {
    125: {
        "step1": r"simran|सिमरन",
        "step2": r"record की जा|record की जा रही|training और quality|quality purpose|record कर",
        "step3": r"renewal premium|premium है|percent एन-सी-बी|de-tariff",
        "step4": r"payment link|link भेज|link आपके|whatsapp",
        "step5": r"sales team|quotation|branch|call कर लूंगी|callback|call करूं",
    },
    127: {
        "step1": r"aarthi|ஆர்த்தி",
        "step2": r"record ஆகுது|training and audit|audit purpose|record ஆ",
        "step3": r"renewal premium|percent ncb|de-tariff",
        "step4": r"payment link|link உங்க|அனுப்பிட்டேன்|whatsapp",
        "step5": r"sales team|quotation|branch|call பண்றேன்|callback",
    },
}


def detect_flow(turns, agent_id: int) -> dict:
    """First assistant turn matching each step's marker, plus collapse/order flags."""
    pats = {k: re.compile(v, re.I) for k, v in _MARKERS.get(agent_id, _MARKERS[125]).items()}
    seen: dict[str, int] = {}
    per_turn: dict[int, list[str]] = {}
    for i, t in enumerate(turns):
        if t["role"] != "assistant":
            continue
        hits = [s for s, p in pats.items() if p.search(t["content"])]
        # Step 1 only counts as the opener; later name-drops are not a re-greet.
        hits = [h for h in hits if not (h == "step1" and i > 2)]
        if hits:
            per_turn[i] = hits
        for h in hits:
            seen.setdefault(h, i)

    flags = []
    for i, hits in per_turn.items():
        fresh = [h for h in hits if seen.get(h) == i]
        # Sentences inside step 2, or inside step 3, are one step. Two different
        # steps landing first in the same turn is W-COLLAPSE.
        for a, b in (("step2", "step3"), ("step3", "step4"), ("step2", "step4")):
            if a in fresh and b in fresh:
                flags.append(f"W-COLLAPSE:{a}+{b}@{i}")
    order = [seen[s] for s, _ in FLOW_STEPS[:4] if s in seen]
    if order != sorted(order):
        flags.append("flow_out_of_order")
    if "step2" in seen and "step1" in seen and seen["step2"] < seen["step1"]:
        flags.append("W-1b")
    return {"seen": seen, "flags": flags}


def _last_assistant(turns) -> int:
    return max((i for i, t in enumerate(turns) if t["role"] == "assistant"), default=-1)


def flow_rows(turns, agent_id: int, det: dict) -> list[dict]:
    """A step is required once the call actually got that far: the previous step
    was delivered and the agent spoke again afterwards. Nobody is faulted for
    not quoting a premium on a call that died in the greeting.
    """
    seen, last = det["seen"], _last_assistant(turns)
    rows, prev_ok = [], True
    for idx, (step, label) in enumerate(FLOW_STEPS):
        observed = step in seen
        if step == "step1":
            required = last >= 0
        elif step == "step5":
            required = False  # only fires on an objection; the judge decides
        else:
            prev = FLOW_STEPS[idx - 1][0]
            required = prev_ok and prev in seen and last > seen[prev]
        verdict = "pass" if observed else ("fail" if required else "n/a")
        rows.append({"step": step, "label": label, "required": required,
                     "observed": observed, "turn_index": seen.get(step),
                     "verdict": verdict, "note": None})
        prev_ok = observed
    return rows


# --------------------------------------------------------------- the variables

CHECKS = [
    ("customer_name", "step1"), ("make", "step2"), ("model", "step2"),
    ("reg_no", "step2"), ("red", "step2"), ("ncb", "step3"), ("dtd", "step3"),
    ("premium", "step3"),
]


def check_variables(turns, av: dict, flow: list[dict]) -> list[dict]:
    reached = {r["step"]: (r["observed"] or r["required"]) for r in flow}
    out = []
    for name, step in CHECKS:
        raw = str(av.get(name) or "").strip()
        row = {"name": name, "required": False, "expected_raw": raw or None,
               "expected_spoken": None, "spoken": False, "verdict": "n/a",
               "turn_index": None, "evidence": None, "note": None, "checked_by": "rule",
               "step": step}
        if not present(raw) or (name == "reg_no" and not reg_valid(raw)) \
                or (name == "customer_name" and not name_valid(raw)):
            # An absent ncb/dtd means the clause is omitted entirely (P-ZERO).
            # Saying *any* figure for it is inventing a discount — I-23, and the
            # single most common human verification finding.
            if name in ("ncb", "dtd") and reached.get(step):
                v, ti, ev = _find_percent(turns, None, _NCB_CUE if name == "ncb" else _DTD_CUE)
                if v == "wrong":
                    row.update(verdict="wrong", turn_index=ti, evidence=ev, spoken=True,
                               required=True, expected_spoken="(clause omitted)",
                               note="value not supplied, yet a figure was quoted")
                    out.append(row); continue
            row["note"] = "not injected — never fault the agent for it"
            out.append(row); continue

        row["required"] = True
        row["expected_spoken"] = expected_spoken(name, raw)
        if not reached.get(step):
            row["verdict"] = "not_reached"
            row["note"] = "call ended before this step"
            out.append(row); continue

        if name in ("premium",):
            n = to_int(raw)
            res = _find_money(turns, n) if n is not None else ("missed", None, None)
        elif name in ("ncb", "dtd"):
            n = to_int(raw)
            res = _find_percent(turns, n, _NCB_CUE if name == "ncb" else _DTD_CUE) \
                if n is not None else ("missed", None, None)
        elif name == "red":
            d = parse_red(raw)
            res = _find_date(turns, *d) if d else ("missed", None, None)
        elif name == "reg_no":
            res = _find_reg(turns, raw)
        else:
            res = _find_text(turns, raw)
        row["verdict"], row["turn_index"], row["evidence"] = res
        row["spoken"] = res[0] in ("ok", "wrong")
        out.append(row)
    return out


# The four disposition contradiction rules -- voicemail with a real conversation,
# hang-up label on a long call, link-sent with no link, progress label on a call
# the customer dropped -- lived here. Removed with the flow verification: the
# engine no longer judges the platform's label, only whether the injected values
# were spoken. The label itself still travels through to the UI and the export as
# plain data; we simply stop having an opinion about it.
#
# `git log -S check_disposition -- audit/rules.py` has them if they are wanted back.


def load_rubric(agent_id: int) -> dict:
    p = ROOT / "rubric" / f"{agent_id}.json"
    if not p.exists():
        p = ROOT / "rubric" / "125.json"
    return json.loads(p.read_text(encoding="utf-8"))
