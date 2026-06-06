"""
detector.py — deterministic SEO issue detection from a Screaming Frog internal_all.csv.

STARTER IMPLEMENTATION. It already detects several issues so the pipeline runs end to
end. Your job in the Sprint is to COMPLETE the rulebook (see rulebook.md): add the
missing detectors, handle edge cases, and improve accuracy against the hidden export.

Standard library only (csv). Detection is plain Python on purpose — the model is for
judgment (rewriting titles, choosing redirect targets), not for counting rows.
"""

from __future__ import annotations
import csv
import os
from collections import defaultdict


def load_rows(export_dir: str) -> list[dict]:
    path = os.path.join(export_dir, "internal_all.csv")
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _int(v, default=0):
    try:
        return int(float(str(v).strip()))
    except Exception:
        return default


def _float(v, default=0.0):
    try:
        return float(str(v).strip())
    except Exception:
        return default


def is_html(r):  return "text/html" in (r.get("Content Type", "") or "").lower()
def is_200(r):   return _int(r.get("Status Code")) == 200
def indexable(r): return (r.get("Indexability", "") or "").strip().lower() == "indexable"


def detect(rows: list[dict]) -> list[dict]:
    """Return a list of issue dicts: {type, severity, affected_urls, count, explanation}.
    STARTER set — extend to the full rulebook for a high score."""
    issues = []

    def add(t, sev, urls, explanation):
        urls = sorted(set(urls))
        if urls:
            issues.append({"type": t, "severity": sev, "affected_urls": urls,
                           "count": len(urls), "explanation": explanation})

    html = [r for r in rows if is_html(r)]
    idx200 = [r for r in html if is_200(r) and indexable(r)]

    status_map = {r["Address"]: _int(r.get("Status Code")) for r in rows}

    # --- Titles ---
    add("missing_title", "High",
        [r["Address"] for r in idx200 if not (r.get("Title 1", "") or "").strip()],
        "Indexable pages with no title tag.")

    # duplicate titles (indexable only)
    by_title = defaultdict(list)
    for r in idx200:
        t = (r.get("Title 1", "") or "").strip()
        if t:
            by_title[t].append(r["Address"])
    dup_t = [u for urls in by_title.values() if len(urls) > 1 for u in urls]
    add("duplicate_title", "High", dup_t, "Pages sharing an identical title.")

    add("title_too_long", "Medium",
        [r["Address"] for r in idx200
         if _int(r.get("Title 1 Pixel Width")) > 561 or _int(r.get("Title 1 Length")) > 60],
        "Titles likely truncated in search results.")

    add("title_too_short", "Low",
        [r["Address"] for r in idx200
         if 0 < _int(r.get("Title 1 Length")) < 30],
        "Titles that are likely too short for optimal SEO.")

    # --- Meta Descriptions ---
    add("missing_meta_description", "Medium",
        [r["Address"] for r in idx200 if not (r.get("Meta Description 1", "") or "").strip()],
        "Indexable pages with no meta description.")

    # duplicate meta descriptions (indexable only)
    by_meta = defaultdict(list)
    for r in idx200:
        m = (r.get("Meta Description 1", "") or "").strip()
        if m:
            by_meta[m].append(r["Address"])
    dup_m = [u for urls in by_meta.values() if len(urls) > 1 for u in urls]
    add("duplicate_meta_description", "Medium", dup_m, "Pages sharing an identical meta description.")

    add("meta_description_too_long", "Low",
        [r["Address"] for r in idx200 if _int(r.get("Meta Description 1 Length")) > 155],
        "Meta descriptions likely truncated in search results.")

    # --- H1s ---
    add("missing_h1", "Medium",
        [r["Address"] for r in html if is_200(r) and not (r.get("H1-1", "") or "").strip()],
        "Pages with no H1 tag.")

    # duplicate h1s (indexable only)
    by_h1 = defaultdict(list)
    for r in idx200:
        h = (r.get("H1-1", "") or "").strip()
        if h:
            by_h1[h].append(r["Address"])
    dup_h1 = [u for urls in by_h1.values() if len(urls) > 1 for u in urls]
    add("duplicate_h1", "Low", dup_h1, "Pages sharing an identical H1.")

    # --- Response codes ---
    add("broken_link", "High",
        [r["Address"] for r in rows if 400 <= _int(r.get("Status Code")) <= 499],
        "URLs returning a client error (4xx).")
    add("server_error", "High",
        [r["Address"] for r in rows if 500 <= _int(r.get("Status Code")) <= 599],
        "URLs returning a server error (5xx).")
    add("redirect", "Medium",
        [r["Address"] for r in rows if 300 <= _int(r.get("Status Code")) <= 399],
        "URLs that redirect (3xx).")

    # --- Redirect Chains ---
    redirect_map = {r["Address"]: r.get("Redirect URL", "")
                    for r in rows if 300 <= _int(r.get("Status Code")) <= 399}

    chain_members = set()
    for start_node in redirect_map:
        path = []
        curr = start_node
        while curr in redirect_map and curr not in path:
            path.append(curr)
            curr = redirect_map[curr]

        # Handle loop: if curr is in path, the cycle is part of the chain
        if curr in path:
            # All nodes in the path are part of the cycle or lead to it
            if len(path) > 1:
                chain_members.update(path)
            elif len(path) == 1 and redirect_map[path[0]] == path[0]:
                # Single node loop A -> A is a chain of length 1?
                # Rulebook: "a redirect whose Redirect URL is itself a redirecting URL"
                # A -> A fits this. Let's consider it a chain.
                chain_members.update(path)
        elif len(path) > 1:
            # Standard chain A -> B -> ... -> Final
            chain_members.update(path)

    add("redirect_chain", "High", list(chain_members), "URLs participating in a redirect chain (length > 1).")

    # --- Orphan pages ---
    add("orphan_page", "Medium",
        [r["Address"] for r in idx200 if _int(r.get("Inlinks")) == 0],
        "Indexable pages with zero internal links in.")

    add("thin_content", "Low",
        [r["Address"] for r in html if indexable(r) and _int(r.get("Word Count")) < 200],
        "Indexable pages with low word count (< 200).")

    add("slow_page", "Low",
        [r["Address"] for r in rows if _float(r.get("Response Time")) > 1.0],
        "Pages with high response time (> 1.0s).")

    add("non_indexable_but_linked", "Medium",
        [r["Address"] for r in rows if (r.get("Indexability", "") or "").strip().lower() == "non-indexable" and _int(r.get("Inlinks")) > 0],
        "Non-indexable pages that are still linked internally.")


    return issues


def summarize(issues: list[dict]) -> dict:
    by_sev = defaultdict(int)
    for i in issues:
        by_sev[i["severity"]] += 1
    return {"total_issues": len(issues),
            "by_severity": {"High": by_sev["High"], "Medium": by_sev["Medium"], "Low": by_sev["Low"]}}


if __name__ == "__main__":
    import sys, json
    d = sys.argv[1] if len(sys.argv) > 1 else "../sample-export"
    rows = load_rows(d)
    iss = detect(rows)
    print(f"Loaded {len(rows)} rows, detected {len(iss)} issue types.")
    print(json.dumps(summarize(iss), indent=2))
    for i in iss:
        print(f"  [{i['severity']:<6}] {i['type']:<24} x{i['count']}")
