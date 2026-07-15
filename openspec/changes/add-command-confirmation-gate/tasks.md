## 1. Configuration & command classification

- [ ] 1.1 Define the dangerous-command set configuration file (format + default entries: `rm -rf`, `sudo`, output redirection `>`, `mkfs`, `dd if=`, `chmod -R`, `curl|sh` / `wget|sh`, fork bomb `:(){ :|:& };:`) and a loader that reads it at startup
- [ ] 1.2 Implement `CommandClassifier`: parse compound shell strings (`shlex` split by `;` / `&&` / `||` / `|`), extract the command name of each segment, and regex-scan the raw string for dangerous tokens; return `{needs_confirmation, risk_reason, category}`
- [ ] 1.3 Unit-test `CommandClassifier`: dangerous-token hit, safe command, compound shell (`ls && rm -rf build`), config-driven set change

## 2. SSE event contract (backend + frontend)

- [ ] 2.1 Add `tool:confirmation_required` to the `AgentEventType` enum (`event_types.py`) and ensure wire-name normalization (`tool-confirmation-required`)
- [ ] 2.2 Define the event payload contract: `{toolCallId, command, riskReason, workingDir, options:[allow_once,allow_all,deny]}`
- [ ] 2.3 Mirror the event type + payload interface in `frontend/src/domain/entities/events.ts` (`AgentEventMap` + `SSE_EVENT_TYPES`)

## 3. Pending-approval registry & session allowlist

- [ ] 3.1 Implement `PendingApprovalRegistry`: holds an `asyncio.Future` keyed by `(task_id, tool_call_id)`; `register` / `resolve(decision)` / `remove`; concurrent-safe (`asyncio.Lock`)
- [ ] 3.2 Implement `SessionApprovalStore`: per-session allowlist keyed by command category; `is_allowed(session_id, category)` / `allow(session_id, category)`; concurrent-safe; in-memory only
- [ ] 3.3 Wire both as injectable services in `presentation/dependencies.py`

## 4. ConfirmationMiddleware

- [ ] 4.1 Thread the event emitter into `context.extra["event_emitter"]` at `tool_execute_node.py:53` (alongside the existing `tool_call_id`)
- [ ] 4.2 Implement `ConfirmationMiddleware.process`: for `shell` calls — classify → if `needs_confirmation` and not in `SessionApprovalStore` → register a `Future`, emit `tool:confirmation_required`, `await` it wrapped in `asyncio.wait_for(timeout=300)` → `allow_once` proceeds / `allow_all` adds to store then proceeds / `deny` returns `ToolResult(success=False, error="user_denied")`; timeout returns `error="approval_timeout"`; passthrough for non-`shell` and already-allowed commands
- [ ] 4.3 Add `ConfirmationMiddleware` FIRST in `dependencies.py` pipeline assembly (before `SecurityMiddleware`) so it sits outside `TimeoutMiddleware`
- [ ] 4.4 Unit-test the middleware: blocks dangerous + emits event, passthrough safe, deny returns `user_denied`, `allow_all` populates store, timeout returns `approval_timeout`

## 5. Approvals endpoint

- [ ] 5.1 Add `POST /api/tasks/{task_id}/approvals` route: body `{toolCallId, decision: allow_once|allow_all|deny}` → resolve the matching `Future` via `PendingApprovalRegistry`; return 404 for unknown `toolCallId`; reject late decisions after timeout
- [ ] 5.2 Integration test: dangerous `shell` blocks → POST approval → call resumes and executes → `tool:result` success

## 6. Sub-agent / team coverage

- [ ] 6.1 Refactor `_build_tool_registry` (`agent_loop_runner.py`) to construct sub-agent / team scoped registries with the confirmation-capable pipeline (same as top-level) instead of the default empty `ExecutionPipeline`
- [ ] 6.2 Regression check: team multi-member concurrent `shell` calls still behave under the now-applied `RateLimit` / `Timeout`; if regression, downgrade scoped registry to `Confirmation`-only pipeline and record the decision in design Open Questions
- [ ] 6.3 Test: a sub-agent and a team member calling a dangerous `shell` command trigger the confirmation gate

## 7. Frontend confirmation UI

- [ ] 7.1 Implement `approvalApi.postApproval(taskId, toolCallId, decision)`
- [ ] 7.2 Implement `CommandConfirmCard.tsx` (clone `ClarifyCard` shape): display command + risk reason, three buttons (本次允许 / 全部允许 / 拒绝), controlled `submitted` / `disabled` props, read-only answered state
- [ ] 7.3 Handle `tool:confirmation_required` in `useChat.ts` → push a segment with `toolStatus: 'awaiting_confirmation'`
- [ ] 7.4 Route to `CommandConfirmCard` in `MessageBubble.tsx` (extend the `SPECIAL_TOOL_NAMES`-style routing)
- [ ] 7.5 Frontend test: card renders on event, decision is posted to the endpoint, card becomes read-only after answer

## 8. End-to-end verification

- [ ] 8.1 E2E: LLM calls dangerous `shell` → card appears → allow-once → command runs → `tool:result` success
- [ ] 8.2 E2E: deny → `user_denied` returned to LLM, task continues (not aborted)
- [ ] 8.3 E2E: allow-all → a second command of the same category runs without a prompt
- [ ] 8.4 E2E: no decision for 5 minutes → `approval_timeout`, suspended call freed
- [ ] 8.5 Update design Open Questions with the resolved sub-agent pipeline-injection decision (full vs `Confirmation`-only)
