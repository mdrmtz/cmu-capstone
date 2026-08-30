---
name: wcag-mcp
description: Query authoritative WCAG 2.2 data via MCP. Use when implementing or reviewing accessibility: looking up success criteria, finding techniques, checking failure patterns, scoping a conformance level, or resolving ambiguous spec language.
---

# WCAG MCP

Provides access to the `wcag` MCP server (`https://wcag-mcp.netlify.app/mcp`) — 20 tools backed by official W3C data covering all WCAG 2.2 success criteria, techniques, and glossary.

## When to Call Which Tool

| Situation | Tool |
|---|---|
| Full requirement + intent for a specific SC | `get-criterion` e.g. `"1.4.3"` |
| SC + all techniques + failure patterns in one call | `get-full-criterion-context` |
| Common mistakes to avoid for an SC | `get-failures-for-criterion` |
| All SCs for a conformance level (scope AA work) | `get-criteria-by-level` with `includeBelow: true` |
| Don't know the SC number, know the topic | `search-wcag` e.g. `"focus"`, `"contrast"`, `"label"` |
| Choose between implementation techniques | `get-techniques-for-criterion` |
| Verify a specific technique (sufficient vs. advisory vs. failure) | `get-technique` e.g. `"H37"`, `"ARIA1"` |
| Precise normative definition of a term | `get-glossary-term` |
| What changed between WCAG 2.1 and 2.2 | `whats-new-in-wcag22` |

## Workflow

**Before implementing** a component with accessibility requirements:
1. `search-wcag` with the relevant topic to find applicable SCs
2. `get-full-criterion-context` on each SC to get requirements + techniques in one call

**Before shipping / during code review:**
1. `get-failures-for-criterion` for each relevant SC — confirm none apply to your implementation

**At project start:**
1. `get-criteria-by-level("AA", { includeBelow: true })` to enumerate all requirements and decide scope

## Notes

- Server config: `.vscode/mcp.json` in this workspace
- Data source: W3C `https://www.w3.org/WAI/WCAG22/wcag.json` — regenerated on each deploy
- All 20 tools are stateless JSON-RPC calls; no auth required
