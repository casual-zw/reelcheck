"""Rebuild the original pilot from source text inspected in Chrome.

Run from project root. Snapshots are local provenance, not model inputs.
Generated labels require an independent human review before benchmark claims.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "density": ("usgs-density.txt", "https://www.usgs.gov/water-science-school/science/water-density", "USGS Water Science School"),
    "evaporation": ("usgs-evaporation.txt", "https://www.usgs.gov/water-science-school/science/evaporation-and-water-cycle", "USGS Water Science School"),
    "moon": ("nasa-moon.txt", "https://science.nasa.gov/moon/facts/", "NASA Science"),
    "heat": ("usgs-heat.txt", "https://www.usgs.gov/special-topic/water-science-school/science/heat-capacity-and-water", "USGS Water Science School"),
}
QUOTES = {
    "D1": ("density", "The density of water is roughly 1 gram per milliliter but, this changes with temperature or if there are substances dissolved in it."),
    "D2": ("density", "Ice is less dense than liquid water which is why your ice cubes float in your glass."),
    "D3": ("density", "Heavy water is indeed heavier than normal water (which contains a tiny amount of heavy water molecules naturally), and heavy-water ice will sink in normal water."),
    "E1": ("evaporation", "Evaporation is the process that changes liquid water to gaseous water (water vapor)."),
    "E2": ("evaporation", "Water easily evaporates at its boiling point (212° F, 100° C) but evaporates much more slowly at its freezing point because of the heat energy required to evaporate the water."),
    "E3": ("evaporation", "Condensation\u00a0is the process of water vapor turning back into liquid water."),
    "M1": ("moon", "The Moon is an average of 238,855 miles (384,400 kilometers) away."),
    "M2": ("moon", "The Moon has a very thin and tenuous atmosphere called an exosphere. It is not breathable."),
    "M3": ("moon", "The Moon has no rings."),
    "H1": ("heat", "Water has to absorb 4,184 Joules of heat (1 kilocalorie) for the temperature of one kilogram of water to increase 1°C."),
    "H2": ("heat", "For the sake of comparison, it only takes 385 Joules of heat to raise 1 kilogram of copper 1°C."),
    "H3": ("heat", "Cities near the oceans will tend to have less change and less extreme temperatures than inland cities."),
}
# claim, visible evidence, label, acceptable decisive passage set, diagnostic slice, reason
CASES = [
    ("Water's density is roughly 1 gram per milliliter, and it changes with temperature and dissolved substances.", ["D1", "D2"], "supported", ["D1"], "qualified_support", None),
    ("Heavy-water ice sinks in normal water.", ["D2", "D3"], "supported", ["D3"], "exception", None),
    ("Every kind of ice floats in normal water, including heavy-water ice.", ["D2", "D3"], "contradicted", ["D3"], "overbroad_scope", None),
    ("Heavy-water ice sinks in normal water.", ["D1"], "insufficient", [], "withheld_decisive_evidence", "missing_evidence"),
    ("Evaporation changes liquid water into water vapor.", ["E1", "E3"], "supported", ["E1"], "normal", None),
    ("Water cannot evaporate at its freezing point; evaporation only happens at its boiling point.", ["E1", "E2"], "contradicted", ["E2"], "condition", None),
    ("Condensation turns liquid water into water vapor.", ["E1", "E3"], "contradicted", ["E3"], "direction", None),
    ("Pure water boils at exactly 100 degrees Celsius at every altitude.", ["E1", "E3"], "insufficient", [], "missing_condition_evidence", "missing_evidence"),
    ("The Moon is about 384,400 kilometers from Earth on average.", ["M1", "M2"], "supported", ["M1"], "qualified_quantity", None),
    ("The Moon has a thin exosphere that humans cannot breathe.", ["M2", "M3"], "supported", ["M2"], "compound_support", None),
    ("The Moon's average distance from Earth is 384,400 miles.", ["M1", "M3"], "contradicted", ["M1"], "wrong_unit", None),
    ("On January 1, 2030, the Moon will be exactly 384,400 kilometers from Earth.", ["M1", "M3"], "insufficient", [], "average_vs_specific_date", "missing_evidence"),
    ("Raising one kilogram of water by one degree Celsius requires 4,184 joules of heat.", ["H1", "H2"], "supported", ["H1"], "normal_quantity", None),
    ("Raising one kilogram of water by one degree Celsius requires only 385 joules of heat.", ["H1", "H2"], "contradicted", ["H1"], "wrong_entity_quantity", None),
    ("Raising one gram of water by one degree Celsius requires 4,184 joules of heat.", ["H1", "H2"], "contradicted", ["H1"], "wrong_mass_unit", None),
    ("San Francisco's daily temperature range is exactly five degrees Celsius smaller than Sacramento's.", ["H3"], "insufficient", [], "general_vs_specific", "missing_evidence"),
]


def main():
    sources, passages = {}, {}
    for sid, (filename, url, author) in SOURCES.items():
        raw = (ROOT / "data/source_snapshots" / filename).read_text()
        sources[sid] = {"source_id": sid, "url": url, "author": author,
                        "retrieved_date": "2026-11-02", "snapshot_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                        "rights_note": "Short agency-authored factual text only; no photos, third-party tables, or artwork copied.",
                        "text": raw}
    for pid, (sid, quote) in QUOTES.items():
        if quote not in sources[sid]["text"]:
            raise ValueError(f"Quote {pid} not found verbatim in saved source")
        passages[pid] = {"id": pid, "source_id": sid, "url": sources[sid]["url"],
                         "retrieved_date": "2026-11-02", "text": quote,
                         "sha256": hashlib.sha256(quote.encode()).hexdigest()}
    inputs, gold = [], []
    for i, (claim, pids, label, required, slice_name, reason) in enumerate(CASES, 1):
        cid = f"dev_{i:02d}"
        group = QUOTES[pids[0]][0]
        inputs.append({"case_id": cid, "group_id": group, "split": "development", "as_of": "2026-11-02",
                       "claim_text": claim, "evidence": [passages[p] for p in pids]})
        gold.append({"case_id": cid, "verdict": label, "acceptable_evidence_sets": [required],
                     "uncertainty_reason": reason, "slice": slice_name,
                     "label_status": "AI_draft_pending_independent_human_review"})
    for filename, rows in [("dev_inputs.jsonl", inputs), ("dev_gold.jsonl", gold),
                           ("sources.jsonl", [{k:v for k,v in s.items() if k != "text"} for s in sources.values()])]:
        (ROOT / "data" / filename).write_text("".join(json.dumps(r, ensure_ascii=False)+"\n" for r in rows))
    print(f"Built {len(inputs)} development cases from {len(sources)} inspected source pages; labels need human review.")


if __name__ == "__main__":
    main()
