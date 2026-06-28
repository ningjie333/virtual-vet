# Agent Guide

Project-level instructions for automated coding agents working in this repo.
Keep this file concise; use linked docs for full rationale.

## Architecture

- Treat `README.md` and `docs/architecture.md` as the current source of truth.
- See `docs/architecture-improvement-plan.md` for known tech debt and prioritized fixes.
- The physiology kernel is the core product.
- `src/` owns kernel and clinical interpretation code.
- `game/`, `gui_app.py`, and `vet-game-frontend/` are outer application layers.
- Allowed dependency direction: app/game -> interpretation -> kernel.
- Do not introduce imports from `src/` back into `game/`, `gui_app.py`, Flask, or frontend code.
- Gameplay pacing must not redefine kernel time, solver meaning, or disease rates.
- Prefer `GameRuntime` seams for app-layer tests and workflows.

## Session And API Rules

- Any endpoint that reads or writes session-owned state must use the session lock.
- Treat a session without a lock as invalid, even if `_game_sessions` still has state.
- State-changing endpoints include `examine`, `administer-drug`, `diagnose`, and `wait`.
- Snapshot/read endpoints such as `game-state`, `hint`, and `diagnosis` should also lock.
- Frontend GET calls must pass parameters in the query string, never in a request body.
- Query values from the frontend should use `encodeURIComponent`.
- Keep API contract checks in `tools/dev/check_api_consistency.py` current when adding endpoint patterns.

## Testing

- Quick gate before committing:
  `python tools/dev/gate_check.py --quick`
- **Workflow closure gate (复查阶段强制，防首尾不对应)**:
  `python tools/dev/gate_check.py --closure`
- Core app/runtime/API confidence:
  `python -m pytest --channel core -q`
- Frontend type check:
  `.\node_modules\.bin\vue-tsc.cmd -b` from `vet-game-frontend/vite-project`
- For narrow API work, also run targeted interface tests:
  `python -m pytest tests/test_interface.py -q`
- Use heavy, benchmark, or research channels only when touching solver, disease endurance, long-horizon numerics, or performance behavior.
- App-layer tests should use fake runtime/advancer seams unless real physiological progression is the assertion.

## Frontend

- The frontend has its own local guide at `vet-game-frontend/vite-project/AGENTS.md`.
- Use existing Vue/Vite+ patterns; do not replace the toolchain.
- Do not rely on generated `static/index.html` or hashed assets as source changes unless explicitly publishing a build.

## Data And Generated Files

- Do not commit failed experiment outputs, traceback-filled JSON, local caches, or generated dependency folders.
- Be careful with experiment JSON files; large numeric diffs should be intentional and explained.
- `static/` is ignored except tracked legacy files; avoid committing only an HTML hash update without assets.
- External reference folders such as `Medicina-main/`, `Bioflow_Labs_Platform-main/`, and `cvs-reference/` are not normal project code.

## Git Hygiene

- The worktree may contain user changes; never revert unrelated edits.
- Keep commits focused by concern.
- Use non-interactive git commands.
- Do not use destructive commands such as `git reset --hard` or `git checkout --` unless explicitly asked.

## When Unsure

- Prefer small, conservative changes that preserve the kernel/app boundary.
- Add or update tests for new invariants.
- If a rule seems wrong, update the authoritative docs and this guide together.

## Workflow Closure (工作流闭环)

三阶段闭环：推进 → 修复 → 复查。每阶段有入口/出口标准，禁止跳过。目标是消除"声明完成但实际遗漏"（首尾不对应）。

### Stage 1: 推进 (Decide What)

- **入口**：用户明确范围（深度/层级），或 agent 提议范围并经用户确认。
- **出口**：用 TodoWrite 列出所有子任务 + 每项的预期验证标准。
- **禁止**：未列 Todo 就开始改代码。

### Stage 2: 修复 (Execute)

- **入口**：每个子任务有明确完成标准。
- **出口**：每完成一项立即 mark completed（不批量累积）。
- **规则**：
  - 改动前先 Read 理解现有代码，不凭记忆改。
  - 任何"统一/替换"操作后，必须用 Grep 独立验证残留（不信任 Edit `replace_all` 报告）。
  - 前后端字段改动后，必须跑 `python tools/dev/check_api_consistency.py --dry-run` 对照 AST 提取的真实字段。
  - 锁/临界区改动必须确认：临界区内无外部函数调用（或 try/except 回滚）；锁获取顺序无嵌套。
  - 新增 public API 必须附至少 1 个非测试调用点的 Grep 证据；新增配置字段必须在 `data/` 中有至少 1 个使用案例。

### Stage 3: 复查 (Verify)

- **入口**：所有 Todo 已 completed。
- **出口**：跑 `python tools/dev/gate_check.py --closure` 通过。
- **强制项**（工具自动检测）：
  - 字段契约：`check_api_consistency.py --dry-run` 的 Summary 行 `+N 真实字段` 必须为 0。
  - 错误消息统一：`gui_app.py` 中 `jsonify({"error": "..."})` 的静态字面量必须走 `*_MSG` 常量。
- **人工确认项**（无工具，靠清单）：
  - 同类错误消息是否全部走同一常量（Grep 验证）。
  - 新增 public 方法是否有调用点（Grep 验证）。
  - 锁临界区是否在异常路径留下半写字典（人工审查）。
- **禁止**：未跑 `--closure` 就声明"完成"或"已修复"。

### Anti-patterns (已踩过的坑)

- ❌ 信任 Edit `replace_all` 报告"成功" → ✅ Grep 独立验证残留。
- ❌ 人工记忆字段名构建 frontend interface → ✅ AST `--dry-run` 提取真实字段为真理之源。
- ❌ "先创建锁再写字典" → ✅ 模块级短临界区包住 "create_lock + populate dicts"。
- ❌ 临界区内调外部函数（可能抛异常留半写） → ✅ 临界区外预构造对象。
- ❌ 声明"已完成"但未跑工具 → ✅ `--closure` 通过才算闭环。
- ❌ 新增 API 无调用点（死代码） → ✅ PR 附 Grep 调用点证据。
- ❌ 同一概念多个名字（`disease`/`disease_name`/`diagnosis`） → ✅ 查 `docs/naming-conventions.md`（待建）统一。
