export const meta = {
  name: 'goal-round',
  description: 'One research round of the /goal archive (protocol: .claude/skills/goal/round-protocol.md): problem critique -> parallel route attacks -> full claim ledger -> three-lens refutation with blind replication -> synthesis with tests -> overreach + label check -> repaired result returned, or blocked',
  whenToUse: 'Invoked by the /goal skill for a round of docs/research/sycophancy-phase0-goal.md. args = {round, obstacle?, root?, python?, scratch?, max_routes?, max_claims?}',
  phases: [
    { title: 'Problem', detail: 'critique / reformulate the obstacle (template), fix up to 3 independent routes' },
    { title: 'Attack', detail: 'one agent per route: derivation + runnable check; every claim with scope and provenance' },
    { title: 'Refute', detail: 'ledger of ALL claims; three lenses on the reviewed subset; blind replication isolation audited' },
    { title: 'Synthesize', detail: 'round record (reviewed + unreviewed + author-refuted), archive update, tests, decisions' },
    { title: 'Check', detail: 'overreach lens on the report; label/evidence/scope/provenance check; one repair; final state returned' },
  ],
}

// ------------------------------------------------------------------------------------------------------------ configuration
const ROOT = (args && args.root) || '/home/user/vibethinker'
const ARCHIVE = ROOT + '/docs/research/sycophancy-phase0-goal.md'
const PLAN = ROOT + '/docs/research/sycophancy-phase0-execution-plan.md'
const MODULE = ROOT + '/sycophancy_phase0/src/sycophancy_phase0/analysis/g6_iv.py'
const TESTS = ROOT + '/sycophancy_phase0/tests/test_analysis.py'
const PROTOCOL = ROOT + '/.claude/skills/goal/round-protocol.md'
const PY = (args && args.python) || 'python3'
const SCRATCH = (args && args.scratch) || '/tmp/goal_rounds'
const round = (args && args.round) || 'rN'
const obstacle = (args && args.obstacle) || null
const MAX_ROUTES = Math.max(1, Math.min(3, (args && args.max_routes) || 3))
const MAX_CLAIMS = Math.max(1, Math.min(3, (args && args.max_claims) || 3))
const RDIR = `${SCRATCH}/${round}`
const safe = s => String(s).replace(/[^A-Za-z0-9_-]/g, '_')

const RULES = `Archive rules (${ARCHIVE} section 0, protocol ${PROTOCOL}): do real mathematics, not plans; never fabricate a proof; label every claim proved (derivation + runnable check) / candidate / refuted; every claim carries a scope sentence (conditions under which it holds) and a does-not-claim sentence; every number carries its source (script and output file); restating, renaming or silently weakening an old result is not progress; do not repeat routes the archive lists as eliminated; never schedule or run anything autonomous; never modify repository files except where this prompt allows. Write scratch files only under ${RDIR}/.`

// ------------------------------------------------------------------------------------------------------------ schemas
const ROUTE = { type: 'object', properties: { name: { type: 'string' }, tools: { type: 'string' }, core_claim: { type: 'string' }, how_it_implies: { type: 'string' }, failure_point: { type: 'string' }, cheapest_check: { type: 'string' } }, required: ['name', 'tools', 'core_claim', 'how_it_implies', 'failure_point', 'cheapest_check'] }
const PROBLEM_SCHEMA = {
  type: 'object',
  properties: {
    original_obstacle: { type: 'string' }, well_posed: { type: 'boolean' }, critique: { type: 'string' },
    template: { type: 'object', properties: { decision: { type: 'string' }, inputs_and_their_generating_mechanism: { type: 'string' }, model_class_or_compatible_set: { type: 'string' }, property_and_quantifiers: { type: 'string' }, success_failure_criterion: { type: 'string' }, out_of_scope: { type: 'string' } },
      required: ['decision', 'inputs_and_their_generating_mechanism', 'model_class_or_compatible_set', 'property_and_quantifiers', 'success_failure_criterion', 'out_of_scope'] },
    hidden_dependencies: { type: 'array', items: { type: 'string' } }, closed_form_plausible: { type: 'string', enum: ['yes', 'unlikely', 'no'] },
    obstacle: { type: 'string' }, why_it_matters: { type: 'string' }, routes: { type: 'array', items: ROUTE },
    do_not_repeat: { type: 'array', items: { type: 'string' } }, constraints: { type: 'string' },
  },
  required: ['original_obstacle', 'well_posed', 'critique', 'template', 'hidden_dependencies', 'closed_form_plausible', 'obstacle', 'why_it_matters', 'routes', 'do_not_repeat', 'constraints'],
}
const NUMBER = { type: 'object', properties: { name: { type: 'string' }, value: { type: 'string' }, source: { type: 'string' } }, required: ['name', 'value', 'source'] }
const CLAIM = { type: 'object', properties: {
  id: { type: 'string' }, statement: { type: 'string' }, status: { type: 'string', enum: ['proved', 'candidate', 'refuted'] },
  assumptions: { type: 'array', items: { type: 'string' } }, scope: { type: 'string' }, does_not_claim: { type: 'string' },
  derivation_md: { type: 'string' }, evidence: { type: 'string' }, script_path: { type: 'string' }, numbers: { type: 'array', items: NUMBER },
  experimental_consequence: { type: 'string' } },
  required: ['id', 'statement', 'status', 'assumptions', 'scope', 'does_not_claim', 'derivation_md', 'evidence', 'script_path', 'numbers', 'experimental_consequence'] }
const ATTACK_SCHEMA = { type: 'object', properties: { route: { type: 'string' }, outcome: { type: 'string', enum: ['progress', 'partial', 'dead_end'] }, claims: { type: 'array', items: CLAIM }, what_failed: { type: 'string' }, next_step: { type: 'string' } }, required: ['route', 'outcome', 'claims', 'what_failed', 'next_step'] }
const VERDICT_SCHEMA = { type: 'object', properties: { refuted: { type: 'boolean' }, severity: { type: 'string', enum: ['none', 'overstated', 'gap', 'wrong', 'irrelevant'] }, reason: { type: 'string' }, fix: { type: 'string' }, strongest_attack_tried: { type: 'string' }, reproduced_numbers: { type: 'boolean' }, files_read: { type: 'array', items: { type: 'string' } } }, required: ['refuted', 'severity', 'reason', 'fix', 'strongest_attack_tried', 'reproduced_numbers', 'files_read'] }
const SYNTH_SCHEMA = { type: 'object', properties: { report_AF_md: { type: 'string' }, decisions_for_user: { type: 'array', items: { type: 'string' } }, experiment_plan_changes: { type: 'array', items: { type: 'string' } }, files_changed: { type: 'array', items: { type: 'string' } }, tests_passed: { type: 'boolean' }, test_output_tail: { type: 'string' } }, required: ['report_AF_md', 'decisions_for_user', 'experiment_plan_changes', 'files_changed', 'tests_passed', 'test_output_tail'] }
const OVERREACH_SCHEMA = { type: 'object', properties: { overreach: { type: 'array', items: { type: 'object', properties: { sentence: { type: 'string' }, why: { type: 'string' }, supported_version: { type: 'string' } }, required: ['sentence', 'why', 'supported_version'] } } }, required: ['overreach'] }
const CHECK_SCHEMA = { type: 'object', properties: { ok: { type: 'boolean' }, issues: { type: 'array', items: { type: 'string' } } }, required: ['ok', 'issues'] }

// ------------------------------------------------------------------------------------------------------------ Problem
phase('Problem')
const ctx = await agent(`You are the problem agent of research round ${round} of the archive ${ARCHIVE}. Read ${PROTOCOL} section 2 (obstacle template), the archive (sections 1, 3, 5, 7, 9), ${PLAN} section 7.11, and ${MODULE}. ${obstacle ? 'The obstacle proposed for this round is: ' + obstacle : 'Take the first item of section 7 "下一轮攻击" as the proposed obstacle.'}
FIRST critique the obstacle statement before anyone attacks it, and fill the template: decision it informs; inputs and the mechanism that generates them (do they match the design's selection rule — e.g. h_3 prefixes selected as in plan §7.11, not h_2); model class or compatible set; the property to establish with its quantifiers; success/failure criterion; what is out of scope. List hidden dependencies the statement omits (full risk distribution, clustering, unequal continuation counts, response model, outcome noise). Say whether a closed form is plausible or a procedure is the honest target. If ill-posed, reformulate minimally and keep the original on record. THEN formulate up to ${MAX_ROUTES} INDEPENDENT routes (not all relying on one unproven lemma) and list results the archive already has. ${RULES}`, { schema: PROBLEM_SCHEMA, phase: 'Problem', label: 'problem' })
if (!ctx) throw new Error('problem agent returned nothing')
log(`obstacle${ctx.well_posed ? '' : ' (reformulated)'}: ${ctx.obstacle} — ${ctx.routes.length} routes; closed form ${ctx.closed_form_plausible}`)

// ------------------------------------------------------------------------------------------------------------ Attack
phase('Attack')
const routes = ctx.routes.slice(0, MAX_ROUTES)
const attacks = (await parallel(routes.map((r, i) => () => agent(`You are attacker ${i + 1} of research round ${round}. Obstacle: ${ctx.obstacle}. Template: ${JSON.stringify(ctx.template)}. Hidden dependencies flagged: ${ctx.hidden_dependencies.join(' | ')}. Your route: ${JSON.stringify(r)}. Constraints: ${ctx.constraints}. Already established (do NOT repeat as progress): ${ctx.do_not_repeat.join(' | ')}.
Do the ACTUAL mathematics now: derivation step by step (markdown with LaTeX), every assumption stated, then a runnable Python check under ${RDIR}/${safe(r.name)}/ run with ${PY} (numpy/scipy available; fractions.Fraction where exactness is claimed). Read ${MODULE} first so notation matches the archive. For every claim give: scope (conditions under which it holds), does_not_claim (the nearest stronger statement it does NOT establish), experimental consequence (which budget / criterion / gate decision changes, or 'none'), and for every number its source file. Report at most ${MAX_CLAIMS} claims with honest statuses; a dead end is a legitimate outcome and must be reported with what failed. ${RULES}`, { schema: ATTACK_SCHEMA, phase: 'Attack', label: `attack:${r.name}` })))).filter(Boolean)
log(`attacks finished: ${attacks.map(a => `${a.route}=${a.outcome}`).join(', ')}`)

// ------------------------------------------------------------------------------------------------------------ ledger
// Every claim of every route enters the ledger.  Author-refuted claims are not reviewed but are handed to synthesis with their
// evidence (they may be the round's most important counterexamples).  Review slots are filled round-robin across routes
// (proved/candidate first) so one route cannot occupy all slots; overflow is handed over marked unreviewed.
const ledger = []
for (const a of attacks) for (const c of a.claims) ledger.push({ ...c, route: a.route, ledger_status: c.status === 'refuted' ? 'author_refuted' : 'pending' })
const pending = ledger.filter(c => c.ledger_status === 'pending')
const byRoute = {}
for (const c of pending) (byRoute[c.route] = byRoute[c.route] || []).push(c)
for (const k of Object.keys(byRoute)) byRoute[k].sort((x, y) => (x.status === 'proved' ? 0 : 1) - (y.status === 'proved' ? 0 : 1))
const reviewed = []
let added = true
while (reviewed.length < MAX_CLAIMS && added) {
  added = false
  for (const k of Object.keys(byRoute)) { if (reviewed.length >= MAX_CLAIMS) break; const c = byRoute[k].shift(); if (c) { reviewed.push(c); added = true } }
}
for (const c of pending) if (!reviewed.includes(c)) c.ledger_status = 'unreviewed_overflow'
for (const c of reviewed) c.ledger_status = 'reviewed'
log(`ledger: ${ledger.length} claims — ${reviewed.length} reviewed, ${ledger.filter(c => c.ledger_status === 'unreviewed_overflow').length} unreviewed overflow, ${ledger.filter(c => c.ledger_status === 'author_refuted').length} author-refuted`)

// ------------------------------------------------------------------------------------------------------------ Refute
phase('Refute')
// Blind replication isolation: the lens receives only statement / assumptions / scope / numbers (no derivation, no script path),
// may write only in its own directory, must not open any other file of this round, and must list every file it read; the
// script audits files_read and withdraws the "blind" credit when the audit fails.  The derivation is not yet in the archive at
// this stage, so the attacker's scratch directory is the only leakage path.
const blindDir = c => `${RDIR}/review_${safe(c.id)}_blind_replication`
const LENSES = [
  ['math', c => `Derivation:\n${c.derivation_md}\nEvidence: ${c.evidence}. Script: ${c.script_path}. Check every step and whether the stated assumptions suffice; check that the scope sentence is the true scope; construct a concrete counterexample (heteroskedastic binomial error, nonlinear functions, clustering, selection, weak identification, exactly singular states) where the assumptions hold but the conclusion fails.`],
  ['blind_replication', c => `ISOLATION: you are given ONLY the statement, assumptions, scope and quoted numbers. You must NOT open any file under ${RDIR}/ except your own directory ${blindDir(c)}/, and must not search for the author's derivation or script anywhere. Re-implement the computation independently (exact arithmetic where exactness is claimed), report whether you reproduce the numbers (reproduced_numbers), then try to break the claim with your own cases. List EVERY file you read in files_read (the audit withdraws the blind credit if any file of this round outside your directory appears).`],
  ['scope', c => `Experimental consequence claimed: ${c.experimental_consequence}. Scope claimed: ${c.scope}. Judge whether the claim, if true, changes a decision of the Phase-0 design in ${PLAN} under the REAL conditions (prefixes clustered by question, continuation counts that may differ, a risk distribution that is not Beta and not known, h_3 prefixes selected as in §7.11); check each stated precondition against the real pipeline. Severity 'irrelevant' = true but changes nothing; 'overstated' = the stated consequence or scope does not follow.`],
]
const judged = await pipeline(reviewed,
  c => parallel(LENSES.map(([lens, instr]) => () => agent(`You are an adversarial reviewer (lens: ${lens}) of claim ${c.id} from route "${c.route}" in research round ${round}. Claim: ${c.statement}. Status claimed: ${c.status}. Assumptions: ${c.assumptions.join('; ')}. Scope: ${c.scope}. Does not claim: ${c.does_not_claim}. Numbers: ${JSON.stringify(c.numbers.map(n => ({ name: n.name, value: n.value })))}.
${instr(c)} Default to refuted=true when uncertain. You may write and run scripts under ${lens === 'blind_replication' ? blindDir(c) : `${RDIR}/review_${safe(c.id)}_${lens}`}/ with ${PY}. Do not modify repository files.`, { schema: VERDICT_SCHEMA, phase: 'Refute', label: `refute:${c.id}:${lens}`, effort: 'high' }))).then(vs => ({ claim: c, verdicts: vs, lenses: LENSES.map(l => l[0]) })),
)
const results = judged.filter(Boolean).map(j => {
  const vs = j.verdicts
  const got = l => vs[j.lenses.indexOf(l)] || null
  const blind = got('blind_replication')
  const blind_audit_ok = !!blind && blind.files_read.every(f => !String(f).includes(RDIR) || String(f).includes(blindDir(j.claim)))
  const present = vs.filter(Boolean)
  const wrong = present.some(v => v.refuted && v.severity === 'wrong')
  const soft = present.some(v => v.refuted && v.severity !== 'wrong')
  const complete = present.length === j.lenses.length
  const replicated = !!blind && blind.reproduced_numbers && blind_audit_ok
  const final = wrong ? 'refuted' : soft ? 'candidate' : (complete && replicated ? j.claim.status : 'candidate')
  return { ...j.claim, final_status: final, independently_checked: complete && replicated && !wrong && !soft, blind_audit_ok, verdicts: present, missing_lenses: j.lenses.filter((l, i) => !vs[i]) }
})
log(`verdicts: ${results.map(r => `${r.id}:${r.final_status}${r.independently_checked ? '(checked)' : ''}${r.blind_audit_ok ? '' : '(blind audit failed)'}`).join(', ')}`)
const handoff = {
  reviewed: results,
  unreviewed_overflow: ledger.filter(c => c.ledger_status === 'unreviewed_overflow'),
  author_refuted: ledger.filter(c => c.ledger_status === 'author_refuted'),
}

// ------------------------------------------------------------------------------------------------------------ Synthesize
phase('Synthesize')
const synthPrompt = extra => `You are the synthesis agent of research round ${round}. Original obstacle: ${ctx.original_obstacle}. ${ctx.well_posed ? '' : 'Reformulated obstacle: ' + ctx.obstacle + ' (critique: ' + ctx.critique + ').'} Template: ${JSON.stringify(ctx.template)}. Attack outcomes: ${JSON.stringify(attacks.map(a => ({ route: a.route, outcome: a.outcome, what_failed: a.what_failed, next_step: a.next_step })))}.
FULL LEDGER (nothing may be dropped): reviewed claims with verdicts (use final_status; independently_checked means all three lenses failed to refute, the blind replication reproduced the numbers and its isolation audit passed): ${JSON.stringify(handoff.reviewed)}. Unreviewed overflow (record as 未审, with evidence pointers, never as results): ${JSON.stringify(handoff.unreviewed_overflow)}. Author-refuted claims (record as 作者自驳 with their evidence — these may be the round's most important counterexamples): ${JSON.stringify(handoff.author_refuted)}.
Tasks, in this order: (1) append "### ${round}" to section 9 of ${ARCHIVE} in the A–F format used there, in Chinese, with the template, the derivations' key formulas and numbers WITH their sources and environments, every claim's scope and does-not-claim sentences copied verbatim, the full ledger with statuses, and explicit lists of decisions for the user and of changes (or 'none') to the experiment plan; (2) update section 7: proved AND independently_checked → "已证明" labelled 独立复核; candidates → "候选"; refuted/author-refuted → "反例与错误" or "已淘汰路线"; unreviewed → a "未审" line; rewrite "最近的关键缺口" and "下一轮攻击" from the next_step fields — never delete history; (3) for every proved claim with a runnable check add a deterministic pytest case named test_goal_${round}_<id> to ${TESTS} (seeded numpy or exact fractions, < 20 s each), adding to ${MODULE} only what the test needs, with a docstring naming the claim; (4) write ${RDIR}/manifest.md listing every script and output of this round; (5) run "${PY} -m pytest ${TESTS} -q" and report the tail. Only ${ARCHIVE}, ${TESTS}, ${MODULE} may change in the repository. The report must not contain any statement stronger than its supporting claim (no universal negatives such as "不存在" unless a claim with that quantifier is 已证明). ${extra} ${RULES}`
let synth = await agent(synthPrompt(''), { schema: SYNTH_SCHEMA, phase: 'Synthesize', label: 'synthesize' })

// ------------------------------------------------------------------------------------------------------------ Check
phase('Check')
const checkPrompt = () => `You are the final checker of research round ${round}. Run "git -C ${ROOT} status --short" and "git -C ${ROOT} diff -- ${ARCHIVE} ${TESTS} ${MODULE}". Verify: (1) every claim labelled 已证明/proved in the new section-9 record and in section 7 has a derivation in the record and a pytest case present in the diff; (2) no claim is labelled above its verdict: ${JSON.stringify(handoff.reviewed.map(r => ({ id: r.id, final_status: r.final_status, independently_checked: r.independently_checked })))}; (3) every ledger entry appears in the record with its status (unreviewed: ${JSON.stringify(handoff.unreviewed_overflow.map(c => c.id))}; author-refuted: ${JSON.stringify(handoff.author_refuted.map(c => c.id))}); (4) every number in the record carries a source and environment; every claim carries scope and does-not-claim; (5) the diff touches only the three allowed files; (6) "${PY} -m pytest ${TESTS} -q" passes; (7) decisions for the user and plan changes are listed. Report ok=false with concrete issues otherwise. Do not modify files.`
const overreachPrompt = report => `You are the overreach reviewer of research round ${round}. Compare this report sentence by sentence with the ledger ${JSON.stringify(handoff.reviewed.map(r => ({ id: r.id, statement: r.statement, scope: r.scope, does_not_claim: r.does_not_claim, final_status: r.final_status })))}. List every sentence that is stronger than its supporting claim (universal negatives, dropped conditions, "only"/"always"/"cannot" without a proved claim of that form, a candidate reported as established) and give the supported version. Report:\n${report}`
let over = await agent(overreachPrompt(synth ? synth.report_AF_md : ''), { schema: OVERREACH_SCHEMA, phase: 'Check', label: 'overreach' })
let check = await agent(checkPrompt(), { schema: CHECK_SCHEMA, phase: 'Check', label: 'check' })
const issues = [...((check && check.issues) || []), ...(((over && over.overreach) || []).map(o => `overreach: "${o.sentence}" — ${o.why}; supported: ${o.supported_version}`))]
if (!check || !check.ok || issues.length) {
  log(`check found ${issues.length} issues — one repair pass`)
  const repaired = await agent(`Repair pass for research round ${round}. Issues: ${issues.join(' || ')}. Fix them in ${ARCHIVE}, ${TESTS} or ${MODULE} only (relabel claims downward if evidence is missing; replace overreaching sentences by their supported versions; never invent evidence), re-run "${PY} -m pytest ${TESTS} -q" and make it pass. Return the CORRECTED report, decisions and plan changes. ${RULES}`, { schema: SYNTH_SCHEMA, phase: 'Check', label: 'repair' })
  if (repaired) synth = repaired                                   // the result returned to the caller is the post-repair state
  over = await agent(overreachPrompt(synth ? synth.report_AF_md : ''), { schema: OVERREACH_SCHEMA, phase: 'Check', label: 'overreach-recheck' })
  check = await agent(checkPrompt(), { schema: CHECK_SCHEMA, phase: 'Check', label: 'recheck' })
}
const finalIssues = [...((check && check.issues) || []), ...(((over && over.overreach) || []).map(o => `overreach: "${o.sentence}"`))]
const status = check && check.ok && finalIssues.length === 0 ? 'ready_to_commit' : 'blocked'
return { round, status, blocking_issues: finalIssues, original_obstacle: ctx.original_obstacle, obstacle: ctx.obstacle, well_posed: ctx.well_posed, template: ctx.template,
  routes: routes.map(r => r.name), attacks: attacks.map(a => ({ route: a.route, outcome: a.outcome })),
  ledger: ledger.map(c => ({ id: c.id, route: c.route, ledger_status: c.ledger_status, author_status: c.status })),
  claims: results.map(r => ({ id: r.id, statement: r.statement, final_status: r.final_status, independently_checked: r.independently_checked, blind_audit_ok: r.blind_audit_ok, missing_lenses: r.missing_lenses })),
  decisions_for_user: synth ? synth.decisions_for_user : null, experiment_plan_changes: synth ? synth.experiment_plan_changes : null,
  report: synth ? synth.report_AF_md : null, tests_passed: synth ? synth.tests_passed : null, check }
