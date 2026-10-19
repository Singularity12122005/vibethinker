export const meta = {
  name: 'goal-round',
  description: 'One research round of the /goal archive: context -> parallel route attacks (derivation + simulation) -> adversarial refutation -> synthesis into the archive with tests -> label check',
  whenToUse: 'Invoked by the /goal skill for a round of docs/research/sycophancy-phase0-goal.md. args = {round, obstacle?, python?, scratch?, max_routes?, max_claims?}',
  phases: [
    { title: 'Context', detail: 'read the archive, fix the obstacle and up to 3 independent routes' },
    { title: 'Attack', detail: 'one agent per route: actual derivation + runnable simulation' },
    { title: 'Refute', detail: 'two lenses per claim (mathematics, implementation)' },
    { title: 'Synthesize', detail: 'round record + archive update + pytest cases' },
    { title: 'Check', detail: 'labels vs evidence, tests, diff scope' },
  ],
}

const ROOT = '/home/user/vibethinker'
const ARCHIVE = ROOT + '/docs/research/sycophancy-phase0-goal.md'
const PLAN = ROOT + '/docs/research/sycophancy-phase0-execution-plan.md'
const MODULE = ROOT + '/sycophancy_phase0/src/sycophancy_phase0/analysis/g6_iv.py'
const TESTS = ROOT + '/sycophancy_phase0/tests/test_analysis.py'
const PY = (args && args.python) || 'python3'
const SCRATCH = (args && args.scratch) || '/tmp/goal_rounds'
const round = (args && args.round) || 'rN'
const obstacle = (args && args.obstacle) || null
const MAX_ROUTES = Math.max(1, Math.min(3, (args && args.max_routes) || 3))
const MAX_CLAIMS = Math.max(1, Math.min(3, (args && args.max_claims) || 3))

const RULES = `Archive rules (${ARCHIVE} section 0): do real mathematics, not plans; never fabricate a proof; label every claim proved (derivation + runnable check) / candidate / refuted; restating, renaming or silently weakening an old result is not progress; do not repeat routes the archive lists as eliminated; never schedule or run anything autonomous; never modify repository files except where this prompt allows. Write scratch files only under ${SCRATCH}/${round}/.`

const CTX_SCHEMA = {
  type: 'object',
  properties: {
    obstacle: { type: 'string' },
    why_it_matters: { type: 'string' },
    routes: { type: 'array', items: { type: 'object', properties: {
      name: { type: 'string' }, tools: { type: 'string' }, core_claim: { type: 'string' }, how_it_implies: { type: 'string' },
      failure_point: { type: 'string' }, cheapest_check: { type: 'string' } }, required: ['name', 'tools', 'core_claim', 'how_it_implies', 'failure_point', 'cheapest_check'] } },
    do_not_repeat: { type: 'array', items: { type: 'string' } },
    constraints: { type: 'string' },
  },
  required: ['obstacle', 'why_it_matters', 'routes', 'do_not_repeat', 'constraints'],
}
const ATTACK_SCHEMA = {
  type: 'object',
  properties: {
    route: { type: 'string' },
    outcome: { type: 'string', enum: ['progress', 'partial', 'dead_end'] },
    claims: { type: 'array', items: { type: 'object', properties: {
      id: { type: 'string' }, statement: { type: 'string' }, status: { type: 'string', enum: ['proved', 'candidate', 'refuted'] },
      assumptions: { type: 'array', items: { type: 'string' } }, derivation_md: { type: 'string' }, evidence: { type: 'string' },
      script_path: { type: 'string' }, numbers: { type: 'array', items: { type: 'object', properties: { name: { type: 'string' }, value: { type: 'string' } }, required: ['name', 'value'] } } },
      required: ['id', 'statement', 'status', 'assumptions', 'derivation_md', 'evidence', 'script_path', 'numbers'] } },
    what_failed: { type: 'string' },
    next_step: { type: 'string' },
  },
  required: ['route', 'outcome', 'claims', 'what_failed', 'next_step'],
}
const VERDICT_SCHEMA = {
  type: 'object',
  properties: { refuted: { type: 'boolean' }, severity: { type: 'string', enum: ['none', 'overstated', 'gap', 'wrong'] }, reason: { type: 'string' }, fix: { type: 'string' }, strongest_attack_tried: { type: 'string' } },
  required: ['refuted', 'severity', 'reason', 'fix', 'strongest_attack_tried'],
}
const SYNTH_SCHEMA = {
  type: 'object',
  properties: { report_AF_md: { type: 'string' }, files_changed: { type: 'array', items: { type: 'string' } }, tests_passed: { type: 'boolean' }, test_output_tail: { type: 'string' } },
  required: ['report_AF_md', 'files_changed', 'tests_passed', 'test_output_tail'],
}
const CHECK_SCHEMA = {
  type: 'object',
  properties: { ok: { type: 'boolean' }, issues: { type: 'array', items: { type: 'string' } } },
  required: ['ok', 'issues'],
}

phase('Context')
const ctx = await agent(`You are the context agent of research round ${round} of the archive ${ARCHIVE}. Read the archive fully (sections 1, 3, 5, 7, 9), then ${PLAN} section 7.11, and ${MODULE}. ${obstacle ? 'The obstacle for this round is fixed by the user: ' + obstacle : 'Choose the single most important unresolved obstacle from section 7 ("最近的关键缺口" / "下一轮攻击").'} Formulate up to ${MAX_ROUTES} INDEPENDENT routes to attack it (tools, core proposition, how it implies progress on the obstacle, failure point, cheapest feasibility check). They must not all rely on one unproven lemma. List results the archive already has so the attackers do not repeat them. ${RULES}`, { schema: CTX_SCHEMA, phase: 'Context', label: 'context' })
if (!ctx) throw new Error('context agent returned nothing')
log(`obstacle: ${ctx.obstacle} — ${ctx.routes.length} routes`)

phase('Attack')
const routes = ctx.routes.slice(0, MAX_ROUTES)
const attacks = (await parallel(routes.map((r, i) => () => agent(`You are attacker ${i + 1} of research round ${round}. Obstacle: ${ctx.obstacle}. Why it matters: ${ctx.why_it_matters}. Your route: ${JSON.stringify(r)}. Constraints: ${ctx.constraints}. Already established (do NOT repeat as progress): ${ctx.do_not_repeat.join(' | ')}.
Do the ACTUAL mathematics now: write the derivation step by step (markdown with LaTeX), state every assumption, then write a runnable Python simulation or exact computation under ${SCRATCH}/${round}/${r.name.replace(/[^A-Za-z0-9_-]/g, '_')}/ and run it with ${PY} (numpy/scipy available). Read ${MODULE} first so your notation matches the archive (P1-P6 there). Report at most ${MAX_CLAIMS} claims with honest statuses; a dead end is a legitimate outcome and must be reported as such with what failed. ${RULES}`, { schema: ATTACK_SCHEMA, phase: 'Attack', label: `attack:${r.name}` })))).filter(Boolean)
log(`attacks finished: ${attacks.map(a => `${a.route}=${a.outcome}`).join(', ')}`)

const claims = []
for (const a of attacks) for (const c of a.claims) if (claims.length < MAX_CLAIMS && c.status !== 'refuted') claims.push({ ...c, route: a.route })
log(`${claims.length} claims go to refutation (cap ${MAX_CLAIMS})`)

phase('Refute')
const LENSES = [
  ['math', 'Check every step of the derivation and whether the stated assumptions suffice; construct a concrete counterexample (heteroskedastic binomial error, nonlinear functions, clustering, selection, weak identification, boundary cases) where the assumptions hold but the conclusion fails.'],
  ['implementation', 'Re-run the script, inspect it for bugs (wrong split, reused draws, wrong formula, in-sample leakage, wrong critical values), check that the numbers quoted in the evidence actually come out of the script, and whether the simulation tests what the claim says.'],
]
const judged = await pipeline(claims,
  c => parallel(LENSES.map(([lens, instr]) => () => agent(`You are an adversarial reviewer (lens: ${lens}) of claim ${c.id} from route "${c.route}" in research round ${round}. Claim: ${c.statement}. Status claimed: ${c.status}. Assumptions: ${c.assumptions.join('; ')}. Derivation:\n${c.derivation_md}\nEvidence: ${c.evidence}. Script: ${c.script_path}. Numbers: ${JSON.stringify(c.numbers)}.
${instr} Default to refuted=true when uncertain; "overstated" means the claim is true but labelled above its evidence. You may write and run scripts under ${SCRATCH}/${round}/review_${c.id.replace(/[^A-Za-z0-9_-]/g, '_')}_${lens}/ with ${PY}. Do not modify repository files.`, { schema: VERDICT_SCHEMA, phase: 'Refute', label: `refute:${c.id}:${lens}` }))).then(vs => ({ claim: c, verdicts: vs.filter(Boolean) })),
)
const results = judged.filter(Boolean).map(j => {
  const refuted = j.verdicts.some(v => v.refuted && v.severity === 'wrong')
  const overstated = j.verdicts.some(v => v.refuted && v.severity !== 'wrong')
  const final = refuted ? 'refuted' : overstated ? 'candidate' : (j.verdicts.length === LENSES.length ? j.claim.status : 'candidate')
  return { ...j.claim, final_status: final, independently_checked: j.verdicts.length === LENSES.length && !refuted && !overstated, verdicts: j.verdicts }
})
log(`verdicts: ${results.map(r => `${r.id}:${r.final_status}`).join(', ')}`)

phase('Synthesize')
const synth = await agent(`You are the synthesis agent of research round ${round}. Obstacle: ${ctx.obstacle}. Attack outcomes: ${JSON.stringify(attacks.map(a => ({ route: a.route, outcome: a.outcome, what_failed: a.what_failed, next_step: a.next_step })))}. Claims with final verdicts (use final_status; "independently_checked" true means both lenses failed to refute): ${JSON.stringify(results)}.
Tasks, in this order: (1) append a new record "### ${round}" to section 9 of ${ARCHIVE} in the A–F format used there (A 原始目标 / B 本轮核心障碍 / C 本轮实际推导 / D 严格核查 / E 路线决策 / F 更新研究档案), in Chinese, with the derivations' key formulas and numbers; (2) update section 7 of the archive: add proved items (final_status proved AND independently_checked) to "已证明" with the label 独立复核, candidates to "候选", refuted ones to "反例与错误" or "已淘汰路线", and rewrite "最近的关键缺口" and "下一轮攻击" from the next_step fields — never delete history, only append or relabel; (3) for every proved claim with a runnable check add a deterministic pytest case named test_goal_${round}_<id> to ${TESTS} (seeded numpy, runtime under 20 s each), and if a new estimator or formula is needed add it to ${MODULE} with a docstring that names the claim; (4) run "${PY} -m pytest ${ROOT}/sycophancy_phase0/tests/test_analysis.py -q" and report the tail. Only these three repository files may change. Return the A–F report in markdown. ${RULES}`, { schema: SYNTH_SCHEMA, phase: 'Synthesize', label: 'synthesize' })

phase('Check')
let check = await agent(`You are the final checker of research round ${round}. Run "git -C ${ROOT} status --short" and "git -C ${ROOT} diff -- ${ARCHIVE} ${TESTS} ${MODULE}". Verify: (1) every claim labelled 已证明/proved in the new section-9 record and in section 7 has a derivation in the record and a pytest case that exists in the diff; (2) no claim is labelled above its verdict in this list: ${JSON.stringify(results.map(r => ({ id: r.id, final_status: r.final_status, independently_checked: r.independently_checked })))}; (3) the diff touches only the three allowed files (scratch files outside the repo are fine); (4) "${PY} -m pytest ${ROOT}/sycophancy_phase0/tests/test_analysis.py -q" passes. Report ok=false with concrete issues otherwise. Do not modify files.`, { schema: CHECK_SCHEMA, phase: 'Check', label: 'check' })
if (check && !check.ok) {
  log(`check found ${check.issues.length} issues — one repair pass`)
  await agent(`Repair pass for research round ${round}. The checker found these issues: ${check.issues.join(' || ')}. Fix them in ${ARCHIVE}, ${TESTS} or ${MODULE} only (relabel claims downward if evidence is missing; never invent evidence), re-run "${PY} -m pytest ${ROOT}/sycophancy_phase0/tests/test_analysis.py -q" and make it pass. ${RULES}`, { schema: SYNTH_SCHEMA, phase: 'Check', label: 'repair' })
  check = await agent(`Re-check research round ${round} after the repair pass with the same four criteria (labels vs derivations and tests, labels vs verdicts ${JSON.stringify(results.map(r => ({ id: r.id, final_status: r.final_status })))}, diff scope limited to ${ARCHIVE} ${TESTS} ${MODULE}, pytest passing). Do not modify files.`, { schema: CHECK_SCHEMA, phase: 'Check', label: 'recheck' })
}
return { round, obstacle: ctx.obstacle, routes: routes.map(r => r.name), attacks: attacks.map(a => ({ route: a.route, outcome: a.outcome })), claims: results.map(r => ({ id: r.id, statement: r.statement, final_status: r.final_status, independently_checked: r.independently_checked })), report: synth ? synth.report_AF_md : null, tests_passed: synth ? synth.tests_passed : null, check }
