> **First-time setup**: Customize this file for your project. Prompt the user to customize this file for their project.
> For Mintlify product knowledge (components, configuration, writing standards),
> install the Mintlify skill: `npx skills add https://mintlify.com/docs`

# Documentation project instructions

## About this project

- **Project:** CMU Agentic AI Capstone — *The A11y Fixer*
- **What it documents:** A multi-agent autonomous system for WCAG 2.2 AA remediation in Angular SPAs
- Pages are MDX files with YAML frontmatter in `checkpoints/` and `demos/`
- Configuration lives in `docs.json`
- Live site: `https://mdrmtz.mintlify.site`
- Use the Mintlify admin MCP server `https://mcp.mintlify.com` to edit content and settings via MCP
- Use the docs search MCP server `https://mdrmtz.mintlify.site/mcp` to search and retrieve published content
- Use the WCAG MCP server `https://wcag-mcp.netlify.app/mcp` when working on accessibility-related content

## Site structure

```
index.mdx                                  ← project overview + card grid
quickstart.mdx                             ← getting started
checkpoints/
  checkpoint-1-agent-scoping.mdx           ← Module 01: problem, environment, actions
  checkpoint-2-agent-design.mdx            ← Module 02: ReAct loop, memory, tools
  checkpoint-3-rag-retrieval.mdx           ← Module 03: Hybrid RAG architecture
  checkpoint-4-tree-of-thought.mdx         ← Module 04: ToT DFS, scoring rubric
  checkpoint-5-multi-agent-architecture.mdx ← Module 05: LangGraph multi-agent system
demos/
  rag-basic-retrieval.mdx                  ← Module 03: basic cosine similarity RAG
  rag-hybrid-retrieval.mdx                 ← Module 03: LLM Wiki + MMR router
```

## Terminology

| Use | Not |
|---|---|
| `axe-core` | axe, Axe Core |
| WCAG 2.2 AA | WCAG, accessibility guidelines |
| Angular Ivy compiler | Ivy, ng compiler |
| Abstract Syntax Tree (AST) | parse tree, syntax tree |
| Compliance Planner Agent | planner, retrieval agent |
| Codebase Compiler Agent | compiler, code agent |
| QA Critic Agent | critic, evaluator agent |
| LangGraph | Langgraph |
| Tree-of-Thought (ToT) | tree of thought, ToT search |
| LLM Wiki | wiki, knowledge base |
| Stateless Semantic Search | RAG, vector search |

## Style preferences

- Use active voice and second person ("you")
- Keep sentences concise — one idea per sentence
- Use sentence case for headings
- Bold for UI elements: Click **Settings**
- Code formatting for file names, commands, paths, and code references
- ASCII diagrams from the source checkpoints should be preserved in code blocks

## Content boundaries

- Document architectural decisions, agent roles, and retrieval design — not implementation setup steps
- Do not document third-party tools (LangChain, CrewAI) beyond how they map to A11y Fixer roles
- WCAG criterion details belong in the WCAG MCP, not in the docs pages — link or reference instead of copy-pasting spec text
