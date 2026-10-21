# OpenMontage Agent Fast Router

Read first; scan as needed.

## 1. Context routing

- Explanation, writing, or advice: this file is enough.
- Project development, diagnosis, status, planning, or monitoring: additionally read `docs/handoff/README.md` and `docs/handoff/CURRENT_STATUS.md`.
- Then read at most the relevant topic handoff first:
  - product behavior and invariants: `docs/handoff/PRODUCT_RULES.md`
  - current binding decisions: `docs/handoff/DECISIONS.md`
  - code and test entrypoints: `docs/handoff/CODE_MAP.md`
  - daily technology brief: `docs/handoff/DAILY_TECH_BRIEF.md`
  - GitHub release and cross-machine setup: `docs/handoff/DEPLOYMENT.md`
- Read `PROJECT_CONTEXT.md` for deeper architecture or conventions.
- Old guides/PRDs are historical; current `docs/handoff/` wins conflicts.
- Inspect only task-relevant paths; do not default-scan projects, logs, media, old guides, full Git history or the whole dirty diff.

After material implementation/state/decision/blocker/next-step changes, update the smallest applicable handoff file and run:

`python scripts/audit_context_handoff.py`

Do not update handoff files for ordinary questions, acknowledgements, or repeated status checks. Replace stale conclusions instead of appending chat history.

## 2. Request routing

- 高质量数字人工作流：读 `docs/高质量数字人工作流.md`，优先于通用口播。
- 新建、修改或审查视频模板：先读 `../Haike-Videohub/agent-runbooks/视频模板编写标准.md`，按骨架、类型扩展与验收量表记录当前范围。
- 数字人模板7：`../Haike-Videohub/agent-runbooks/数字人模板7.md`。
- Exact call sign **「模板图文视频」** maps to `../Haike-Videohub/agent-runbooks/模板图文视频.md` before type inference; never substitute another production line.
- 数字人口播模板6／招商A：读 `../Haike-Videohub/agent-runbooks/数字人口播模板6-招商A.md`；模板3读 `skills/INDEX.md`；其他口播读 `../Haike-Videohub/agent-runbooks/数字人口播视频.md`。
- Agent 制片（含模糊指令）或续做：读 `docs/CODEX_VIDEO_BATCH.md`；新任务用账号预设、明确参数优先，旧任务复用冻结规格与回执。
- 素材解说/电影解说/直播切片解说：读 `../Haike-Videohub/agent-runbooks/素材解说视频.md`；素材决定结构，走统一队列。
- Video analysis: read `../Haike-Videohub/agent-runbooks/视频快速理解与分层分析.md`; start with local overview, deepen by goal. Analysis does not authorize production.
- Answer, explain, review, or report status: inspect read-only evidence and respond. Do not mutate external state.
- Diagnose: identify the cause and evidence. Implement only when the user asks for a fix or the request clearly includes one.
- Change or build: implement, verify in proportion to risk, fix discovered in-scope defects, and report the outcome.
- Monitor or wait: follow the existing producer and task state. Unchanged state is not an error.
- If a choice would materially change scope, cost, external effects, or product behavior and cannot be inferred safely, stop and ask.

## 3. Video-production contract

Actual production uses OpenMontage and its manifests, except compatibility workflows registered in `skills/INDEX.md`; Codex must not become an undocumented producer. **「模板图文视频」** is the sole current exception: follow its runbook and complete project-manifest/workbench gates until a formal adapter replaces it.

Before a production run:

1. Resolve an exact call sign first, then the project and pipeline/manifest; record the workflow before production.
2. Perform capability and configuration preflight.
   For media-provider choices, use the registry's compact `provider_menu_summary()` first; do not dump the raw support envelope into the task.
3. Read the relevant installed provider/stage skill before invoking that stage.
4. Present or persist provider, model or instance, cost guardrail, aspect ratio, music choice, and review gates.
5. Use idempotent job identifiers and durable state so retries do not duplicate paid work.
6. Submit supported parent production through the unified queue (`python -m backlot queue submit ...` or `/api/production-queue/jobs`). Do not call the registered review-preview or full-preview runners directly; the queue is the cross-project execution authority.

Stages: source/script, audio, avatar, media, composition, captions/music, QA and review. Audio duration is the master clock; visuals follow it. Never stretch speech to fit a slot.

Every used asset must have provenance and a stable ID. Avatar media and main visual media are separate layers: an avatar does not mean a scene has a main visual. Locked or frozen slots must not be overwritten by batch operations. Local replacement must not invalidate unrelated segments.

Preview and final render must share the same timeline, subtitle, avatar geometry, crop, and asset contract. Formal publication requires explicit user authorization for the current accounts, content scope and budget. An authorized agent batch may complete quality checks and publish within that scope without repeated confirmations; otherwise stop at a review-ready preview.

## 4. Providers, cost, and failures

- State the exact provider and model/instance before a paid or materially expensive call. Never silently substitute providers or models.
- If several eligible providers exist, follow the project/user selection. If none is explicit, surface the supported choices instead of guessing a costly route.
- New RunningHub production defaults to paid-accepted workflow `2094449979141218305` with profile `infinitetalk_448x560_exact_clock_v2` on Plus 48GB (`instanceType=plus`). For a two-presenter parent job, persist both task IDs before polling so the two provider jobs run concurrently; the global parent-video queue remains single-lane. The final PCM16 mono WAV is aligned once to the 25FPS frame clock and its exact frame count is submitted to node 35. Frozen legacy Standard/Lite jobs keep their recorded instance and sequencing contract.
- Enforce project and daily budgets before submission. A paid operation must be recoverable and auditable.
- Failures must preserve completed artifacts and record: stage, provider, error class, retryability, safe resume point, and user-facing Chinese remediation.
- All user-facing UI messages are Chinese; map raw backend errors to actionable Chinese descriptions.

For daily technology brief rules, always use `docs/handoff/DAILY_TECH_BRIEF.md`. Do not revive old fixed `4n+2` or “every news item has four lines” assumptions.

## 5. Quality gates

- Validate schemas and state transitions before running media tools.
- Use at most two independent review passes unless the user explicitly requests more: one structural/semantic pass and one visual/output pass.
- Verify outputs with appropriate evidence: tests, ffprobe/media streams, dimensions, duration, representative frames, subtitles, audio mix, and persisted task status.
- A generated artifact is not complete until it is visible through the intended frontend flow or clearly handed off as a test artifact.
- Preserve completed paid artifacts during retries. Never restart the whole pipeline to fix one local slot.

## 6. Repository work

- Search with `rg` or `rg --files` first.
- Use `apply_patch` for source and documentation edits. Formatting and generated bulk artifacts may use their native tools.
- The worktree may contain user changes. Inspect the relevant diff and preserve unrelated work.
- Do not use destructive Git or filesystem operations unless the user explicitly requests them and the exact target is verified.
- Never expose secrets in logs, UI, tests, or responses. Store credentials only in the repository's ignored local-secret mechanism; redact values from evidence.
- Prefer small, reversible changes and focused tests, then run broader tests when the change crosses contracts.

## 7. Skills and communication

- If the user names a skill, or the task clearly matches an available skill, read its `SKILL.md` completely and follow it.
- Resolve Chinese production call signs through `skills/INDEX.md` before loading a pipeline. Distinguish the two 「复刻」 lines by supplied input; ask only when ambiguous.
- **「模板图文视频」 is exact:** load its runbook first and require its 9-second/3-scene gate.
- Use `skills/INDEX.md` for pipeline, runtime, music and taste guidance.
- For repeated operator tasks such as three-platform publication, start at `../Haike-Videohub/agent-runbooks/README.md`; verify live account and task state before following a recorded procedure.
- Propose new evidence and recovery steps through Videohub governance; edit shared runbooks only with explicit maintenance assignment.
- Announce skill use and any skill-caused action or pause in commentary.
- When tools are needed, send a concise commentary update first and keep the user informed during long work.
- Final responses lead with the outcome, name material files with clickable absolute paths, state what was tested, and call out only genuine remaining risks.

## 8. Authoritative detail sources

- Lightweight current state and routing: `docs/handoff/`
- Architecture and repository conventions: `PROJECT_CONTEXT.md`
- Pipeline manifests and provider capabilities: `config/pipelines/`, `config/providers/`, `config/capability_matrix.yaml`
- Product requirements and historical rationale: `docs/PRD*` and `docs/TASK_GUIDE_*` (historical unless promoted into handoff)
- Project evidence and job state: the selected project directory and `.backlot/` files relevant to that task only

Repair missing, stale, contradictory or over-budget handoff files before relying on historical context.
