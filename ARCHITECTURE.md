# A11y Fixer — Capstone Project Architecture

## System Overview

```mermaid
graph LR
    subgraph "💾 Data Input"
        AuditData["audit.json<br/>Violations List"]
    end

    subgraph "🔄 Agent System"
        Orchestrator["🎯 Orchestrator<br/>Route & Decide"]
        Planner["📋 Compliance Planner<br/>WCAG Mapping"]
        Compiler["🔧 Codebase Compiler<br/>Apply & Verify"]
        Critic["⭐ QA Critic<br/>Score 0-20"]
    end

    subgraph "🛠️ MCP Servers"
        WCAG["wcag-mcp"]
        Chrome["chrome-devtools-mcp"]
        AngularCLI["angular-cli-mcp"]
        Docs["docs-langchain"]
    end

    subgraph "✅ Auto Fix Path"
        AutoPR["🚀 GitHub PR<br/>Live or Dry-Run"]
    end

    subgraph "👤 Human Review Path"
        HITLQueue["📋 HITL Queue<br/>Awaiting Review"]
        Dashboard["🎯 Dashboard UI<br/>Approve/Reject"]
    end

    subgraph "✨ Output"
        Delivery["✅ Delivered"]
    end

    AuditData --> Orchestrator

    Orchestrator --> Planner
    Planner --> WCAG
    Planner --> Compiler

    Compiler --> AngularCLI
    Compiler --> Chrome
    Compiler --> Critic

    Critic --> Chrome
    Critic --> Docs
    Planner --> Docs

    Critic --> Orchestrator

    Orchestrator -->|high score| AutoPR
    Orchestrator -->|low score| HITLQueue

    HITLQueue --> Dashboard
    Dashboard --> AutoPR

    AutoPR --> Delivery

    style Orchestrator fill:#3b82f6,stroke:#1e40af,color:#fff
    style Planner fill:#3b82f6,stroke:#1e40af,color:#fff
    style Compiler fill:#3b82f6,stroke:#1e40af,color:#fff
    style Critic fill:#3b82f6,stroke:#1e40af,color:#fff
    
    style HITLQueue fill:#10b981,stroke:#059669,color:#fff
    style Dashboard fill:#10b981,stroke:#059669,color:#fff
    
    style AutoPR fill:#f59e0b,stroke:#d97706,color:#fff
    style Delivery fill:#8b5cf6,stroke:#6d28d9,color:#fff
    
    style WCAG fill:#ec4899,stroke:#be185d,color:#fff
    style Chrome fill:#ec4899,stroke:#be185d,color:#fff
    style AngularCLI fill:#ec4899,stroke:#be185d,color:#fff
    style Docs fill:#ec4899,stroke:#be185d,color:#fff
```

## High-Level Flow

### 1️⃣ **Audit & Discovery**
- GitHub Actions or CLI trigger → scans Angular app with axe-core
- Creates `audit.json` with violation list

### 2️⃣ **User Interface Layer**
Three complementary dashboards:
- **Main Dashboard**: Overview of all violations, filterable by WCAG level
- **HITL Queue**: Violations awaiting human approval
- **Lessons**: Knowledge base from fixed violations

### 3️⃣ **Agent Intelligence**
Four subagents work together:
- **Compliance Planner**: Maps violations to WCAG rules via wcag-mcp
- **Codebase Compiler**: Applies patches, runs tests via angular-cli-mcp
- **QA Critic**: Scores fixes 0-20 using Chrome DevTools analysis
- **Orchestrator**: Routes to auto-fix or human review based on score

### 4️⃣ **External Integrations**
- **WCAG MCP**: Real-time WCAG rule lookups (never training data)
- **Chrome DevTools MCP**: Visual stability & rendering validation
- **Angular CLI MCP**: Build, test, and verify patches
- **LangChain Docs MCP**: Reference documentation for compliance

### 5️⃣ **Delivery**
- **Auto Fix Route**: High-confidence fixes → GitHub PR creation
- **Human Review Route**: Low-confidence fixes → HITL queue for approval

## Key Design Principles

✅ **Multi-Agent Coordination** — 4 subagents + 6 MCP servers work in concert
✅ **Iterative Refinement** — If QA score is low, loop back to Compliance Planner
✅ **Real-Time WCAG** — Never rely on training data; always query wcag-mcp
✅ **Human-in-the-Loop** — Uncertain fixes go to HITL queue for approval
✅ **End-to-End Validation** — Build, test, visual analysis before delivery

## Data Flow

```mermaid
graph TD
    A["audit.json<br/>(violations)"] --> B["Agent System<br/>(4 subagents + 6 MCP servers)"]
    B --> C{High confidence?}
    C -->|Yes| D["GitHub PR<br/>(live or dry-run)"]
    C -->|No| E["HITL Queue<br/>(human review)"]
    E --> F["Dashboard UI<br/>(approval)"]
    F --> D
    D --> G["Delivery<br/>(or rejection)"]
```
