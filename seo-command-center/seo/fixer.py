"""
fixer.py — model-driven SEO fixes (titles, metas, redirects).
Uses local Ollama API for generation and difflib for candidate search.
"""
from __future__ import annotations
import json
import urllib.request
from difflib import SequenceMatcher

import os

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = os.environ.get("RADAR_MODEL", "qwen3.5:9b")

def call_ollama(prompt: str) -> str:
    """Simple wrapper for Ollama generate API."""
    try:
        data = json.dumps({"model": MODEL, "prompt": prompt, "stream": False}).encode("utf-8")
        req = urllib.request.Request(OLLAMA_URL, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8")).get("response", "").strip()
    except Exception:
        return ""

def get_similarity_candidates(broken_url: str, rows: list[dict], limit=5) -> list[str]:
    """Find the most similar 200 OK indexable URLs based on path similarity."""
    candidates = []
    for r in rows:
        # Filter for 200 OK indexable
        if (r.get("Status Code") == "200" or (r.get("Status Code") and r.get("Status Code").strip() == "200")) and \
           (r.get("Indexability", "").strip().lower() == "indexable"):
            addr = r.get("Address", "")
            if addr:
                score = SequenceMatcher(None, broken_url, addr).ratio()
                candidates.append((score, addr))

    candidates.sort(key=lambda x: x[0], reverse=True)
    return [addr for score, addr in candidates[:limit]]

def generate_text(url: str, context: dict, text_type: str) -> str:
    """Generate an optimized title or meta description with a length-check retry."""
    limit = 60 if text_type == "title" else 155
    h1 = context.get("h1", "N/A")
    current = context.get("current", "N/A")

    prompt = (f"You are an SEO expert. Rewrite the following {text_type} for the page {url}. "
              f"Context: H1='{h1}', Current='{current}'. "
              f"Requirements: Max {limit} characters. Return ONLY the text of the {text_type}, "
              f"no quotes, no labels, no explanations.")

    res = call_ollama(prompt)

    # Validation and Retry
    if len(res) > limit:
        retry_prompt = (f"The following {text_type} is {len(res)} characters long:\n\n"
                       f"{res}\n\n"
                       f"Rewrite it to under {limit} characters while preserving SEO value. "
                       f"Return ONLY the text.")
        res = call_ollama(retry_prompt)

    return res[:limit] # Hard crop as last resort

def suggest_redirect(broken_url: str, candidates: list[str]) -> str | None:
    """Use the model to pick the best redirect target from candidates."""
    if not candidates:
        return None

    cand_list = "\n".join([f"- {c}" for c in candidates])
    prompt = (f"The URL {broken_url} is a 404. Which of these live candidates is the most logical replacement? "
              f"Candidates:\n{cand_list}\n"
              f"Return ONLY the best URL from the list, or 'None' if no match is logical.")

    res = call_ollama(prompt).strip()
    return res if res in candidates else None

def run_fixer_pipeline(rows: list[dict], issues: list[dict]) -> dict:
    """Process the detected issues and generate a set of fixes."""
    fixes = {"titles": [], "redirect_map": []}

    # Map rows by Address for quick context lookup
    row_map = {r["Address"]: r for r in rows if "Address" in r}

    # Separate issues to handle capping
    title_issues = [i for i in issues if i["type"] in ("missing_title", "title_too_long")]
    meta_issues = [i for i in issues if i["type"] in ("missing_meta_description", "meta_description_too_long")]
    broken_issues = [i for i in issues if i["type"] == "broken_link"]

    # 1. Fix Titles (Limit 10)
    for i in title_issues[:10]:
        urls = i["affected_urls"]
        for url in urls:
            r = row_map.get(url, {})
            context = {"h1": r.get("H1-1", "N/A"), "current": r.get("Title 1", "N/A")}
            new_val = generate_text(url, context, "title")
            fixes["titles"].append({"url": url, "old": context["current"], "new": new_val})
            if len(fixes["titles"]) >= 10: break
        if len(fixes["titles"]) >= 10: break

    # 2. Fix Metas (Limit 10)
    for i in meta_issues[:10]:
        urls = i["affected_urls"]
        for url in urls:
            r = row_map.get(url, {})
            context = {"h1": r.get("H1-1", "N/A"), "current": r.get("Meta Description 1", "N/A")}
            new_val = generate_text(url, context, "meta")
            fixes["titles"].append({"url": url, "old": context["current"], "new": new_val}) # Note: titles list often used for all meta-tags in starter
            if len(fixes["titles"]) >= 20: break # 10 titles + 10 metas
        if len(fixes["titles"]) >= 20: break

    # Note: The starter server.py and a common pattern in this project is a single 'titles' list
    # for all metadata rewrites. We follow that.

    # 3. Redirect Suggestions (Limit 10)
    for i in broken_issues[:10]:
        urls = i["affected_urls"]
        for url in urls:
            candidates = get_similarity_candidates(url, rows)
            best = suggest_redirect(url, candidates)
            if best:
                fixes["redirect_map"].append({"from": url, "to": best, "reason": "Path similarity match"})
            if len(fixes["redirect_map"]) >= 10: break
        if len(fixes["redirect_map"]) >= 10: break

    return fixes
