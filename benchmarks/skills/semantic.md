Use compiler-backed SystemVerilog information only where it resolves a fact required by the
question. Treat every tool result as evidence, not as a reason to explore unrelated design areas.

1. Read the requested response contract first. Identify every required field and whether it asks
   for an elaborated path, an effective parameter, a direct actual expression, a resolved symbol,
   a declaration property, or a source-level access.
2. Load the logical project from projects.json once before semantic queries. Do not reload it unless
   the task explicitly depends on RTL changes made during this session. Check diagnostics only when
   compilation state is relevant to the answer or a semantic query fails unexpectedly.
3. Use the narrowest query that proves each field. For generated hierarchy, query the smallest
   relevant root and depth. Do not use unfiltered list_instances when an exact path, name, module,
   or path prefix is known.
4. For an effective parameter, call get_instance_parameters with names. For selected port bindings,
   call get_instance_connections with ports. Do not use inspect_instance, inspect_module, or a
   broad parameter/connection query when one of these targeted queries supplies the requested
   field.
5. Keep connection representations distinct. expression is the complete direct actual expression,
   including selects such as request.address. symbols are the resolved base symbols referenced by
   that expression. Return exactly the representation requested; do not silently substitute one
   for the other.
6. Use trace_connectivity only when the question asks for a bounded route, upstream/downstream
   dependency, or cross-instance propagation. Do not use it for parameter values, hierarchy,
   direct port bindings, declarations, or simple driver/load locations. Use get_drivers or
   get_loads for a direct source-level access question.
7. Reuse a result that already proves a fact. Do not repeat equivalent queries or widen a query
   merely to gain confidence. If a result is truncated, refine its scope first; increase limit only
   when the omitted items can affect the requested answer.
8. Read source for local behavior, comments, naming, and intent, or when compiler-backed evidence
   cannot answer the question. Do not infer netlist, timing, simulation, formal, CDC, or synthesis
   evidence from source-level results.
9. Resolve ambiguity with exact returned identifiers. If the available compiler evidence cannot
   prove the requested fact, say so rather than guessing. Return only the requested answer format.
