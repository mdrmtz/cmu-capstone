# The A11y Fixer — CMU Agentic AI Capstone

> ## 🅰️ The A11y Fixer — CMU Agentic AI Capstone (Module 7, Assignment 7.1)
>
> This repository is one of six that make up **The A11y Fixer**: an autonomous multi-agent system that crawls and audits Angular applications for WCAG 2.2 AA accessibility violations, and delivers verified, human-reviewable fixes as real pull requests — built for the CMU Agentic AI Program capstone.
>
> **This repo's role:** this is the umbrella project. It links `a11y-fixer`, `dashboard-app`, and `presentation` as real git submodules, hosts the six capstone checkpoint documents plus the final report, and publishes the documentation/chat site.

| Repository | Role |
| --- | --- |
| [`a11y-fixer`](https://github.com/mdrmtz/a11y-fixer) | The autonomous agent itself — orchestration, sub-agents, CLI, guardrails, evaluation harness. **Start here for a technical review.** |
| [`dashboard-app`](https://github.com/mdrmtz/dashboard-app) | Human-in-the-loop review dashboard (Angular + Express) — the Bounded Decider UI. |
| [`presentation`](https://github.com/mdrmtz/presentation) | Markdown-authored Astro slide deck for the final capstone presentation video (Assignment 7.1). |
| [`cmu-capstone`](https://github.com/mdrmtz/cmu-capstone) | Umbrella project: links `a11y-fixer`, `dashboard-app`, and `presentation` as real git submodules, hosts the capstone checkpoints and final report, and publishes the docs/chat site. |
| [`wcag-mcp`](https://github.com/mdrmtz/wcag-mcp) | Live WCAG 2.2 knowledge server (MCP) — queried at runtime, never a static cache. |
| [`Hallucinate.io`](https://github.com/mdrmtz/Hallucinate.io) | Deliberately-broken Angular fixture used as the benchmark/target site. |

**Final report & evaluation results:** see the final capstone report in [`cmu-capstone`](https://github.com/mdrmtz/cmu-capstone). **Live docs & project chat:** https://mdrmtz.mintlify.site

### Architecture: Module 1-6 concepts applied

![The A11y Fixer -- Module 1-6 concepts applied](architecture-module-concepts.png)

Every mapping in this diagram is cited directly from the agent's own source
docstrings, cross-referenced against this checkout's `Module-01` through `Module-06`
folders -- not inferred after the fact. Full legend, the concept-to-code table, and
diagram source: [`2-Architecture-Module-1-6-Concepts.md`](2-Architecture-Module-1-6-Concepts.md).
For the pipeline architecture itself (not the course mapping), see
[`agent/1-Architecture-High-Level.md`](agent/1-Architecture-High-Level.md) and
[`agent/ARCHITECTURE.md`](agent/ARCHITECTURE.md).
---

Documentation site for **The A11y Fixer**: an autonomous multi-agent system for WCAG 2.2 AA remediation in Angular Single Page Applications.

**Live site:** https://mdrmtz.mintlify.site

## What's documented

| Section | Pages |
|---|---|
| **Capstone Checkpoints** | Agent Scoping, Agent Design, RAG & Retrieval, Tree-of-Thought, Multi-Agent Architecture |
| **Demos** | Basic RAG Retrieval, Hybrid Retrieval Router |

## MCP servers

| Server | URL | Purpose |
|---|---|---|
| Docs search | `https://mdrmtz.mintlify.site/mcp` | Search and read published pages (no auth) |
| Mintlify admin | `https://mcp.mintlify.com` | Edit content, manage navigation, open PRs |
| WCAG data | `https://wcag-mcp.netlify.app/mcp` | Query WCAG 2.2 criteria, techniques, and glossary |

## AI-assisted writing

```bash
npx skills add https://mintlify.com/docs
```

Agent instructions for this project live in [`AGENTS.md`](./AGENTS.md).

## Development

Install the [Mintlify CLI](https://www.npmjs.com/package/mint) to preview your documentation changes locally. To install, use the following command:

```
npm i -g mint
```

Run the following command at the root of your documentation, where your `docs.json` is located:

```
mint dev
```

View your local preview at `http://localhost:3000`.

## Publishing changes

Install our GitHub app from your [dashboard](https://dashboard.mintlify.com/settings/organization/github-app) to propagate changes from your repo to your deployment. Changes are deployed to production automatically after pushing to the default branch.

## Need help?

### Troubleshooting

- If your dev environment isn't running: Run `mint update` to ensure you have the most recent version of the CLI.
- If a page loads as a 404: Make sure you are running in a folder with a valid `docs.json`.

### Resources
- [Mintlify documentation](https://mintlify.com/docs)
