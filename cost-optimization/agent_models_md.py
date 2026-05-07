"""
Config-as-source-of-truth: parse a markdown table at request time to
derive runtime model assignments. Editing the markdown moves the
dashboard. No hardcoded model strings in Python that drift from intent.

Convention: a single markdown file (e.g. AGENT_MODELS.md) holds tables
that map each agent → (text model, image model, manager). The dashboard
parses these at every request, so:

- Operators edit markdown to change a model — no code change, no deploy
- Dashboard reflects the edit on the next /api/overview rebuild
- Conflict checker compares the markdown vs the runtime config and
  surfaces drift as a dashboard alarm

This file shows the parser + a small example of how a dashboard view
function consumes it to override hardcoded defaults.

Example AGENT_MODELS.md:

    ## Team A
    | Bot     | Role             | Text Model               | Image Model                          | Reports To |
    |---------|------------------|--------------------------|--------------------------------------|------------|
    | scanner | source intel     | google/gemini-2.5-flash  | —                                    | manager    |
    | creator | drafting         | openai/gpt-4.1           | nano-banana-pro / google/gemini-3-pro-image | manager    |
"""
from __future__ import annotations

import re
from pathlib import Path

HEADER_BOUNDARY = re.compile(r"^\s*\|\s*-{2,}", re.MULTILINE)
ROW = re.compile(r"^\s*\|(.+)\|\s*$")


def parse_md_table_rows(text: str, section_title: str | None = None) -> list[dict]:
    """Parse all GFM tables in `text` and return a list of dict rows
    (key = lowercased+underscored header). If section_title is given,
    only parse tables under that section heading."""
    if section_title:
        # Find the section header, take text until next heading of same/higher level
        section_re = re.compile(rf"^#+\s+{re.escape(section_title)}\s*$",
                                re.MULTILINE | re.IGNORECASE)
        m = section_re.search(text)
        if not m:
            return []
        rest = text[m.end():]
        next_section = re.search(r"^#+\s+", rest, re.MULTILINE)
        if next_section:
            rest = rest[:next_section.start()]
        text = rest

    out = []
    lines = text.splitlines()
    i = 0
    while i < len(lines) - 1:
        # A header row is | a | b |, followed by | --- | --- |
        if ROW.match(lines[i]) and HEADER_BOUNDARY.match(lines[i + 1] or ""):
            headers = [h.strip().lower().replace(" ", "_")
                       for h in ROW.match(lines[i]).group(1).split("|")]
            i += 2
            while i < len(lines) and ROW.match(lines[i]):
                cells = [c.strip() for c in ROW.match(lines[i]).group(1).split("|")]
                if len(cells) >= len(headers):
                    out.append(dict(zip(headers, cells[:len(headers)])))
                i += 1
        else:
            i += 1
    return out


# ── Domain-specific helpers built on the table parser ─────────────────────

def parse_agent_models_table(path: Path) -> dict[str, dict]:
    """Read AGENT_MODELS.md → {bot_name: {role, text_model, image_model, ...}}.

    Treats `Bot` as the primary key, lowercases header names, drops the
    table-header row whose Bot column literally says 'Bot'.
    """
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    rows: dict[str, dict] = {}
    for entry in parse_md_table_rows(text):
        bot = entry.get("bot", "").strip()
        if not bot or bot.lower() == "bot":
            continue
        rows[bot] = {
            "role": entry.get("role", ""),
            "model": entry.get("text_model", ""),
            "imageModel": entry.get("image_model", ""),
            "reportsTo": entry.get("reports_to", ""),
            "path": str(path),
        }
    return rows


def derive_support_models(image_model_raw: str) -> list[str]:
    """Split a slash- or comma-separated image-model column into a list.

    Splits on " / " (with mandatory spaces) only — model names like
    "google/gemini-3-pro-image" have un-spaced slashes inside and must
    stay intact.
    """
    if not image_model_raw or image_model_raw in {"—", "-", "n/a", "N/A", "none", ""}:
        return []
    parts = re.split(r"\s+/\s+|\s*,\s*", image_model_raw)
    return [p.strip() for p in parts if p.strip()]


def synthesize_model_uses(
    primary_model: str,
    role: str,
    support_models: list[str],
) -> list[dict]:
    """Build a [{model, use}, ...] list for the dashboard."""
    out = [{"model": primary_model, "use": role or "primary execution"}]
    for sm in support_models:
        out.append({"model": sm, "use": "image generation"})
    return out


# ── Example: how a dashboard view function consumes this ──────────────────
#
# def build_capability_view(agents, hardcoded_defaults):
#     table = parse_agent_models_table(Path("AGENT_MODELS.md"))
#     rows = []
#     for agent in agents:
#         row = table.get(agent.name, {})
#         primary = row.get("model") or hardcoded_defaults.get(agent.name, {}).get("primary")
#         support = derive_support_models(row.get("imageModel", ""))
#         model_uses = synthesize_model_uses(primary, row.get("role", ""), support)
#         rows.append({
#             "bot": agent.name,
#             "primaryModel": primary,
#             "supportModels": support,
#             "modelUses": model_uses,
#         })
#     return rows
#
# A "config conflict" detector then compares table[bot].model against
# the live runtime config (e.g. AGENTS.json) and surfaces drift on
# the dashboard:
#
#     if primary != runtime_config.get(bot, {}).get("primary"):
#         conflicts.append({
#             "bot": bot,
#             "type": "model_drift",
#             "table_says": primary,
#             "runtime_says": runtime_config[bot]["primary"],
#         })
