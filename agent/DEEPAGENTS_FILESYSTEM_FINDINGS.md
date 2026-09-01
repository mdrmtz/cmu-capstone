# DeepAgents FilesystemMiddleware Findings

## Key Insights from deepagents-sandboxes.ipynb

### 1. **Sandbox Backend Provides Built-in Filesystem Tools**
When configuring an agent with a sandbox backend, it **automatically** provides:
```python
agent = create_deep_agent(
    model=model,
    backend=sandbox,
    system_prompt=analyst_prompt
)
```

This automatically includes:
- **Filesystem tools**: `ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep`
- **Execute tool**: for running arbitrary shell commands in the sandbox
- **Security boundary**: protects the host system

### 2. **FilesystemMiddleware is Internal**
The notebook does NOT explicitly instantiate `FilesystemMiddleware`. Instead:
- `create_deep_agent()` with `backend=sandbox` handles filesystem middleware internally
- The middleware is created by the framework, not manually

### 3. **For Manual SubAgent Creation (like in codebase_compiler.py)**
Since `codebase_compiler.py` manually creates a `SubAgent()`, it MUST:
1. Explicitly add `FilesystemMiddleware` 
2. Supply the actual file tools to the middleware (not just names)
3. Ensure proper tool configuration

### 4. **Tool Initialization Pattern**
From the sandbox notebook, the agent workflow shows:
```
🔧 **read_file**({'file_path': '/work/sales.csv', 'limit': 50})
🔧 **write_file**('/work/analyze.py')
🔧 **execute**(f"cd /work && python analyze.py")
```

These are actual **Tool** objects, not string names.

### 5. **What's Missing in codebase_compiler.py**
The likely issue is that `FilesystemMiddleware` needs:
- Actual tool objects/instances, not just string names like `"read_file"`
- Proper initialization of each tool with required parameters
- The tools need to be callable and properly configured for the virtual path system

## Implementation Notes

### For SubAgent-based Middleware:
```python
from langchain_core.tools import Tool

# FilesystemMiddleware expects actual Tool objects
filesystem_tools = {
    "read_file": Tool(...),  # actual Tool instance
    "write_file": Tool(...), 
    "edit_file": Tool(...),
    # etc.
}

middleware = FilesystemMiddleware(tools=filesystem_tools)
```

### Key Differences:
| Approach | How FilesystemMiddleware is Set Up |
|----------|-----------------------------------|
| `create_deep_agent(backend=sandbox)` | Framework handles it automatically |
| Manual `SubAgent` creation | Must manually create and add middleware |

## References
- Source: `deepagents-sandboxes.ipynb` from langchain-samples/deepagents-deep-dive
- Shows real-world usage of sandbox backends
- Demonstrates that filesystem tools are provided by backend, not by middleware alone
