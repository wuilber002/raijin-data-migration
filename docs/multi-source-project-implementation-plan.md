# Multi-source project implementation plan

## Scope contract

- **Source** owns credentials, source/destination endpoints, inventory, discovery,
  waves, restore requests and object-level recovery checkpoints.
- **Project** owns aggregate delivery, restore admission allocation, planning
  buffer, risk, cost, closure and operator-facing audit.
- **Runtime** owns the physical transfer lane, host protection, Raiju capacity,
  aggregate throughput and fairness between projects.

## Delivery checklist

- [x] P1. Replace source-owned Raiju control memory with one durable runtime
  controller and global aggregate measurements.
- [x] P2. Add durable project restore-admission state; enforce a global budget
  with fair project allocation and explain each admission decision.
- [x] P3. Use hierarchical capacity evidence: runtime first, then project, then
  source/connection calibration; retain source-local checkpoints.
- [x] P4. Emit project context for all source/wave events and deduplicate stable
  capacity-guard events.
- [x] P5. Expose project/runtime/source scope explicitly through API and UI, with
  project aggregate diagnostics and source drill-down.
- [x] P6. Add deterministic contract tests for concurrent multi-source admission,
  restart persistence, fairness, cold-start planning and scoped observability.
- [x] P7. Validate schema migration, unit/contract tests, a live multi-source
  pre-production scenario and the VM deployment before marking complete.

## Completion rule

No checklist item is marked complete until its implementation, automated proof
and operational contract are present. A final audit reruns every proof and
reopens any item with a divergence.
