SEO Command Center — Forge Sprint 01 starter
A Claude Code plugin that ingests a Screaming Frog SEO export, audits it against the rulebook, prioritizes the issues, writes fixes, and renders a live dashboard plus an exportable client report.

Quick start (headless)
bash
pip install mcp
python run.py sample-export/
# Live cockpit: http://localhost:7700
# Outputs: outputs/report.json and outputs/report.html
Inside Claude Code
/seo-audit sample-export/
Project structure
seo-command-center/
├── .claude-plugin/plugin.json   plugin manifest
├── .claude/                     audit hooks (settings.json + hooks/audit.sh)
├── skills/seo-audit/SKILL.md    orchestrator
├── agents/                      ingest, auditor, fixer, reporter
├── mcp/server.py                MCP server + dashboard (localhost:7700)
├── seo/detector.py              deterministic issue detection
├── dashboard/                   index.html + app.js
├── run.py                       headless runner (grader entry point)
└── outputs/                     report.json + report.html
Process files (graded)
File	Purpose
.claude/audit.jsonl	Auto-written by hooks — commit it
agent-log.md	Session transcript — run bash scripts/export-transcript.sh
CLAUDE.md	Project memory / agent instructions
PROMPTS.md	Key prompts log
DECISIONS.md	Real decisions and learnings

