---
name: a11y-fixer-docs
description: Search and retrieve content from The A11y Fixer documentation site. Use when answering questions about the capstone project architecture, agent roles, RAG design, Tree-of-Thought implementation, multi-agent coordination, or any content in the checkpoints and demos.
---

# The A11y Fixer Docs MCP

Provides access to the `cmu-capstone-docs` MCP server (`https://mdrmtz.mintlify.site/mcp`) — 3 tools covering all 9 published pages of The A11y Fixer capstone documentation.

## When to Call Which Tool

| Situation | Tool | Example command |
|---|---|---|
| Find pages relevant to a topic | `search_the_a11y_fixer` | `query: "Tree-of-Thought DFS"` |
| Read a full page by path | `query_docs_filesystem_the_a11y_fixer` | `cat /checkpoints/checkpoint-4-tree-of-thought.mdx` |
| Browse the site structure | `query_docs_filesystem_the_a11y_fixer` | `tree / -L 2` |
| Find all mentions of a keyword | `query_docs_filesystem_the_a11y_fixer` | `rg -il "LangGraph" /` |
| Read multiple pages at once | `query_docs_filesystem_the_a11y_fixer` | `head -80 /index.mdx /quickstart.mdx` |
| Read a section, not a full page | `query_docs_filesystem_the_a11y_fixer` | `rg -C 5 "MMR" /checkpoints/checkpoint-3-rag-retrieval.mdx` |
| Report a doc error | `submit_feedback` | `path: "/checkpoints/checkpoint-3-rag-retrieval", feedback: "..."` |

## Site Structure

```
/index.mdx                                        ← project overview, architecture table
/quickstart.mdx                                   ← 3-step flow + scoring rubric
/checkpoints/checkpoint-1-agent-scoping.mdx       ← problem, environment, ReAct actions
/checkpoints/checkpoint-2-agent-design.mdx        ← ReAct loop, dual memory, tools
/checkpoints/checkpoint-3-rag-retrieval.mdx       ← Hybrid RAG: LLM Wiki + MMR
/checkpoints/checkpoint-4-tree-of-thought.mdx     ← ToT DFS, adaptive inflation, 0-20 rubric
/checkpoints/checkpoint-5-multi-agent-architecture.mdx ← LangGraph, A2A schema, 3 agents
/demos/rag-basic-retrieval.mdx                    ← basic cosine similarity RAG (Ollama)
/demos/rag-hybrid-retrieval.mdx                   ← LLM Wiki + MMR router (full source)
```

## Workflow

**For broad questions** (e.g. "how does the agent fix accessibility violations?"):
1. `search_the_a11y_fixer` with the topic → get relevant page links
2. `query_docs_filesystem_the_a11y_fixer` with `cat <path>.mdx` on the most relevant result

**For precise lookups** (e.g. "what is the exact MMR lambda value?"):
1. `query_docs_filesystem_the_a11y_fixer` with `rg -C 3 "lambda" /checkpoints/checkpoint-3-rag-retrieval.mdx`

**For structural exploration**:
1. `query_docs_filesystem_the_a11y_fixer` with `tree / -L 2` first, then `cat` target files

## Key Terms (use these as search queries)

`axe-core`, `LLM Wiki`, `Stateless Semantic Search`, `MMR`, `Tree-of-Thought`, `DFS`, `LangGraph`, `Compliance Planner`, `Codebase Compiler`, `QA Critic`, `Angular Ivy`, `AST`, `WCAG 2.2 AA`, `HyDE`, `adaptive sibling inflation`, `contrastive backpropagation`

## Notes

- The filesystem tool is **stateless** — `cd` in one call does not carry over to the next; use absolute paths
- Output is truncated at 30KB per call — prefer `head -N` or `rg -C` over `cat` on large files
- Append `.mdx` to page paths when using filesystem commands (e.g. `/quickstart.mdx` not `/quickstart`)
- When citing pages in responses, strip `.mdx` → `/quickstart` becomes `https://mdrmtz.mintlify.site/quickstart`
