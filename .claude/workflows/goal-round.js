export const meta = {
  name: 'goal-round',
  description: 'One /goal research round under round-protocol v5.1: baseline -> problem critique -> route attacks with atomic claims -> full ledger -> truth review (math + blind replication, isolation audit) with applicability notes -> fix-and-re-review (code-fact route with backup and revert) -> evidence copied, frozen and checked by code -> compact record + verified evidence table -> severity-gated audit -> ready_to_commit or blocked',
  whenToUse: 'Invoked by the /goal skill. args = {round, obstacle?, root?, python?, scratch?, module?, max_routes?, max_claims?, fix_rounds?, resume_note?}',
  phases: [
    { title: 'Problem', detail: 'baseline of the working tree and the suite (by code); critique / reformulate the obstacle with the template; up to 3 routes' },
    { title: 'Attack', detail: 'one agent per route; at most 6 atomic claims each, with a separate consequence note; unfinished computations listed by output path' },
    { title: 'Review', detail: 'math + blind replication decide truth; applicability lens writes the applicability note' },
    { title: 'Fix', detail: 'rewrite strictly from truth-lens fix texts (or apply a code change, with backup), process re-runs, stale code facts; then fresh review' },
    { title: 'Write', detail: 'copy + snapshot + ledger.json checked by round_gate.py; compact record; detailed record; evidence.json; tests' },
    { title: 'Audit', detail: 'round_gate.py measurements decided by the script, overreach, label/template/scope; blocking-only gate; up to 3 repairs' },
  ],
}

// ---------------------------------------------------------------------------------------------------------- configuration
const A = args || {}
const strip = p => String(p).replace(/^[ \t\r\n]+|[ \t\r\n]+$/g, '').replace(/\/+$/, '')
const BAD_CHARS = /[\p{Cc}\p{Cf}\p{Zl}\p{Zp}]/u                     // control, format, line/paragraph separators (as round_gate.py)
const num = (x, d, lo, hi) => { if (x === undefined || x === null || x === '') return d; const v = Number(x); return Number.isFinite(v) ? Math.max(lo, Math.min(hi, Math.floor(v))) : d }
const normalised = s => typeof s === 'string' && s.startsWith('/') && !s.includes('//') && !/\/\.{1,2}(\/|$)/.test(s) && !BAD_CHARS.test(s)
const under = (s, p) => s === p || s.startsWith(p + '/')
const absDir = (x, name) => { const s = strip(x); if (!normalised(s) || /[\s'"`$\\;&|<>*?]/.test(s)) throw new Error(`${name} must be an absolute, normalised path (no ., .., //, blanks, quotes or shell characters): ${x}`); return s }
const sq = s => `'${String(s).replace(/'/g, `'\\''`)}'`              // single-quote for the shell
const canonicalJSON = x => JSON.stringify(x).replace(/[\u007f-\uffff]/g, c => '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0'))
function sha256hex(ascii) {                                          // FIPS 180-4 SHA-256 of an ASCII string
  const K = [0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2]
  const bytes = []
  for (let i = 0; i < ascii.length; i++) bytes.push(ascii.charCodeAt(i) & 0xff)
  const bits = bytes.length * 8
  bytes.push(0x80)
  while (bytes.length % 64 !== 56) bytes.push(0)
  for (const x of [Math.floor(bits / 0x100000000), bits >>> 0]) bytes.push((x >>> 24) & 255, (x >>> 16) & 255, (x >>> 8) & 255, x & 255)
  const H = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19], W = new Array(64)
  const rotr = (x, n) => ((x >>> n) | (x << (32 - n))) >>> 0
  for (let off = 0; off < bytes.length; off += 64) {
    for (let t = 0; t < 16; t++) W[t] = ((bytes[off + 4 * t] << 24) | (bytes[off + 4 * t + 1] << 16) | (bytes[off + 4 * t + 2] << 8) | bytes[off + 4 * t + 3]) >>> 0
    for (let t = 16; t < 64; t++) W[t] = (W[t - 16] + (rotr(W[t - 15], 7) ^ rotr(W[t - 15], 18) ^ (W[t - 15] >>> 3)) + W[t - 7] + (rotr(W[t - 2], 17) ^ rotr(W[t - 2], 19) ^ (W[t - 2] >>> 10))) >>> 0
    let [a, b, c, d, e, f, g, h] = H
    for (let t = 0; t < 64; t++) {
      const t1 = (h + (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) + ((e & f) ^ (~e & g)) + K[t] + W[t]) >>> 0
      const t2 = ((rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) + ((a & b) ^ (a & c) ^ (b & c))) >>> 0
      h = g; g = f; f = e; e = (d + t1) >>> 0; d = c; c = b; b = a; a = (t1 + t2) >>> 0
    }
    ;[a, b, c, d, e, f, g, h].forEach((x, i) => { H[i] = (H[i] + x) >>> 0 })
  }
  return H.map(x => x.toString(16).padStart(8, '0')).join('')
}
const ROOT = absDir(A.root || '/home/user/vibethinker', 'root')
const PY = String(A.python || 'python3')
if (!/^[A-Za-z0-9_./-]+$/.test(PY)) throw new Error(`python must be a plain command or path, got ${PY}`)
const round = String(A.round || '')
if (!/^[A-Za-z0-9][A-Za-z0-9_-]*$/.test(round)) throw new Error(`round must be a plain name such as r5, got ${JSON.stringify(A.round)}`)
const SCRATCH = absDir(A.scratch || '/tmp/goal_rounds', 'scratch')
if (under(SCRATCH, ROOT) || under(ROOT, SCRATCH)) throw new Error(`scratch ${SCRATCH} and the repository ${ROOT} must not contain each other`)
const RDIR = `${SCRATCH}/${round}`
const STATE_DIR = `${SCRATCH}/${round}.state`                       // baseline file: outside RDIR, so never copied into the repository
const ARCHIVE = `${ROOT}/docs/research/sycophancy-phase0-goal.md`
const PLAN = `${ROOT}/docs/research/sycophancy-phase0-execution-plan.md`
const MODULE = absDir(A.module || `${ROOT}/sycophancy_phase0/src/sycophancy_phase0/analysis/g6_iv.py`, 'module')
if (!under(MODULE, ROOT) || MODULE === ROOT) throw new Error(`module ${MODULE} must be inside the repository`)
const MODULE_REL = MODULE.slice(ROOT.length + 1)
const TESTS = `${ROOT}/sycophancy_phase0/tests/test_analysis.py`
const PROTOCOL = `${ROOT}/.claude/skills/goal/round-protocol.md`
const VERIFIER = `${ROOT}/.claude/skills/goal/verify_evidence.py`
const GATE = `${ROOT}/.claude/skills/goal/round_gate.py`
const EVD_REL = `docs/research/goal-rounds/${round}`
const EVD = `${ROOT}/${EVD_REL}`
const MAX_ROUTES = num(A.max_routes, 3, 1, 3)
const MAX_CLAIMS = num(A.max_claims, 3, 1, 6)                     // review quota: 3 by default, at most 6 (§8.6)
const MAX_ATOMS = 6                                                // atomic claims per route (§8.6); more are recorded as dropped
const FIX_ROUNDS = num(A.fix_rounds, 1, 0, 2)
const MAX_REPAIRS = 3
const RECORD_TARGET = 12000, RECORD_HARD = 13000                   // §9 subsection: target and mechanical cap (characters)
const LBL = { ok: '独立复核', refuted: '已驳回', cand: '候选' }
const LENS_NAMES = ['math', 'blind_replication', 'applicability']
const pyid = s => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '')
const cut = (s, n) => { const t = String(s || ''); return t.length > n ? t.slice(0, n) + '…' : t }
const hasText = s => typeof s === 'string' && s.trim() !== '' && !/^(none|n\/a|na|-|无|没有)\.?$/i.test(s.trim())
const base = p => strip(p).split('/').pop()
const escRe = x => String(x).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const fileToken = (name, text) => !!name && new RegExp('(^|[\\s/\'"`(\\[{<,;:])' + escRe(name) + '($|[\\s\'"`)\\]}>,;:])').test(String(text || ''))
// commands the agents run verbatim (round_gate.py measures; this script decides)
const gateCmd = (only, extra = '') => `${PY} ${GATE} ${ROOT} ${round} --module ${MODULE_REL} --only ${only}${extra}`
const VERIFY_CMD = gateCmd('verifier')                              // sources only in the frozen working material, environment required
const TEST_CMD = `cd ${ROOT}/sycophancy_phase0 && ${PY} -m pytest -q -p no:cacheprovider`
// blind isolation (§8.6, v5.1 §9): forbidden prefixes, substrings and patterns; mirrored in round_gate.py
const FORBID_PREFIX = [SCRATCH, `${ROOT}/docs/research/goal-rounds`, ARCHIVE]
const FORBID_SUB = ['/docs/research/goal-rounds/', '/sycophancy-phase0-goal.md', '/.claude/projects/', '/subagents/', '/tool-results/']
const FORBID_RE = [/\/tasks\/[^/]+\.output$/]
const pathOk = (f, own) => {
  const s = strip(f)
  if (!normalised(s)) return false                                 // relative, ~, ., .. and // all count as out of bounds
  if (own && under(s, own)) return true
  if (FORBID_PREFIX.some(p => under(s, p))) return false
  if (FORBID_SUB.some(p => s.includes(p))) return false
  return FORBID_RE.every(re => !re.test(s))
}
const sourceOk = (src, dirs) => { const s = strip(src || ''); return normalised(s) && dirs.some(d => under(s, d)) }

const RULES = `Protocol ${PROTOCOL} (read §1-§9; v5.1 is in force). Do real mathematics, never fabricate a proof or a number, never restate an old result as progress, never repeat an eliminated route, never schedule anything. Each claim is ONE proposition (a theorem or identity, a set of numbers, or a code-interface fact); what it means for the experiment goes into a separate consequence note. Every number names the finished output file it comes from and the environment it was computed in. Scratch files only under ${RDIR}/ (outside the repository). Do not modify repository files unless this prompt says so.`

// ---------------------------------------------------------------------------------------------------------- schemas
const ROUTE = { type: 'object', properties: { name: { type: 'string' }, tools: { type: 'string' }, core_claim: { type: 'string' }, how_it_implies: { type: 'string' }, failure_point: { type: 'string' }, cheapest_check: { type: 'string' } }, required: ['name', 'tools', 'core_claim', 'how_it_implies', 'failure_point', 'cheapest_check'] }
const TEMPLATE = { type: 'object', properties: { decision: { type: 'string' }, inputs_and_their_generating_mechanism: { type: 'string' }, model_class_or_compatible_set: { type: 'string' }, property_and_quantifiers: { type: 'string' }, success_failure_criterion: { type: 'string' }, out_of_scope: { type: 'string' } }, required: ['decision', 'inputs_and_their_generating_mechanism', 'model_class_or_compatible_set', 'property_and_quantifiers', 'success_failure_criterion', 'out_of_scope'] }
const PROBLEM = { type: 'object', properties: {
  original_obstacle: { type: 'string' }, well_posed: { type: 'boolean' }, critique: { type: 'string' }, template: TEMPLATE,
  hidden_dependencies: { type: 'array', items: { type: 'string' } }, closed_form_plausible: { type: 'string', enum: ['yes', 'unlikely', 'no'] },
  obstacle: { type: 'string' }, why_it_matters: { type: 'string' }, routes: { type: 'array', items: ROUTE }, do_not_repeat: { type: 'array', items: { type: 'string' } }, constraints: { type: 'string' } },
  required: ['original_obstacle', 'well_posed', 'critique', 'template', 'hidden_dependencies', 'closed_form_plausible', 'obstacle', 'why_it_matters', 'routes', 'do_not_repeat', 'constraints'] }
const NUMBER = { type: 'object', properties: { name: { type: 'string' }, value: { type: 'string' }, kind: { type: 'string', enum: ['point', 'upper', 'lower', 'exact', 'count'] }, source: { type: 'string' }, conditions: { type: 'string' }, environment: { type: 'string' } }, required: ['name', 'value', 'kind', 'source', 'conditions', 'environment'] }
const CLAIM = { type: 'object', properties: {
  author_id: { type: 'string' }, kind: { type: 'string', enum: ['theorem', 'identity', 'numbers', 'code_fact'] }, statement: { type: 'string' }, premises: { type: 'string' },
  numbers: { type: 'array', items: NUMBER }, derivation_md: { type: 'string' }, script_path: { type: 'string' }, uses_module: { type: 'boolean' }, does_not_claim: { type: 'string' },
  consequence: { type: 'string' }, author_status: { type: 'string', enum: ['proved', 'candidate', 'refuted'] } },
  required: ['author_id', 'kind', 'statement', 'premises', 'numbers', 'derivation_md', 'script_path', 'uses_module', 'does_not_claim', 'consequence', 'author_status'] }
const UNFINISHED = { type: 'object', properties: { description: { type: 'string' }, output_paths: { type: 'array', items: { type: 'string' } } }, required: ['description', 'output_paths'] }
const ATTACK = { type: 'object', properties: { outcome: { type: 'string', enum: ['progress', 'partial', 'dead_end'] }, claims: { type: 'array', items: CLAIM }, unfinished_computations: { type: 'array', items: UNFINISHED }, what_failed: { type: 'string' }, next_step: { type: 'string' } }, required: ['outcome', 'claims', 'unfinished_computations', 'what_failed', 'next_step'] }
const TRUTH = { type: 'object', properties: { refuted: { type: 'boolean' }, severity: { type: 'string', enum: ['none', 'overstated', 'gap', 'wrong'] }, reason: { type: 'string' }, fix: { type: 'string' }, strongest_attack_tried: { type: 'string' }, reproduced_numbers: { type: 'boolean' }, files_read: { type: 'array', items: { type: 'string' } } }, required: ['refuted', 'severity', 'reason', 'fix', 'strongest_attack_tried', 'reproduced_numbers', 'files_read'] }
const APPLIC = { type: 'object', properties: { severity: { type: 'string', enum: ['none', 'gap', 'irrelevant'] }, premises_not_holding: { type: 'array', items: { type: 'string' } }, note: { type: 'string' }, consequence_follows: { type: 'boolean' } }, required: ['severity', 'premises_not_holding', 'note', 'consequence_follows'] }
const CHANGE = { type: 'object', properties: { field: { type: 'string', enum: ['statement', 'premises', 'numbers', 'kind', 'does_not_claim', 'consequence', 'code'] }, change: { type: 'string' }, from_lens: { type: 'string', enum: ['math', 'blind_replication', 'applicability'] } }, required: ['field', 'change', 'from_lens'] }
const REWRITE = { type: 'object', properties: { possible: { type: 'boolean' }, claim: CLAIM, changes: { type: 'array', items: CHANGE }, code_change: { type: 'string' } }, required: ['possible', 'claim', 'changes', 'code_change'] }
const CODE = { type: 'object', properties: { restore_line: { type: 'string' }, applied: { type: 'boolean' }, summary: { type: 'string' } }, required: ['restore_line', 'applied', 'summary'] }
const GATE_LINE = { type: 'object', properties: { gate_line: { type: 'string' } }, required: ['gate_line'] }
const LEDGER_OUT = { type: 'object', properties: { copy_line: { type: 'string' }, ledger_line: { type: 'string' } }, required: ['copy_line', 'ledger_line'] }
const WRITE = { type: 'object', properties: { report_AF_md: { type: 'string' }, decisions_for_user: { type: 'array', items: { type: 'string' } }, plan_changes: { type: 'array', items: { type: 'string' } }, evidence_entries: { type: 'integer' }, verifier_tail: { type: 'string' }, tests_tail: { type: 'string' }, files_changed: { type: 'array', items: { type: 'string' } } }, required: ['report_AF_md', 'decisions_for_user', 'plan_changes', 'evidence_entries', 'verifier_tail', 'tests_tail', 'files_changed'] }
const ISSUES = { type: 'object', properties: { issues: { type: 'array', items: { type: 'object', properties: { severity: { type: 'string', enum: ['blocking', 'minor'] }, where: { type: 'string' }, problem: { type: 'string' }, fix: { type: 'string' } }, required: ['severity', 'where', 'problem', 'fix'] } } }, required: ['issues'] }
const LOGGED = { type: 'object', properties: { appended: { type: 'boolean' }, files_changed: { type: 'array', items: { type: 'string' } } }, required: ['appended', 'files_changed'] }

const persist = path => `Before returning, write the exact JSON object you return to ${path} (create the directory).`
const parseGate = line => { const m = /GATE (\{.*\})\s*$/.exec(String(line || '').trim()); if (!m) return null; try { return JSON.parse(m[1]) } catch (e) { return null } }

// ---------------------------------------------------------------------------------------------------------- round state (every exit returns all of it)
let ctx = null, baselineHead = null, baselinePassed = null, attacks = [], ledger = [], current = [], w = null, codeEpoch = 0, evidenceIgnored = [], fullGateCmd = null
const allReviews = [], gaveUp = [], codeChanges = [], audits = [], minorSeen = new Map()
let lastBlocking = []
const finalLabels = () => current.map(r => ({ id: r.claim.id, version: r.claim.version, attempt: r.claim.attempt, truth_label: r.truth_label, v4_label: r.v4_label, blind_status: r.blind_status }))
const state = () => ({ round, obstacle: ctx && ctx.obstacle, original_obstacle: ctx && ctx.original_obstacle, well_posed: ctx && ctx.well_posed, template: ctx && ctx.template,
  baseline_tests_passed: baselinePassed, baseline_head: baselineHead, state_dir: STATE_DIR, gate_command: fullGateCmd, evidence_ignored_by_git: evidenceIgnored,
  attacks: attacks.map(a => ({ route: a.route, route_dir: a.route_dir, outcome: a.outcome, unfinished: a.unfinished_computations })),
  ledger: ledger.map(c => ({ id: c.id, route: c.route, ledger_status: c.ledger_status })),
  truth_labels: finalLabels(), versions: allReviews.map(r => ({ id: r.claim.id, version: r.claim.version, attempt: r.claim.attempt, review_reason: r.review_reason, truth_label: r.truth_label, blind_status: r.blind_status })),
  gave_up: gaveUp, code_changes: codeChanges, write: w, audits, open_blocking_issues: lastBlocking, open_minor_issues: [...minorSeen.values()] })
const blocked = reason => ({ ...state(), status: 'blocked', reason })

// ---------------------------------------------------------------------------------------------------------- Problem
phase('Problem')
const LONG = 'It may run the whole test suite and take up to 10 minutes: give the command a 600000 ms timeout (or run it in the background and wait for it to finish), and never return a line from an interrupted run.'
const mech = (label, phaseName, only, extra = '', sfx = '') => agent(`Mechanical step${sfx}. Run exactly this command and return its LAST output line (it starts with "GATE ") verbatim in gate_line; run nothing else and change no file yourself. ${LONG}\n${gateCmd(only, extra)}`, { schema: GATE_LINE, phase: phaseName, label, effort: 'low' }).then(x => x && parseGate(x.gate_line))
const baselineOk = g => g && g.baseline && !g.baseline.error && /^[0-9a-f]{64}$/.test(g.baseline.sha256 || '') && g.pytest && !g.pytest.error && g.pytest.summary_found === true
  && g.hashes && !g.hashes.error && g.hashes.module_sha && g.fresh && !g.fresh.error
const BASELINE_ARGS = ` --state-dir ${sq(STATE_DIR)} --copy-from ${sq(RDIR)}`
let blg = await mech('baseline', 'Problem', 'baseline,pytest,hashes,fresh', BASELINE_ARGS)
if (!baselineOk(blg)) blg = await mech('baseline:retry', 'Problem', 'baseline,pytest,hashes,fresh', BASELINE_ARGS, ' (retry)')
if (!baselineOk(blg)) return blocked('the baseline of the working tree could not be measured')
// a fresh run must start from empty round directories; a resume replays this measurement from the cache
if (blg.fresh.scratch_entries || blg.fresh.evidence_entries) return blocked(`round name ${round} was used before: ${blg.fresh.scratch_entries} entries in ${RDIR}, ${blg.fresh.evidence_entries} in ${EVD}; use a new round name or move them aside (a resume of the same run is not affected)`)
baselineHead = blg.baseline.head
baselinePassed = Number.isInteger(blg.pytest.passed) ? blg.pytest.passed : null
if (blg.pytest.failed || blg.pytest.errors) log(`baseline suite already fails: ${blg.pytest.tail}`)
log(`baseline: ${blg.baseline.count} changed paths before the round (${STATE_DIR}/baseline.json); HEAD ${String(baselineHead).slice(0, 12)}; suite ${blg.pytest.tail}`)

const problemPrompt = `You are the problem agent of research round ${round} of ${ARCHIVE}. Read ${PROTOCOL} §2 (obstacle template), the archive (§1, §3, §5, §7, §9), ${PLAN} §7.11 and ${MODULE}. ${A.obstacle ? 'Proposed obstacle: ' + A.obstacle : 'Take the first item of §7 "下一轮攻击" as the proposed obstacle.'}
Critique the statement and fill the template (decision; inputs and the mechanism that generates them, checked against the design's selection rules; model class or compatible set; property with quantifiers; success/failure criterion; out of scope); list hidden dependencies; say whether a closed form is plausible or a procedure is the honest target; reformulate minimally if ill-posed and keep the original. Then give up to ${MAX_ROUTES} independent routes that do not all rest on one unproven lemma, and the results the archive already has. ${persist(`${RDIR}/problem/problem.json`)} ${RULES}`
ctx = await agent(problemPrompt, { schema: PROBLEM, phase: 'Problem', label: 'problem' })
if (!ctx) ctx = await agent(problemPrompt, { schema: PROBLEM, phase: 'Problem', label: 'problem:retry' })
if (!ctx) return blocked('the problem agent returned nothing twice')
const routes = ctx.routes.slice(0, MAX_ROUTES)
if (ctx.routes.length > MAX_ROUTES) log(`dropped ${ctx.routes.length - MAX_ROUTES} routes beyond the cap: ${ctx.routes.slice(MAX_ROUTES).map(r => r.name).join(' | ')}`)
if (!routes.length) return blocked('the problem agent proposed no route')
log(`obstacle${ctx.well_posed ? '' : ' (reformulated)'}: ${ctx.obstacle}`)

// ---------------------------------------------------------------------------------------------------------- Attack
phase('Attack')
const routeDir = i => `${RDIR}/route${i + 1}`
const rawAttacks = await parallel(routes.map((r, i) => () => agent(`You are attacker ${i + 1} of research round ${round}. Obstacle: ${ctx.obstacle}. Template: ${JSON.stringify(ctx.template)}. Hidden dependencies: ${ctx.hidden_dependencies.join(' | ')}. Your route: ${JSON.stringify(r)}. Constraints: ${ctx.constraints}. Already established (not progress): ${ctx.do_not_repeat.join(' | ')}.
Do the ACTUAL mathematics: derivation step by step, every premise stated, runnable checks under ${routeDir(i)}/ run with ${PY} (exact arithmetic where exactness is claimed). script_path and every number's source must be absolute paths of finished output files under ${routeDir(i)}/; every number's environment names the python, numpy, scipy (and torch, if used) versions and the hardware. Read ${MODULE} first; set uses_module=true when a claim's script imports it. Do not open anything under ${RDIR}/ outside ${routeDir(i)}/ and do not look for the other routes' work. Split every result into ATOMIC claims (one proposition each; at most ${MAX_ATOMS}); put what a claim means for the experiment into its consequence field, not into the statement. Do NOT return while any of your own computations is still running; list anything unfinished in unfinished_computations with the absolute paths of the outputs it will write (never the same file name as a source you cite, and do not name finished files in its description), and cite no number from it. A dead end is a legitimate outcome. ${persist(`${routeDir(i)}/attack.json`)} ${RULES}`, { schema: ATTACK, phase: 'Attack', label: `attack:route${i + 1}` })))
attacks = rawAttacks.map((a, i) => a ? { ...a, route: routes[i].name, route_dir: routeDir(i) } : { route: routes[i].name, route_dir: routeDir(i), outcome: 'agent_failed', claims: [], unfinished_computations: [{ description: `attack agent returned nothing; any files under ${routeDir(i)}/ are unreviewed material`, output_paths: [] }], what_failed: 'agent failure', next_step: 'rerun this route' })
if (!rawAttacks.some(Boolean)) return blocked('no attack agent produced output')
log(`attacks: ${attacks.map(a => `${a.route}=${a.outcome}`).join(', ')}`)

// ---------------------------------------------------------------------------------------------------------- ledger (script-assigned ids, by route index)
// with output paths given, only full paths count; without them, the file name (in a path or as a token of the description)
const isUnfinished = (src, unf) => unf.some(u => (u.output_paths || []).length ? u.output_paths.some(o => strip(o) === strip(src)) : fileToken(base(src), u.description))
attacks.forEach((a, ri) => a.claims.forEach((c, j) => {
  let status = 'pending'
  if (j >= MAX_ATOMS) status = 'dropped_over_cap'
  else if (c.author_status === 'refuted') status = 'author_refuted'
  else if (c.numbers.some(n => !sourceOk(n.source, [routeDir(ri)]))) status = 'excluded_unsourced'
  else if (c.numbers.some(n => isUnfinished(n.source, a.unfinished_computations))) status = 'excluded_unfinished'
  ledger.push({ ...c, id: `R${ri + 1}-${j + 1}`, route: a.route, route_index: ri, version: 1, attempt: 1, ledger_status: status })
}))
const queues = attacks.map((_, ri) => ledger.filter(c => c.route_index === ri && c.ledger_status === 'pending').sort((x, y) => (x.author_status === 'proved' ? 0 : 1) - (y.author_status === 'proved' ? 0 : 1)))
const toReview = []
for (let progress = true; toReview.length < MAX_CLAIMS && progress;) {
  progress = false
  for (const q of queues) { if (toReview.length >= MAX_CLAIMS) break; const c = q.shift(); if (c) { toReview.push(c); progress = true } }
}
for (const c of ledger) if (c.ledger_status === 'pending') c.ledger_status = toReview.includes(c) ? 'reviewed' : 'unreviewed_overflow'
const countOf = s => ledger.filter(c => c.ledger_status === s).length
log(`ledger: ${ledger.length} claims; reviewed ${toReview.length}; overflow ${countOf('unreviewed_overflow')}; author-refuted ${countOf('author_refuted')}; excluded unfinished ${countOf('excluded_unfinished')}; excluded unsourced ${countOf('excluded_unsourced')}; dropped over cap ${countOf('dropped_over_cap')}`)

// ---------------------------------------------------------------------------------------------------------- review (v5 truth rule, announced before any verdict)
log(`v5 truth rule: ${LBL.ok} iff math and blind replication are both unrefuted with severity none, the blind replication reproduced the numbers (or verified the proposition exactly on its own finite example) and its isolation audit passed; any 'wrong' => ${LBL.refuted}; otherwise ${LBL.cand}. The applicability lens writes the applicability note only. The v4 label (any objection of any lens => ${LBL.cand}) is kept alongside.`)
const dirOf = (c, lens) => `${RDIR}/review/${c.id}_v${c.version}_a${c.attempt}_${lens}`
const LENSES = {
  math: [TRUTH, c => `Derivation:\n${c.derivation_md}\nScript: ${c.script_path}. Decide whether the proposition follows from its premises EXACTLY as written; construct a counterexample within the premises if one exists (boundary and singular cases, heteroskedasticity, clustering, selection). Severity 'none' means true as written, every word.`],
  blind_replication: [TRUTH, c => `ISOLATION: you receive only the proposition, premises and numbers. Your own directory is ${dirOf(c, 'blind_replication')}/. Do NOT open: anything under ${SCRATCH}/ outside your own directory; ${ARCHIVE}; anything under a docs/research/goal-rounds/ directory; any session transcript, subagent file, tool-results file or task output file (paths containing /.claude/projects/, /subagents/, /tool-results/ or /tasks/*.output). Do not search for the authors' scripts, derivations or earlier reviews. You may read ${MODULE} and other source code. Keep tool outputs short: redirect long command output into a file in your own directory and print only what you need; never open a persisted tool-results file. Re-implement independently (exact arithmetic where exactness is stated) and verify every number; with no numbers, set reproduced_numbers=true only after verifying the proposition exactly on a finite example of your own. List EVERY file you read in files_read as an absolute, normalised path (your own scripts included); a relative path or one containing . or .. fails the audit.`],
  applicability: [APPLIC, c => `Consequence the author draws: ${c.consequence}. Do not judge truth. Judge whether the premises hold for the real design in ${PLAN} (selection rules, clustering, unknown risk law, arm sizes, order of generation) and whether the consequence follows (consequence_follows): severity 'none' = premises hold there as stated; 'gap' = list each premise that does or may not hold in premises_not_holding; 'irrelevant' = holds but bears on no decision. Your note becomes the claim's applicability note.`],
}
const runLens = (c, lens) => {
  const [schema, instr] = LENSES[lens]
  return agent(`Fresh reviewer (lens: ${lens}) of claim ${c.id} (version ${c.version}, attempt ${c.attempt}) of research round ${round}.
PROPOSITION: ${c.statement}
PREMISES: ${c.premises}
NUMBERS: ${JSON.stringify(c.numbers.map(n => ({ name: n.name, value: n.value, kind: n.kind, conditions: n.conditions })))}
DOES NOT CLAIM: ${c.does_not_claim}
${instr(c)} ${lens === 'applicability' ? '' : 'Default to refuted=true when uncertain about truth. '}Scripts only under ${dirOf(c, lens)}/, run with ${PY}. ${persist(`${dirOf(c, lens)}/verdict.json`)} Do not modify repository files.`,
    { schema, phase: c.version > 1 || c.attempt > 1 ? 'Fix' : 'Review', label: `review:${c.id}:v${c.version}a${c.attempt}:${lens}`, effort: 'high' })
    .then(v => v ? { ...v, review_dir: dirOf(c, lens), code_epoch: codeEpoch } : null)
}
function decide(c, vs, reason, lensesRun, epoch) {
  const m = vs.math || null, b = vs.blind_replication || null, ap = vs.applicability || null
  const audit = !!b && Array.isArray(b.files_read) && b.files_read.length > 0 && b.files_read.every(f => pathOk(f, b.review_dir))
  const blind_status = !b ? 'missing' : audit ? 'ok' : 'audit_failed'
  const clean = v => !!v && v.refuted === false && v.severity === 'none'
  const truth = clean(m) && clean(b) && b.reproduced_numbers === true && audit ? LBL.ok : [m, b].some(v => v && v.severity === 'wrong') ? LBL.refuted : LBL.cand
  const v4 = truth === LBL.refuted ? LBL.refuted : truth === LBL.ok && ap && ap.severity === 'none' ? LBL.ok : LBL.cand
  const eps = [m, b, ap].filter(Boolean).map(v => v.code_epoch).filter(Number.isInteger)
  return { claim: c, truth_label: truth, v4_label: v4, blind_status, missing_lenses: LENS_NAMES.filter(l => !vs[l]), verdicts: { math: m, blind_replication: b, applicability: ap }, review_reason: reason, lenses_run: lensesRun, code_epoch: eps.length ? Math.min(...eps) : epoch }
}
// item = {claim, lenses, keep (verdicts kept from the same text), reason}; a failed pipeline stage yields the all-missing decision
const reviewItems = items => { const epoch = codeEpoch; return pipeline(items, it => parallel(it.lenses.map(l => () => runLens(it.claim, l))).then(res => {
  const vs = { ...(it.keep || {}) }
  it.lenses.forEach((l, j) => { vs[l] = res[j] || null })
  return decide(it.claim, vs, it.reason, it.lenses, epoch)
})).then(out => out.map((r, j) => r || { ...decide(items[j].claim, { ...(items[j].keep || {}), ...Object.fromEntries(items[j].lenses.map(l => [l, null])) }, items[j].reason, items[j].lenses, epoch), review_failed: true })) }
phase('Review')
current = await reviewItems(toReview.map(c => ({ claim: c, lenses: LENS_NAMES, reason: 'first' })))
allReviews.push(...current)
log(`truth labels: ${current.map(r => `${r.claim.id}:${r.truth_label}${r.blind_status === 'ok' ? '' : '(blind ' + r.blind_status + ')'}`).join(', ')}`)

// ---------------------------------------------------------------------------------------------------------- fix and re-review
const FIELDS = ['statement', 'premises', 'numbers', 'kind', 'does_not_claim', 'consequence']
const TRUTH_FIELDS = ['statement', 'premises', 'numbers', 'kind']
const canon = (f, v) => f === 'numbers' ? JSON.stringify((v || []).map(n => [n.name, n.value, n.kind, strip(n.source || ''), n.conditions, n.environment])) : JSON.stringify(typeof v === 'string' ? v.trim() : v)
const notClean = v => !!v && !(v.refuted === false && v.severity === 'none')
function checkRewrite(wr, old) {
  if (!wr) return 'rewrite agent returned nothing'
  if (!wr.possible) return 'not possible without new mathematics (rewriter)'
  if (!wr.changes.length) return 'no change declared'
  const changed = FIELDS.filter(f => canon(f, wr.claim[f]) !== canon(f, old[f]))
  const wantsCode = wr.changes.some(ch => ch.field === 'code')
  for (const f of changed) if (!wr.changes.some(ch => ch.field === f)) return `undeclared change of ${f}`
  for (const ch of wr.changes) if (TRUTH_FIELDS.includes(ch.field) && ch.from_lens === 'applicability') return `${ch.field} changed on an applicability note`
  if (!changed.length && !wantsCode) return 'nothing changed (re-reviewing the same text is not a fix)'
  if (wantsCode && !hasText(wr.code_change)) return "field 'code' declared without a code_change"
  if (wantsCode && wr.claim.kind !== 'code_fact') return 'a code change serves only a code_fact claim'
  if (wr.claim.numbers.some(n => !sourceOk(n.source, [routeDir(old.route_index), `${RDIR}/rewrite`]))) return 'a number has no finished source under the route or rewrite directory'
  if (wr.claim.numbers.some(n => isUnfinished(n.source, attacks[old.route_index].unfinished_computations))) return 'a number comes from a computation its route listed as unfinished'
  return null
}
async function applyCode(old, wr) {                                // sequential; backup, restore, test run and the expected hashes are mechanical
  const v = old.version + 1, cdir = `${RDIR}/code/${old.id}_v${v}`, rec = { id: old.id, version: v, change: wr.code_change, dir: cdir }
  const SD = ` --state-dir ${sq(STATE_DIR)}`, BD = ` --backup-dir ${sq(cdir)}`
  const restoreCmd = gateCmd('restore', BD + SD)
  const restored = g => !!(g && g.restore && g.restore.restored === true && g.restore.matches_expected === true)
  const restore = async () => {
    let rs = await mech(`restore:${old.id}:v${v}`, 'Fix', 'restore', BD + SD)
    if (!restored(rs)) rs = await mech(`restore:${old.id}:v${v}:retry`, 'Fix', 'restore', BD + SD, ' (retry)')
    return restored(rs)
  }
  let bk = await mech(`backup:${old.id}:v${v}`, 'Fix', 'backup', BD + SD)
  if (!bk || !bk.backup || bk.backup.error) bk = await mech(`backup:${old.id}:v${v}:retry`, 'Fix', 'backup', BD + SD, ' (retry)')
  if (!bk || !bk.backup || bk.backup.error) return { ok: false, why: 'the module could not be backed up; no code change was attempted' }
  if (bk.backup.matches_expected !== true)                         // the files or an existing backup differ from the recorded reference
    return { fatal: `${MODULE} or ${TESTS} (or the backup in ${cdir}) differ from the reference recorded in ${STATE_DIR}/expect.json before this code change` }
  const code = await agent(`Apply a code change for claim ${old.id} v${v} of round ${round}. FIRST run exactly this command (it puts ${MODULE} and ${TESTS} back to the backed-up state, which matters if an earlier attempt was interrupted) and put its last output line (starting "GATE ") in restore_line:\n${restoreCmd}\nThen apply exactly this change to ${MODULE}, add one pinning test to ${TESTS}, and change nothing else: ${wr.code_change}. Claim it serves: ${wr.claim.statement}. You may run "${TEST_CMD}" to check your work (up to 10 minutes; use a 600000 ms timeout). Do not copy, back up or restore any file yourself. Set applied=true only if the change is complete. ${RULES}`, { schema: CODE, phase: 'Fix', label: `code:${old.id}:v${v}` })
  const after = await mech(`codecheck:${old.id}:v${v}`, 'Fix', 'hashes,pytest', SD)
  const p = after && after.pytest
  const ok = !!(code && restored(parseGate(code.restore_line)) && code.applied && after && after.hashes && !after.hashes.error && after.hashes.module_changed === true
    && p && !p.error && p.summary_found && p.exit === 0 && !p.failed && !p.errors && p.passed > 0 && (baselinePassed === null || p.passed >= baselinePassed))
  if (ok) {
    let ac = await mech(`accept:${old.id}:v${v}`, 'Fix', 'accept', SD)
    if (!ac || !ac.accept || ac.accept.accepted !== true) ac = await mech(`accept:${old.id}:v${v}:retry`, 'Fix', 'accept', SD, ' (retry)')
    if (!ac || !ac.accept || ac.accept.accepted !== true) return { fatal: `the accepted code change for ${old.id} v${v} could not be recorded in ${STATE_DIR}/expect.json` }
    codeEpoch++
    codeChanges.push({ ...rec, outcome: 'applied', epoch: codeEpoch, summary: code.summary, tests_tail: p.tail })
    return { ok: true, code: { summary: code.summary, tests_tail: p.tail } }
  }
  if (!(await restore())) return { fatal: `code change for ${old.id} v${v} failed and ${MODULE} / ${TESTS} could not be restored to the backup in ${cdir}` }
  codeChanges.push({ ...rec, outcome: 'reverted', summary: code ? code.summary : 'code agent returned nothing', tests_tail: p ? p.tail : null })
  return { ok: false, why: `code change ${code ? (code.applied ? 'did not leave a passing suite' : 'reported incomplete') : 'agent returned nothing'}; module and tests restored from the backup` }
}
// process failures only, and only where a re-run can change the outcome: a missing lens, or a failed isolation audit of a
// blind verdict that would otherwise have passed; a substantive negative (wrong, gap, not reproduced) is kept
function rerunLenses(r) {
  const m = r.verdicts.math, b = r.verdicts.blind_replication
  const bPass = !!b && b.refuted === false && b.severity === 'none' && b.reproduced_numbers === true
  const lenses = LENS_NAMES.filter(l => !r.verdicts[l] || (l === 'blind_replication' && r.blind_status === 'audit_failed' && bPass))
  const truthBlocked = (!!m && notClean(m)) || (!!b && !bPass)
  return truthBlocked ? lenses.filter(l => l === 'applicability') : lenses
}
function rerunItem(slot) {
  const r = current[slot], x = rerunLenses(r)
  rerunDone.add(`${r.claim.id}_v${r.claim.version}`)
  const kept = LENS_NAMES.filter(l => !x.includes(l) && r.verdicts[l])
  const full = moduleClaim(r.claim) && kept.some(l => !(r.verdicts[l].code_epoch >= codeEpoch))   // kept verdicts predate a code change
  const lenses = full ? LENS_NAMES : x
  return { slot, claim: { ...r.claim, attempt: r.claim.attempt + 1 }, lenses, keep: Object.fromEntries(LENS_NAMES.filter(l => !lenses.includes(l)).map(l => [l, r.verdicts[l]])), reason: full ? 'process_rerun_after_code_change' : 'process_rerun' }
}
const moduleClaim = c => c.kind === 'code_fact' || !!c.uses_module
const gaveUpIds = new Set(), rerunDone = new Set()
for (let k = 1; k <= FIX_ROUNDS; k++) {
  const rewriteSlots = [], rerunCand = []
  current.forEach((r, i) => {
    if (gaveUpIds.has(r.claim.id)) return
    const m = r.verdicts.math, b = r.verdicts.blind_replication
    if (r.truth_label !== LBL.ok && [m, b].some(v => notClean(v) && hasText(v.fix))) { rewriteSlots.push(i); return }
    if (rerunLenses(r).length && !rerunDone.has(`${r.claim.id}_v${r.claim.version}`)) rerunCand.push({ slot: i })
  })
  const staleAny = current.some(r => r.truth_label === LBL.ok && moduleClaim(r.claim) && r.code_epoch < codeEpoch)
  if (!rewriteSlots.length && !rerunCand.length && !staleAny) break
  phase('Fix')
  const rewrites = await parallel(rewriteSlots.map(i => () => { const r = current[i]; return agent(`Rewrite claim ${r.claim.id} (version ${r.claim.version}) of round ${round} STRICTLY from the truth lenses' fix texts — no new mathematics, no strengthening; if the fixes cannot be applied without new mathematics, set possible=false. Every changed field (statement, premises, numbers, kind, does_not_claim, consequence) must have a change entry naming the field and the lens its text comes from; statement, premises, numbers and kind may change only on math or blind-replication fix texts; any unlisted change rejects the rewrite. New numbers need finished sources under ${routeDir(r.claim.route_index)}/ or ${RDIR}/rewrite/. If the claim is a code_fact and its failures are edge cases of the code's input handling, add a change with field 'code' and describe in code_change the minimal change to ${MODULE} that makes the property an interface fact, and state the claim about the changed code; otherwise leave code_change empty. Original claim: ${JSON.stringify(r.claim)}. Math verdict: ${JSON.stringify(r.verdicts.math)}. Blind-replication verdict: ${JSON.stringify(r.verdicts.blind_replication)}. Applicability verdict: ${JSON.stringify(r.verdicts.applicability)}. ${persist(`${RDIR}/rewrite/${r.claim.id}_v${r.claim.version + 1}.json`)} ${RULES}`, { schema: REWRITE, phase: 'Fix', label: `rewrite:${r.claim.id}:v${r.claim.version + 1}` }) }))
  const items = []
  for (let j = 0; j < rewriteSlots.length; j++) {
    const wr = rewrites[j], r = current[rewriteSlots[j]], old = r.claim
    const why = checkRewrite(wr, old)
    const rewriteFile = `${RDIR}/rewrite/${old.id}_v${old.version + 1}.json`
    if (why) { gaveUpIds.add(old.id); gaveUp.push({ id: old.id, from_version: old.version, reason: why, rewrite_file: rewriteFile }); continue }
    let code = null
    if (wr.changes.some(ch => ch.field === 'code')) {
      const res = await applyCode(old, wr)
      if (res.fatal) return blocked(res.fatal)
      if (!res.ok) { gaveUpIds.add(old.id); gaveUp.push({ id: old.id, from_version: old.version, reason: res.why, rewrite_file: rewriteFile }); continue }
      code = res.code
    }
    const claim = { ...old, statement: wr.claim.statement, premises: wr.claim.premises, numbers: wr.claim.numbers, kind: wr.claim.kind, does_not_claim: wr.claim.does_not_claim, consequence: wr.claim.consequence,
      derivation_md: wr.claim.derivation_md, script_path: wr.claim.script_path, uses_module: !!(old.uses_module || wr.claim.uses_module), version: old.version + 1, attempt: 1, changes: wr.changes,
      code_applied: code ? { change: wr.code_change, summary: code.summary, tests_tail: code.tests_tail, epoch: codeEpoch } : null }
    items.push({ slot: rewriteSlots[j], claim, lenses: LENS_NAMES, reason: 'rewrite' })
  }
  // process re-runs, decided after this round's code changes
  for (const x of rerunCand) items.push(rerunItem(x.slot))
  // claims labeled 独立复核 about the module are stale once its code changed after their review: re-review them on the same text
  current.forEach((r, i) => {
    if (r.truth_label === LBL.ok && moduleClaim(r.claim) && r.code_epoch < codeEpoch && !items.some(x => x.slot === i))
      items.push({ slot: i, claim: { ...r.claim, attempt: r.claim.attempt + 1 }, lenses: LENS_NAMES, reason: 'stale_after_code_change' })
  })
  if (!items.length) break
  const again = await reviewItems(items)
  items.forEach((x, j) => { allReviews.push(again[j]); current[x.slot] = again[j] })
  log(`fix round ${k}: ${items.map((x, j) => `${x.claim.id} v${x.claim.version}a${x.claim.attempt} (${x.reason}): ${again[j].truth_label}`).join(', ')}${gaveUp.length ? '; given up: ' + gaveUp.map(g => `${g.id} (${g.reason})`).join(', ') : ''}`)
}
// a process failure in the last fix round's reviews (a rewrite's or a stale re-review's) still gets its one re-run
{
  const last = current.map((r, i) => i).filter(i => rerunLenses(current[i]).length && !rerunDone.has(`${current[i].claim.id}_v${current[i].claim.version}`))
  if (last.length) {
    phase('Fix')
    const items = last.map(rerunItem)
    const again = await reviewItems(items)
    items.forEach((x, j) => { allReviews.push(again[j]); current[x.slot] = again[j] })
    log(`process re-runs after the fix rounds: ${items.map((x, j) => `${x.claim.id} v${x.claim.version}a${x.claim.attempt} (${x.reason}): ${again[j].truth_label}`).join(', ')}`)
  }
}
const staleLeft = current.filter(r => r.truth_label === LBL.ok && moduleClaim(r.claim) && r.code_epoch < codeEpoch)
if (staleLeft.length) log(`no fix round left to re-review ${staleLeft.map(r => r.claim.id).join(', ')} after the last code change; the record must say they were reviewed at an earlier code epoch`)

// ---------------------------------------------------------------------------------------------------------- Write: copy, snapshot, ledger.json (checked by code), then the record
phase('Write')
const pick = (o, keys) => Object.fromEntries(keys.filter(k => o && o[k] !== undefined).map(k => [k, o[k]]))
const projNums = ns => (ns || []).map(n => pick(n, ['name', 'value', 'kind', 'source', 'conditions', 'environment']))
const projChanges = cs => (cs || []).map(c => pick(c, ['field', 'change', 'from_lens']))
const projUnf = us => (us || []).map(u => pick(u, ['description', 'output_paths']))
const K = v => v ? { refuted: v.refuted, severity: v.severity, reproduced_numbers: v.reproduced_numbers, files_read: v.files_read, review_dir: v.review_dir, code_epoch: v.code_epoch } : null
const AP = v => v ? { severity: v.severity, premises_not_holding: v.premises_not_holding, note: cut(v.note, 600), consequence_follows: v.consequence_follows, review_dir: v.review_dir, code_epoch: v.code_epoch } : null
const versionRec = r => ({ id: r.claim.id, version: r.claim.version, attempt: r.claim.attempt, route: r.claim.route, route_index: r.claim.route_index, author_id: r.claim.author_id, author_status: r.claim.author_status,
  kind: r.claim.kind, uses_module: r.claim.uses_module, statement: r.claim.statement, premises: r.claim.premises, does_not_claim: r.claim.does_not_claim, consequence: r.claim.consequence, numbers: projNums(r.claim.numbers),
  script_path: r.claim.script_path, changes: projChanges(r.claim.changes), code_applied: r.claim.code_applied || null, review_reason: r.review_reason, lenses_run: r.lenses_run, code_epoch: r.code_epoch,
  verdicts: { math: K(r.verdicts.math), blind_replication: K(r.verdicts.blind_replication), applicability: AP(r.verdicts.applicability) },
  truth_label: r.truth_label, v4_label: r.v4_label, blind_status: r.blind_status, missing_lenses: r.missing_lenses, review_failed: !!r.review_failed })
const LEDGER = { round, protocol: 'v5.1', scratch_round_dir: RDIR, evidence_dir: EVD_REL,
  truth_rule: `${LBL.ok} iff math and blind replication unrefuted with severity none, blind reproduced_numbers=true and isolation audit ok; any severity wrong => ${LBL.refuted}; else ${LBL.cand}. v4: ${LBL.ok} only if additionally applicability severity none.`,
  isolation: { forbid_prefix: FORBID_PREFIX, forbid_sub: FORBID_SUB, forbid_re: FORBID_RE.map(re => re.source) },
  versions: allReviews.map(versionRec), final: finalLabels(),
  not_reviewed: ledger.filter(c => c.ledger_status !== 'reviewed').map(c => ({ id: c.id, author_id: c.author_id, route: c.route, ledger_status: c.ledger_status, author_status: c.author_status, kind: c.kind, statement: cut(c.statement, 400), full_text: `${routeDir(c.route_index)}/attack.json`, numbers: projNums(c.numbers).map(n => pick(n, ['name', 'kind', 'source'])) })),
  gave_up: gaveUp, code_changes: codeChanges, code_epoch: codeEpoch,
  attacks: attacks.map(a => ({ route: a.route, route_dir: a.route_dir, outcome: a.outcome, unfinished: projUnf(a.unfinished_computations).map(u => ({ ...u, description: cut(u.description, 300) })), what_failed: cut(a.what_failed, 400), next_step: cut(a.next_step, 400) })) }
// the verdict prose the writer needs (the full texts are in the frozen review/*/verdict.json files)
const VTEXT = allReviews.map(r => ({ id: r.claim.id, version: r.claim.version, attempt: r.claim.attempt, math: r.verdicts.math && { reason: cut(r.verdicts.math.reason, 600), fix: cut(r.verdicts.math.fix, 300) },
  blind_replication: r.verdicts.blind_replication && { reason: cut(r.verdicts.blind_replication.reason, 600), fix: cut(r.verdicts.blind_replication.fix, 300) } }))
const EXPECT = { versions: allReviews.map(r => ({ id: r.claim.id, version: r.claim.version, attempt: r.claim.attempt, truth_label: r.truth_label, v4_label: r.v4_label, blind_status: r.blind_status })), final: finalLabels() }
const LEDGER_SHA = sha256hex(canonicalJSON(LEDGER))
// per-part digests (top-level keys, and each version) so that a mismatch names the part to rewrite
// the ledger is written as small part files (top-level keys in order; one file per version), which round_gate.py assembles and checks part by part
const PART_VALUES = []
for (const k of Object.keys(LEDGER)) { if (k === 'versions') LEDGER.versions.forEach((v, i) => PART_VALUES.push([`versions.${i}`, v])); else PART_VALUES.push([k, LEDGER[k]]) }
const LEDGER_PARTS = Object.fromEntries(PART_VALUES.map(([k, v]) => [k, sha256hex(canonicalJSON(v)).slice(0, 16)]))
const PDIR = `${EVD}/review-verdicts/ledger.parts`
const SDA = ` --state-dir ${sq(STATE_DIR)}`
const ledgerCmd = gateCmd('assemble,ledger,freeze', ` --expect ${sq(JSON.stringify(EXPECT))} --ledger-sha ${LEDGER_SHA} --ledger-parts ${sq(JSON.stringify(LEDGER_PARTS))}` + SDA)
const partFiles = keys => PART_VALUES.filter(([k]) => keys.includes(k)).map(([k, v]) => `FILE ${PDIR}/${k}.json\n${JSON.stringify(v)}`).join('\n\n')
const ledgerPrompt = (sfx, keys, prev) => `Ledger step of round ${round}${sfx}.${A.resume_note ? ' Resume note: ' + A.resume_note + '.' : ''} ${keys.length === PART_VALUES.length ? `(1) Run exactly: ${gateCmd('copy,snapshot', ` --copy-from ${sq(RDIR)}` + SDA)}\nand put its last output line (starting "GATE ") in copy_line.` : '(1) Skip the copy (it succeeded before); put "skipped" in copy_line.'} (2) Write each of the following files with the Write tool, one call per file, with exactly the JSON given after its FILE line (no other change, no reformatting needed, nothing added):\n\n${partFiles(keys)}\n\n(3) Run exactly: ${ledgerCmd}\nand put its last output line (starting "GATE ") in ledger_line. Change no other file.${prev ? ' The previous attempt reported: ' + prev : ''}`
const ledgerOk = g => !!(g && g.assemble && !g.assemble.error && !g.assemble.missing.length && !g.assemble.unreadable.length && g.ledger && !g.ledger.error
  && g.ledger.mismatches === 0 && g.ledger.versions === EXPECT.versions.length && g.freeze && g.freeze.frozen === true)
let lo = await agent(ledgerPrompt('', PART_VALUES.map(([k]) => k), ''), { schema: LEDGER_OUT, phase: 'Write', label: 'ledger', effort: 'low' })
const lo0 = lo
let lg = lo && parseGate(lo.ledger_line)
if (!ledgerOk(lg)) {
  const named = lg && lg.ledger && Array.isArray(lg.ledger.differing_parts) ? lg.ledger.differing_parts.map(x => String(x).split(' ')[0]) : []
  const again = [...new Set([...named, ...((lg && lg.assemble && lg.assemble.missing) || []), ...((lg && lg.assemble && lg.assemble.unreadable) || [])])].filter(k => k in LEDGER_PARTS)
  lo = await agent(ledgerPrompt(' (retry)', again.length ? again : PART_VALUES.map(([k]) => k), lo ? cut(lo.ledger_line, 1500) : 'nothing'), { schema: LEDGER_OUT, phase: 'Write', label: 'ledger:retry', effort: 'low' })
  lg = lo && parseGate(lo.ledger_line)
}
if (!ledgerOk(lg)) return blocked(`ledger.json does not match the workflow's ledger: ${lg ? JSON.stringify({ assemble: lg.assemble, ledger: lg.ledger }) : 'no gate output'}`)
const copyOk = g => g && g.copy && !g.copy.error && g.snapshot && !g.snapshot.error
const cg = [lo, lo0].map(x => x && parseGate(x.copy_line)).find(copyOk)
if (!cg) return blocked(`copying the working material or the module snapshot failed: ${cut((lo0 || {}).copy_line, 600)}`)
if (cg.snapshot.matches_expected !== true) return blocked(`${MODULE} differs from the reference recorded in ${STATE_DIR}/expect.json (it changed outside a reviewed code change)`)
evidenceIgnored = cg.copy.ignored_by_git || []
if (evidenceIgnored.length) log(`git ignores ${cg.copy.ignored_count} copied evidence files; the caller must add them with git add -f: ${evidenceIgnored.join(', ')}`)
if (lg.ledger.warnings) log(`ledger: ${lg.ledger.warnings} warnings (reviewers' own verdict.json copies missing or different): ${JSON.stringify(lg.ledger.warning_list)}`)
log(`copied ${cg.copy.copied} files; frozen material ${lg.freeze.files} files recorded in ${STATE_DIR}/frozen.json`)

const anyNumbers = allReviews.some(r => r.claim.numbers.length > 0)
const ctxForWriter = { original_obstacle: ctx.original_obstacle, obstacle: ctx.obstacle, well_posed: ctx.well_posed, critique: ctx.critique, template: ctx.template, hidden_dependencies: ctx.hidden_dependencies, closed_form_plausible: ctx.closed_form_plausible, why_it_matters: ctx.why_it_matters }
const writePrompt = `You write the record of research round ${round} under protocol v5.1 (${PROTOCOL} §7–§9). Repository root ${ROOT}. The ledger is ${EVD}/review-verdicts/ledger.json (every reviewed version with its verdicts and labels, the final labels, the claims not reviewed, rewrites given up, code changes, attack outcomes); the copied working material is under ${EVD}/ (problem/, route*/, review/, rewrite/, code/). That material and review-verdicts/ are FROZEN: never edit, move or delete anything in them. Problem statement: ${JSON.stringify(ctxForWriter)}.
Every step REPLACES what an earlier attempt of this round wrote (same heading, same lines, same test names), else adds; nothing is duplicated.
(1) ${EVD}/detailed-record.md: the full A–F record with the derivations (from the copied route files), every claim version with its verdicts (from ledger.json and the copied review/*/verdict.json), the rewrites given up and why, the code changes, the unfinished computations, and a final section "非阻断问题" (empty). The truth lenses' reasons and fixes as returned: ${JSON.stringify(VTEXT)}. If a verdict.json named in ledger.json is missing from the copy, say so; never create one.
(2) The compact "### ${round}" subsection of §9 of ${ARCHIVE} (Chinese, A–F, target ${RECORD_TARGET} characters, hard cap ${RECORD_HARD}; heading line exactly "### ${round}"; sub-headings only as #### or deeper; a tag you only mention goes in a code span on both sides, \`[E:x]\`): the six template items in short form; the ledger table with EVERY ledger entry (${JSON.stringify(ledger.map(c => ({ id: c.id, ledger_status: c.ledger_status })))}): for reviewed claims id, final version, truth label (独立复核 / 已驳回 / 候选) and v4 label, one-sentence statement, scope = the premises copied VERBATIM from ledger.json, does-not-claim copied VERBATIM, applicability note = the applicability lens verdict (for 'gap' name each premise it lists; say whether the consequence follows); entries not reviewed are 未审 / 作者自驳 / 排除（数字来自未完成计算） / 排除（数字无来源） / 超额未收 with a one-line statement and never stated as established; blind_status 'audit_failed' carries the phrase 盲重实现未确认（隔离审计失败）, 'missing' the phrase 盲重实现缺席; a claim reviewed at an earlier code epoch than the last applied code change says so; at most 5 headline numbers per claim, each followed directly by [E:<evidence id>] with the printed value written just before the tag; what was and was not solved against the obstacle's own criterion; the decision implication no stronger than the truth labels AND the applicability notes; decisions for the user; plan changes ('none' if none); next attack; a process note (unfinished computations, rewrites given up, code changes${A.resume_note ? ', and this resume note: ' + A.resume_note : ''}).
(3) §7 of the archive: 独立复核 claims go to 已证明 (label 独立复核) with a deterministic pytest case named test_goal_${pyid(round)}_<lowercase id with non-alphanumerics as _>; others to 候选 / 反例与错误 / 已淘汰路线 / a 未审 line; rewrite 最近的关键缺口 and 下一轮攻击; never delete history of earlier rounds.
(4) Those pytest cases in ${TESTS} (seeded or exact, < 20 s each). To ${MODULE} you may only ADD new functions a test needs; never change or remove an existing line (the gate compares it with the review-time snapshot).
(5) ${EVD}/evidence.json: {"round": "${round}", "environment": "<default environment>", "entries": [{"id", "printed" (a JSON string, exactly as the record prints it), "kind" (point|upper|lower|exact|count), "source" (repository-relative path of a COPIED working file under ${EVD_REL}/problem/, route<k>/, review/, rewrite/ or code/ — never a file you create), "locator" ({"json": [keys]} or {"regex": "...(value)...", "occurrence": k}), "conditions", "environment" (if it differs from the default), "claim" and "number" (the ledger id and number name, for every number that is a claim's number)}]} with one entry per [E:...] tag in the subsection and per number in the rewritten §7 lines. Run "${VERIFY_CMD}" until its verifier part shows every entry passing; remove a number rather than cite another source.
(6) Run "${TEST_CMD}" and return its last line in tests_tail; return the verifier's last line in verifier_tail and the number of entries in evidence_entries.
Allowed files: ${ARCHIVE}, ${TESTS}, ${MODULE} (additions only), ${EVD}/ outside the frozen material. ${RULES}`
w = await agent(writePrompt, { schema: WRITE, phase: 'Write', label: 'write' })
if (!w) w = await agent(writePrompt, { schema: WRITE, phase: 'Write', label: 'write:retry' })
if (!w) return blocked('write agent returned nothing twice')

// ---------------------------------------------------------------------------------------------------------- Audit gate
phase('Audit')
const GATE_PARTS = ['verifier', 'pytest', 'ledger', 'record', 'frozen', 'module', 'scope']
fullGateCmd = gateCmd(GATE_PARTS.join(','), ` --expect ${sq(JSON.stringify(EXPECT))} --ledger-sha ${LEDGER_SHA} --ledger-parts ${sq(JSON.stringify(LEDGER_PARTS))}` + SDA)
const blk = (where, problem, fix) => ({ severity: 'blocking', where, problem, fix })
function gateIssues(g) {
  if (!g) return [blk('mechanical gate', 'round_gate.py output missing or unparsable', 'rerun the gate')]
  const out = []
  const isObj = x => !!x && typeof x === 'object' && !Array.isArray(x)
  const SHAPE = { verifier: ['passed', 'total'], pytest: ['passed', 'failed', 'errors', 'exit'], ledger: ['versions', 'mismatches', 'warnings'], record: ['headings', 'chars', 'inner_headings', 'bad_tag_count'], frozen: ['files'], module: ['violations'], scope: ['count'] }
  for (const k of GATE_PARTS) {                                     // every requested part must be there, complete, and without error
    const x = g[k]
    if (!isObj(x)) { out.push(blk(`gate part ${k}`, 'missing from the gate line', 'rerun the gate and copy its last line verbatim')); continue }
    if (x.error) { out.push(blk(`gate part ${k}`, x.error, 'fix what the part needs')); continue }
    const bad = SHAPE[k].filter(f => !Number.isInteger(x[f]))
    if (k === 'frozen' && typeof x.unchanged !== 'boolean') bad.push('unchanged')
    if (k === 'scope' && typeof x.head_moved !== 'boolean') bad.push('head_moved')
    if (bad.length) out.push(blk(`gate part ${k}`, `incomplete: ${bad.join(', ')}`, 'rerun the gate and copy its last line verbatim'))
  }
  if (out.length) return out
  const v = g.verifier, p = g.pytest, l = g.ledger, rec = g.record
  if (v && !v.error && (v.total < 0 || v.passed !== v.total || (anyNumbers && v.total === 0))) out.push(blk('evidence verifier', `${v.passed}/${v.total} entries pass${anyNumbers && v.total === 0 ? ' (empty table while reviewed claims carry numbers)' : ''}: ${JSON.stringify(v.failures)}`, 'fix evidence.json or the printed numbers'))
  if (p && !p.error && (p.failed || p.errors || !(p.passed > 0) || p.exit !== 0 || p.summary_found === false)) out.push(blk('pytest', p.tail, 'make the suite pass'))
  if (p && !p.error && baselinePassed !== null && p.passed < baselinePassed) out.push(blk('pytest', `${p.passed} tests pass, fewer than the ${baselinePassed} before the round`, 'restore the removed or broken tests'))
  if (l && !l.error && (l.mismatches !== 0 || l.versions !== EXPECT.versions.length)) out.push(blk('ledger', JSON.stringify(l.problems), 'make ledger.json carry exactly the workflow\'s versions and labels'))
  if (rec && !rec.error) {
    if (rec.headings !== 1) out.push(blk('record', `${rec.headings} "### ${round}" headings in the archive`, 'keep exactly one'))
    if (rec.inner_headings) out.push(blk('record', `${rec.inner_headings} ##/### headings inside the ${round} subsection`, 'use #### (or deeper) for its sub-headings'))
    if (!(rec.chars > 0) || rec.chars > RECORD_HARD) out.push(blk('record length', `§9 ${round} subsection has ${rec.chars} characters (cap ${RECORD_HARD})`, 'move detail to detailed-record.md'))
    if (rec.bad_tag_count) out.push(blk('evidence tags', JSON.stringify(rec.bad_tags), 'tag only numbers whose evidence entry exists, with the printed value just before the tag'))
  }
  if (g.frozen.unchanged !== true) out.push(blk('frozen material', `the frozen material differs from the reference recorded in ${STATE_DIR}/frozen.json at the ledger step`, 're-run the gate once; if it persists, undo the edits to problem/, route*/, review/, rewrite/, code/ or review-verdicts/ (git diff and the scratch copies show what changed)'))
  if (g.module.violations !== 0) out.push(blk('module', g.module.violations < 0 ? 'review-time snapshot missing' : `the module changed after review: ${JSON.stringify(g.module.details)}`, 'after review only add new functions or classes (and imports) to the module'))
  if (g.scope.count) out.push(blk('scope', `changed outside the allowed files, or baseline files changed: ${JSON.stringify(g.scope.out_of_scope)}`, 'restore those files to their state before the round'))
  if (g.scope.head_moved) out.push(blk('scope', `HEAD moved during the round (now ${g.scope.head})`, 'nothing may be committed during a round; undo the commit'))
  if (l && !l.error && l.warnings) out.push({ severity: 'minor', where: 'ledger', problem: `reviewers' own verdict.json copies: ${JSON.stringify(l.warning_list)}`, fix: 'note in detailed-record.md' })
  return out
}
const auditors = (pass, sfx) => [
  () => agent(`Mechanical gate (pass ${pass}${sfx}). Run exactly this command and return its LAST output line (it starts with "GATE ") verbatim in gate_line; run nothing else and change no file. ${LONG}\n${fullGateCmd}`, { schema: GATE_LINE, phase: 'Audit', label: `gate:p${pass}${sfx}`, effort: 'low' }),
  () => agent(`Overreach reviewer (pass ${pass}${sfx}) of §9 "### ${round}" and the ${round} lines of §7 of ${ARCHIVE}, against ${EVD}/review-verdicts/ledger.json (final labels ${JSON.stringify(finalLabels())}; applicability notes limit what the claims mean for the design). Blocking: a sentence stronger than its claim or its applicability note, a dropped premise on a headline claim, a label above its truth label, an unreviewed claim stated as established, a misreport of what a reviewer found, a number that carries no [E:...] tag (labels, formula symbols and counts of claims excepted). Minor: wording or citation details. Do not modify files.`, { schema: ISSUES, phase: 'Audit', label: `overreach:p${pass}${sfx}` }),
  () => agent(`Label, template and history checker (pass ${pass}${sfx}) of §9 "### ${round}" and §7 of ${ARCHIVE}, against ${EVD}/review-verdicts/ledger.json. Blocking if: a label differs from ${JSON.stringify(finalLabels())}; any of the ledger entries ${JSON.stringify(ledger.map(c => ({ id: c.id, ledger_status: c.ledger_status })))} is missing or carries a wrong status; one of the six template items (decision; inputs and their generating mechanism; model class; property and quantifiers; success/failure criterion; out of scope) is missing; a reviewed claim's scope or does-not-claim cell differs from its premises / does_not_claim in ledger.json; a claim with blind_status audit_failed lacks 盲重实现未确认（隔离审计失败） or one with missing lacks 盲重实现缺席; decisions for the user or plan changes are not listed; history of earlier rounds was deleted from §7 or §9 (compare with "git -C ${ROOT} show HEAD:docs/research/sycophancy-phase0-goal.md"); a 独立复核 claim lacks its pytest case in ${TESTS}; ${EVD}/detailed-record.md is missing. Do not modify files.`, { schema: ISSUES, phase: 'Audit', label: `check:p${pass}${sfx}` }),
]
let clean = false, repairs = 0, stopReason = null
for (let pass = 1; pass <= MAX_REPAIRS + 1; pass++) {
  let res = await parallel(auditors(pass, ''))
  const missingIdx = res.map((x, i) => x ? -1 : i).filter(i => i >= 0)
  if (missingIdx.length) {                                         // one retry for missing auditors; still missing => blocked
    const again = await parallel(missingIdx.map(i => auditors(pass, ':retry')[i]))
    missingIdx.forEach((i, j) => { res[i] = again[j] })
  }
  if (res.some(x => !x)) { audits.push({ pass, missing: ['gate', 'overreach', 'check'].filter((_, i) => !res[i]) }); lastBlocking = [blk('audit', 'an auditor returned nothing after a retry', 'rerun the round from cache')]; stopReason = 'an auditor returned nothing after a retry'; break }
  const g = parseGate(res[0].gate_line)
  const found = [...gateIssues(g), ...res[1].issues, ...res[2].issues]
  lastBlocking = found.filter(i => i.severity === 'blocking')
  found.filter(i => i.severity === 'minor').forEach(i => { const key = `${i.where}|${i.problem}`; if (!minorSeen.has(key)) minorSeen.set(key, { ...i, first_pass: pass }) })
  audits.push({ pass, blocking: lastBlocking, minor: found.filter(i => i.severity === 'minor').length, gate: g ? { verifier: g.verifier && `${g.verifier.passed}/${g.verifier.total}`, pytest: g.pytest && g.pytest.tail, record_chars: g.record && g.record.chars } : null })
  log(`audit pass ${pass}: ${lastBlocking.length} blocking, ${found.length - lastBlocking.length} minor`)
  if (!lastBlocking.length) { clean = true; break }
  if (repairs >= MAX_REPAIRS) { stopReason = `blocking issues remain after ${repairs} repairs`; break }
  repairs++
  const repairPrompt = sfx => `Repair ${repairs}${sfx} of the ${round} record. Fix every BLOCKING issue and the quick minor ones: ${JSON.stringify(found)}. The round as it stands: report ${JSON.stringify(w)}; final labels ${JSON.stringify(finalLabels())}. Never raise a label; never edit the frozen material (${EVD}/problem, route*, review, rewrite, code, review-verdicts); never revert a change that predates the round; to ${MODULE} only additions; keep "${VERIFY_CMD}" and "${TEST_CMD}" passing; log the changes under "修复日志" at the end of ${EVD}/detailed-record.md. Return the WRITE object for the WHOLE round after your repair: the full A–F report, every decision for the user and every plan change (unchanged ones included), cumulative files_changed, and fresh verifier and pytest tails. Allowed files: ${ARCHIVE}, ${TESTS}, ${MODULE} (additions), ${EVD}/ outside the frozen material. ${RULES}`
  let rep = await agent(repairPrompt(''), { schema: WRITE, phase: 'Audit', label: `repair:${repairs}` })
  if (!rep) rep = await agent(repairPrompt(' (retry)'), { schema: WRITE, phase: 'Audit', label: `repair:${repairs}:retry` })
  if (!rep) { lastBlocking = [...lastBlocking, blk('repair', `repair ${repairs} returned nothing twice; files may be partly repaired`, 'rerun the round from cache')]; stopReason = `repair ${repairs} returned nothing twice`; break }
  w = { ...rep, decisions_for_user: rep.decisions_for_user.length ? rep.decisions_for_user : w.decisions_for_user, plan_changes: rep.plan_changes.length ? rep.plan_changes : w.plan_changes, files_changed: [...new Set([...(w.files_changed || []), ...(rep.files_changed || [])])] }
}
let minorLogged = null
if (clean && minorSeen.size) {                                     // non-blocking issues of every pass go into the repository, one by one
  const minors = [...minorSeen.values()]
  const logPrompt = sfx => `Append these non-blocking issues${sfx}, one bullet each (with the pass that found them; a later repair may already have addressed some), to the section "非阻断问题" at the end of ${EVD}/detailed-record.md and change nothing else: ${JSON.stringify(minors)}. Return appended=true and the files you changed.`
  let lg2 = await agent(logPrompt(''), { schema: LOGGED, phase: 'Audit', label: 'log-minor', effort: 'low' })
  if (!lg2 || !lg2.appended) lg2 = await agent(logPrompt(' (retry)'), { schema: LOGGED, phase: 'Audit', label: 'log-minor:retry', effort: 'low' })
  minorLogged = !!(lg2 && lg2.appended)
  if (lg2) w = { ...w, files_changed: [...new Set([...(w.files_changed || []), ...(lg2.files_changed || [])])] }
  if (!minorLogged) log('the non-blocking issues could not be written to detailed-record.md; they are in open_minor_issues for the caller to record')
  // the append is the last change: the mechanical gate runs once more on the final state
  const gf = await auditors('final', '')[0]()
  const fin = gateIssues(gf && parseGate(gf.gate_line)).filter(i => i.severity === 'blocking')
  audits.push({ pass: 'final', blocking: fin })
  if (fin.length) { clean = false; lastBlocking = fin; stopReason = 'the mechanical gate failed after the non-blocking issues were logged' }
}
return { ...state(), status: clean ? 'ready_to_commit' : 'blocked', reason: clean ? null : stopReason || 'audit incomplete', minor_issues_logged: minorLogged }
