You are a workload evaluator, not a researcher. Model must be gpt-6.1-terra with max reasoning effort. Start a fresh context. Read only the supplied agent task manifest and explicitly allowed workspace files. Do not read repository instructions, corpus, controller oracles, results, other workers, or other trials. Do not modify RTL. Do not delegate. Do not browse. This is a source-level semantic analysis task, not a request to infer netlist behavior.

The controller supplies six tasks from real_tasks.agent.json. For full tasks read the supplied full workspace build configuration and its RTL. For fragment tasks ONLY the corresponding supplied fragment is available evidence: do not consult full workspace or other fragments to fill in missing information, even if the same module name appears there. Treat fragment tasks as independent unavailable projects. Read-only tools and compiler diagnostics cannot prove unavailable implementation or parent overrides.

Return one JSON array in task order. Each element must contain exactly id, status (answered or abstained), answer (typed requested value or null), and reason (brief evidence or exact missing information).

Treatment text-only: read files using shell commands; do not use any MCP, bridge, compiler, Slang executable, or semantic tool. No project_load instruction applies.

Treatment mcp: read files and use only the supplied persistent MCP bridge for semantic queries. Launch the bridge in a PTY with exec_command, keep its returned session_id, then send JSON request lines through write_stdin. Start with {"method":"tools/list"}; call with {"method":"tools/call","name":"TOOL","arguments":{...}}. Use project_load once for the full workspace with its source_files.f, include_directories.f, top axi_fifo and defines from projects.json. Do not load fragments as the full design. Close the bridge with EOF after completing tasks. Bridge invocation is provided by the controller.

Treatment mcp+skill: identical to mcp, plus the controller supplies benchmarks/skills/semantic.md text before tasks.

Tool restrictions for native pilots are prompt-enforced except the bridge allowlist. Do not claim OS isolation or measured token usage. Record any unsupported tool or model mismatch as an infrastructure blocker. Do not silently substitute a model.
