---
name: goal
description: Run one research round of the standing goal archive docs/research/sycophancy-phase0-goal.md (dynamic control of multi-turn sycophancy). Use when the user types /goal, says 继续做下去, or pastes new GPU diagnostics, review memos or an archive produced elsewhere for the Phase-0 study.
---

# /goal — one research round, user-triggered, never scheduled

The archive `docs/research/sycophancy-phase0-goal.md` holds the claim ladder (C0–C6, C★), the propositions (P1–P6, A1, CE-B1, …),
the routes, the research record (已证明 / 候选 / 反例与错误 / 已淘汰路线 / 最近的关键缺口 / 下一轮攻击) and one record per round
in §9. A round advances it by real derivation plus runnable checks, then an adversarial review, then an honest record. Nothing runs
on its own: no cron, no wake-ups, no background loops. One invocation = one round.

## Procedure

1. **Read the state**: the archive (§1, §3, §5, §7, §9), `docs/research/sycophancy-phase0-execution-plan.md` §7.11, and
   `sycophancy_phase0/src/sycophancy_phase0/analysis/g6_iv.py`. If the user pasted new measurements or a memo, first fold the facts
   into the plan / RUNBOOK / handoff exactly as earlier rounds did (numbers verbatim, claims only as far as the data supports).
2. **If the user pasted an archive produced in another environment** (an executor's round): do not adopt its claims on trust.
   Re-implement each new claim's computation independently from the statement alone (exact arithmetic where it claims exactness),
   record the replication in a new §9 subsection, adopt the text only after that, and re-create its referenced tests in this repo as
   your own implementation. Say explicitly which code from the other environment did not reach this branch.
3. **Pick the obstacle**: the user's instruction if given; otherwise the first item of §7 "下一轮攻击". Do not re-run eliminated routes.
4. **Run the round by the protocol** `.claude/skills/goal/round-protocol.md` (v5.1; its §7–§9 revisions override §1–§6; the
   user opted into agents): with the Workflow tool, call `name: "goal-round"` with `args: {round: "r<k>", obstacle: "<the
   template's one-sentence form>", root: "<repo root>", python: "<python with numpy/scipy>", scratch: "<absolute scratch
   dir>/goal_rounds"}` (absolute, normalised paths without blanks; scratch outside the repository). The workflow: measures the
   working-tree and test baseline with `round_gate.py` → problem critique filling the obstacle template → ≤3 independent route
   attacks, each returning at most 6 ATOMIC claims (one proposition each, consequence as a separate note, every number with a
   finished source and environment) → a full ledger (reviewed / overflow / author-refuted / excluded / dropped, slots
   round-robin by route) → truth review by the mathematics lens and a blind replication whose isolation audit is mechanical,
   plus an applicability lens that only writes the applicability note → up to `fix_rounds` rewrites strictly from the truth
   lenses' fix texts (checked field by field by the script), one re-run of process failures, and the code-fact route with backup
   and revert → evidence copied, frozen and its ledger re-checked by `round_gate.py` → record, §7, tests, `evidence.json` →
   an audit gate whose mechanical part is `round_gate.py` and whose judgement parts are overreach and label/template checks,
   with up to 3 repairs. It returns `status: "ready_to_commit"` or `status: "blocked"` with `reason` and
   `open_blocking_issues`; a blocked round is never committed. Without the Workflow tool (e.g. a Windows environment), execute
   the same protocol stage by stage with fresh agent sessions as its §6 describes, and still run `round_gate.py` and
   `verify_evidence.py` for the mechanical steps; paths are parameters.
5. **Verify yourself**: read the new §9 record, `review-verdicts/ledger.json` and the diff; run the full suite (`pytest -q` in
   `sycophancy_phase0/`) and the result's `gate_command` (the complete `round_gate.py` command the workflow's gate ran, with
   its state directory) and read its GATE line. The truth label
   comes only from the mathematics lens and the blind replication: 独立复核 needs both unrefuted with severity none, the
   blind replication's numbers reproduced and its isolation audit passed; any severity `wrong` gives 已驳回; anything else
   is 候选. The applicability verdict is a note on the claim and limits what the record may say about the design; it never
   changes the truth label (the result also carries the v4 label, which does). Downgrade any label the evidence does not
   support; never upgrade one. If `minor_issues_logged` is false, add `open_minor_issues` to the detailed record yourself.
   A stopped or abandoned round's material is recorded as unreviewed and never counted as a claim.
6. **Commit and push** on the session's designated branch with the session's commit conventions (add the files listed in
   `evidence_ignored_by_git` with `git add -f`, so that the verified evidence is committed); then answer in the A–F format:
   A 原始目标 / B 本轮核心障碍 / C 本轮实际推导 / D 严格核查 / E 路线决策 / F 更新研究档案, plus "尚未解决" items and the
   decisions the user must take, stated plainly.

## Rules (from the archive §0)
- Success = a meaningful idea formulation pushed to the strongest claim the evidence allows; "not solved" must be written as such.
- No fabricated proofs, no restating or renaming old results as progress, no silent weakening of the claim.
- Every 已证明 item needs a derivation and a pytest case (CPU simulation or exact arithmetic) or a GPU diagnostic that ran.
- A formula that depends on quantities the experiment cannot observe is not a budget rule; prefer procedures with quantified
  uncertainty (simulation from pilot data with bootstrap) over closed forms that only hold for assumed distributions.
- If two consecutive rounds make no real progress, re-examine the problem statement itself before attacking again.
- Every claim carries a scope and a does-not-claim sentence; a report sentence may never be stronger than its claim; "不存在 /
  不可能 / 只对 … 成立" needs a 已证明 claim with that quantifier.
- The ledger is complete: unreviewed and author-refuted claims are recorded as such with their evidence, never dropped.
