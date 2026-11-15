Use compiler-backed SystemVerilog information only where it resolves a fact required by the
question. Treat every tool result as evidence, not as a reason to explore unrelated design areas.

Start with the task and relevant source. Read RTL, included headers and macro definitions to
understand expressions, branch conditions and intent. Use MCP when a required conclusion needs
compiler evidence about resolved types, effective parameters, hierarchy, accesses or diagnostics.
Do not alternate source and MCP calls by habit or repeat a fact that is already adequately supported.
An answer supported by the supplied source does not require a confirmation call solely because MCP
is available.
For macro-heavy code, verify defines, include directories, source order and single_unit before
interpreting results. A macro definition visible in the repository is not necessarily active in
the loaded fragment. Source-level references alone do not prove that a procedural branch executes.

1. Read the requested response contract first. Identify every required field and whether it asks
   for an elaborated path, an effective parameter, a direct actual expression, a resolved symbol,
   a declaration property, or a source-level access.
2. Read source_files.f as an ordered inventory and choose the smallest relevant source set plus
   dependencies. Call project_load with actual absolute source_files paths in inventory order,
   actual include_directories from include_directories.f, and defines from projects.json. Choose
   the relevant top_module, using top_module.txt when the requested fact needs the supplied project
   top. Add missing dependencies with another project_load when needed. single_unit defaults to
   true; use false only when separate compilation units are required. Inspect diagnostics when
   compilation state is relevant or a semantic query fails unexpectedly. A standalone top uses its
   defaults; load its parent context when the answer requires parent instance overrides. When
   comparing compilation configurations, collect the needed facts for one configuration before
   loading the next; retain those observations instead of repeatedly switching back and forth.
3. Use the narrowest query that proves each field. For hierarchy, pass the exact elaborated
   instance or generate-block path as get_hierarchy.root and the smallest relevant max_depth; a
   root is not limited to a top instance. Do not use unfiltered list_instances when an exact path,
   name, module, or path prefix is known.
4. For an effective parameter on one instance, call inspect_instance with fields=["parameters"]
   and parameter_names. For an inventory of instances of the same module type, call
   list_instance_facts instead of one parameter query per instance. To request only selected
   parameters, set parameter_names to those names and port_names=[]. To request only selected
   connections, set port_names to those names and parameter_names=[]. Omitted name filters return
   all facts in that section; [] selects none. This bulk tool does not accept fields, and empty
   sections still have page metadata. For selected port bindings on one
   instance, call inspect_instance with fields=["connections"] and port_names. For module defaults,
   use inspect_module with the relevant fields and exact parameter_names or port_names. Select only
   the sections needed to answer the question.
5. Keep connection representations distinct. expression is the complete direct actual expression,
   including selects such as request.address. symbols are the resolved base symbols referenced by
   that expression. Return exactly the representation requested; do not silently substitute one
   for the other.
6. For source-level reads or writes, use get_references with the exact symbol and kind="read"
   or kind="write". Both filters include read_write accesses. These results describe source-level
   accesses rather than netlist connectivity. Use get_state_elements for signals written in
   always_ff; do not infer reset or synthesis behavior from that classification.
7. Reuse a result that already proves a fact. Do not repeat equivalent queries or widen a query
   merely to gain confidence. If a result is truncated, refine its scope first; increase limit only
   when the omitted items can affect the requested answer.
8. Read source for local behavior, comments, naming, and intent, or when compiler-backed evidence
   cannot answer the question. Do not infer netlist, timing, simulation, formal, CDC, or synthesis
   evidence from source-level results.
9. Resolve ambiguity with symbol_id returned by find_symbol or a previous result. A qualified path
   can still be ambiguous across symbol kinds; do not guess a kind or silently choose a candidate.
   If the available evidence cannot prove the requested fact, say so rather than guessing. Stop
   querying when the requested conclusions and their limits are supported. Return only the
   requested answer format.
