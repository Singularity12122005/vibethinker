---
name: goal
description: Run one research round of the standing goal archive docs/research/sycophancy-phase0-goal.md (dynamic control of multi-turn sycophancy). Use when the user types /goal, says 继续做下去, or pastes new GPU diagnostics / review memos for the Phase-0 study.
---

# /goal — one research round, user-triggered, never scheduled

The archive `docs/research/sycophancy-phase0-goal.md` holds the claim ladder (C0–C6, C★), the propositions (P1–P6), the routes,
the research record (已证明 / 候选 / 反例与错误 / 已淘汰路线 / 最近的关键缺口 / 下一轮攻击) and one record per round in §9.
A round advances it by real derivation plus runnable checks, then an adversarial review, then an honest record. Nothing runs on
its own: no cron, no wake-ups, no background loops. One invocation = one round.

## Procedure

1. **Read the state**: the archive (§1, §3, §5, §7, §9), `docs/research/sycophancy-phase0-execution-plan.md` §7.11, and
   `sycophancy_phase0/src/sycophancy_phase0/analysis/g6_iv.py`. If the user pasted new measurements or a memo, first fold the
   facts into the plan / RUNBOOK / handoff exactly as earlier rounds did (numbers verbatim, claims only as far as the data supports).
2. **Pick the obstacle**: the user's instruction if given; otherwise the first item of §7 "下一轮攻击". Do not re-run eliminated routes.
3. **Run the round with agents** (the user opted into this): call the Workflow tool with `name: "goal-round"` and
   `args: {round: "r<k>", obstacle: "<one sentence>", python: "<path of the python with numpy/scipy>", scratch: "<scratchpad>/goal_rounds"}`.
   The workflow (`.claude/workflows/goal-round.js`) does: context → ≤3 independent route attacks (derivation + simulation) →
   two-lens refutation of ≤3 claims → synthesis into the archive §7/§9 with pytest cases → label check (+ one repair pass).
   If the Workflow tool is unavailable, run the same five stages with the Agent tool, sequentially, with the same prompts.
4. **Verify yourself**: read the new §9 record and the diff; run the full suite (`pytest -q` in `sycophancy_phase0/`); downgrade any
   label the evidence does not support; a claim is 独立复核 only if both refutation lenses failed to refute it.
5. **Commit and push** on the session's designated branch with the session's commit conventions; then answer in the A–F format:
   A 原始目标 / B 本轮核心障碍 / C 本轮实际推导 / D 严格核查 / E 路线决策 / F 更新研究档案, plus "尚未解决" items stated plainly.

## Rules (from the archive §0)
- Success = a meaningful idea formulation pushed to the strongest claim the evidence allows; "not solved" must be written as such.
- No fabricated proofs, no restating or renaming old results as progress, no silent weakening of the claim.
- Every 已证明 item needs a derivation and a pytest case (CPU simulation or exact arithmetic) or a GPU diagnostic that ran.
- If two consecutive rounds make no real progress, re-examine the problem statement itself before attacking again.
