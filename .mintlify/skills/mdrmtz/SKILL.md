---
name: mdrmtz
description: Use when working with The A11y Fixer — an autonomous multi-agent system for WCAG 2.2 AA remediation in Angular SPAs. Covers agent architecture, Hybrid RAG retrieval, Tree-of-Thought search, LangGraph multi-agent coordination, and accessibility engineering.
---

# The A11y Fixer

Autonomous WCAG 2.2 AA remediation agent for Angular Single Page Applications. Takes `axe-core` audit violations as input and delivers verified, regression-free Pull Requests as output via a three-agent LangGraph pipeline.

**Live docs:** https://mdrmtz.mintlify.site  
**Docs MCP:** https://mdrmtz.mintlify.site/mcp (tools: `search_the_a11y_fixer`, `query_docs_filesystem_the_a11y_fixer`, `submit_feedback`)

## Agents

| Agent | Role | Key Output |
|---|---|---|
| **Compliance Planner** | Retrieves WCAG clauses via Hybrid RAG (LLM Wiki + MMR Stateless Semantic Search) | Structured compliance manifest |
| **Codebase Compiler** | Applies Tree-of-Thought AST patches (k=3 branches, depth T=3) using Tree-sitter | Candidate diffs on isolated Git branches |
| **QA Critic** | Scores each patch 0–20 (Compile Safety 8pts, AST Validity 4pts, WCAG Compliance 5pts, Layout Stability 3pts) | Approve PR or trigger adaptive backtrack |

## Tools & Integrations

| Tool | Purpose |
|---|---|
| `axe-core` | Accessibility audit engine — produces the violation JSON the system consumes |
| Chrome DevTools MCP | Live browser inspection — computed accessibility tree, contrast ratios, console errors |
| Angular Ivy compiler | Compilation target for every patch candidate |
| Tree-sitter | AST parsing and non-destructive code modification |
| LangGraph | Directed stateful pipeline with conditional edges for backtracking |
| Git transactional sandbox | Each ToT branch runs in `git checkout -f && git clean -fd` isolation |

## Retrieval Architecture

Two-pathway Hybrid RAG:
- **LLM Wiki (Pathway B):** Deterministic hash-key lookup for known `axe-core` error codes (`button-name`, `color-contrast`, `bypass`). Zero vector search, zero hallucination risk.
- **Stateless Semantic Search (Pathway A):** MMR-reranked vector search (λ=0.5, k=3) for exploratory queries. Identical queries always return identical chunks.

## Tree-of-Thought Search

- **Algorithm:** DFS — O(T) workspace footprint vs O(bᵀ) for BFS
- **Branching factor:** k=3 (inflates to k=5 on branch exhaustion via Adaptive Sibling Inflation)
- **Depth limit:** T=3 (HTML ARIA injection → TypeScript property → CSS encapsulation)
- **Global circuit-breaker:** 15 node evaluations per session
- **Backtrack trigger:** composite score ≤5 or Angular Ivy compile failure

## Docs Structure

```
/index.mdx                                     ← overview + architecture table
/quickstart.mdx                                ← 3-step flow + scoring rubric
/checkpoints/checkpoint-1-agent-scoping.mdx    ← problem, environment, ReAct loop
/checkpoints/checkpoint-2-agent-design.mdx     ← dual memory, tool integration
/checkpoints/checkpoint-3-rag-retrieval.mdx    ← Hybrid RAG design
/checkpoints/checkpoint-4-tree-of-thought.mdx  ← ToT DFS, rubric, evaluator roles
/checkpoints/checkpoint-5-multi-agent-architecture.mdx ← LangGraph, A2A schema
/demos/rag-basic-retrieval.mdx                 ← cosine similarity RAG (Ollama)
/demos/rag-hybrid-retrieval.mdx                ← LLM Wiki + MMR router (full source)
```

## How to Query the Docs MCP

```bash
# Search by topic
{"method":"tools/call","params":{"name":"search_the_a11y_fixer","arguments":{"query":"Tree-of-Thought DFS"}}}

# Read a full page
{"method":"tools/call","params":{"name":"query_docs_filesystem_the_a11y_fixer","arguments":{"command":"cat /checkpoints/checkpoint-4-tree-of-thought.mdx"}}}

# Find all mentions of a keyword
{"method":"tools/call","params":{"name":"query_docs_filesystem_the_a11y_fixer","arguments":{"command":"rg -il \"LangGraph\" /"}}}
```
