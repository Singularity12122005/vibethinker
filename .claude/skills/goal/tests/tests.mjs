// Stub suite for goal-round.js and its cross-checks with round_gate.py (round-protocol v5.1 §9.11).
// Run from the repository root:  PYTHON=<python with numpy> node .claude/skills/goal/tests/tests.mjs
import { run, claim, okT, badT, ap, own, gate, num1, RD, H, route, tmpl, codeOk, RESTORED, LEDGER_OK, ledgerFromPrompt, ledgerParts } from './harness.mjs'
import fs from 'fs'
import os from 'os'
import path from 'path'
import { fileURLToPath } from 'url'
import { execFileSync } from 'child_process'
const TMP = prefix => fs.mkdtempSync(path.join(os.tmpdir(), prefix))
const results = []
const check = (name, cond, info = '') => { results.push([name, !!cond]); console.log(`${cond ? 'PASS' : 'FAIL'}  ${name}${cond ? '' : '  ' + info}`) }
const lbl = r => r.out && r.out.truth_labels ? r.out.truth_labels.map(t => `${t.id}:${t.truth_label}:${t.blind_status}`).join(',') : 'none'
const PY = process.env.PYTHON || 'python3', GATE = process.env.GATE || fileURLToPath(new URL('../round_gate.py', import.meta.url))
// cross-check the JS decision rule with round_gate.py's on the ledger the script hands to the ledger agent
function pyLedgerCheck(r, mutate) {
  const p = r.prompts['ledger']
  const root = TMP('goalround-py-')
  const pdir = `${root}/docs/research/goal-rounds/rT/review-verdicts/ledger.parts`
  fs.mkdirSync(pdir, { recursive: true })
  const parts = ledgerParts(p)
  if (mutate) { const led = ledgerFromPrompt(p); mutate(led); parts.length = 0; for (const k of Object.keys(led)) { if (['versions', 'not_reviewed'].includes(k) && led[k].length) led[k].forEach((v, i) => parts.push([`${k}.${i}`, v])); else parts.push([k, led[k]]) } }
  for (const [k, v] of parts) fs.writeFileSync(`${pdir}/${k}.json`, JSON.stringify(v, null, 1))
  const cmd = /--expect '(\{.*?\})' --ledger-sha ([0-9a-f]{64}) --ledger-parts '(\{.*?\})'/.exec(p)
  const out = execFileSync(PY, [GATE, root, 'rT', '--module', 'm.py', '--only', 'assemble,ledger', '--expect', cmd[1], '--ledger-sha', cmd[2], '--ledger-parts', cmd[3]]).toString().trim().split('\n').pop()
  fs.rmSync(root, { recursive: true })
  const g = JSON.parse(out.slice(5))
  return { ...g.ledger, assemble: g.assemble }
}

// S1 happy path
let r = await run('S1', {})
check('S1 ready_to_commit', r.out && r.out.status === 'ready_to_commit', JSON.stringify(r.err || r.out && r.out.reason))
check('S1 labels', lbl(r) === 'R1-1:独立复核:ok', lbl(r))
check('S1 v4 label candidate (applicability gap)', r.out.truth_labels[0].v4_label === '候选')
let pl = pyLedgerCheck(r); check('S1 python ledger check agrees', pl.mismatches === 0 && pl.versions === 1, JSON.stringify(pl))
pl = pyLedgerCheck(r, led => { led.versions[0].truth_label = '候选' }); check('S1 python ledger check catches a changed label', pl.mismatches > 0)
pl = pyLedgerCheck(r, led => { led.versions[0].verdicts.blind_replication.files_read.push('/scr/rT/route1/attack.json') }); check('S1 python check catches a changed files_read', pl.mismatches > 0)
pl = pyLedgerCheck(r, led => { led.versions[0].premises = 'P1 (premise dropped)' }); check('S1 python check catches a changed premise (sha) and names versions.0', pl.mismatches === 1 && /canonical sha256/.test(pl.problems[0]) && /differing parts: \['versions\.0'\]/.test(pl.problems[0]), JSON.stringify(pl))
pl = pyLedgerCheck(r, led => { led.not_reviewed = [] }); check('S1 python check names a top-level part', /differing parts: \['not_reviewed'\]/.test(pl.problems[0]) || pl.mismatches === 0, JSON.stringify(pl))
pl = pyLedgerCheck(r, led => { led.versions[0].verdicts.applicability.note = 'edited' }); check('S1 python check catches an edited applicability note (sha)', pl.mismatches === 1)
check('S1 writer prompt has template', r.prompts.write.includes('inputs_and_their_generating_mechanism'))
check('S1 gate gets the state dir and the ledger references', r.prompts['gate:p1'].includes("--state-dir '/scr/rT.state'") && /--ledger-sha [0-9a-f]{64} --ledger-parts '/.test(r.prompts['gate:p1']) && r.out.gate_command === r.prompts['gate:p1'].split('\n').pop())

// S2 isolation: bad blind paths fail the audit; process re-run once on the same text
const BAD = id => [own(id, 'v1a1') + '/../../route1/attack.json', '/scr//rT/route1/s.py', '/scr/./rT/route1/s.py', '/scr/r3/review/x/verdict.json',
  '/repo/docs/research/sycophancy-phase0-goal.md', '/other/checkout/docs/research/goal-rounds/r4/ledger.json', '/root/.claude/projects/p/s/tool-results/x.txt',
  '/tmp/claude-0/s/tasks/a123.output', '/tmp/claude-0/s/tasks/b9.output', 'relative/file.py', '~/x.py', own(id, 'v1a1') + '/.']
for (const bad of BAD('R1-1')) {
  r = await run('S2', { review: (id, va, lens) => lens === 'applicability' ? ap('none') : okT(lens === 'blind_replication' ? (va === 'v1a1' ? [own(id, va) + '/c.py', bad] : [own(id, va) + '/c.py']) : ['/repo/m.py']) })
  const v = r.out && r.out.versions
  check(`S2 bad path ${bad} -> audit_failed then re-run ok`, v && v.length === 2 && v[0].blind_status === 'audit_failed' && v[0].truth_label === '候选' && v[1].review_reason === 'process_rerun' && v[1].truth_label === '独立复核', JSON.stringify(v) + JSON.stringify(r.err && r.err.message))
  if (bad.includes('/../')) { pl = pyLedgerCheck(r); check('S2 python agrees on the audit (.. path)', pl.mismatches === 0, JSON.stringify(pl)) }
}
for (const good of [own('R1-1', 'v1a1'), own('R1-1', 'v1a1') + '/', '/repo/sycophancy_phase0/src/m.py']) {
  r = await run('S2g', { review: (id, va, lens) => lens === 'applicability' ? ap('none') : okT(lens === 'blind_replication' ? [good] : ['/repo/m.py']) })
  check(`S2 good path ${good} accepted`, r.out.versions.length === 1 && r.out.versions[0].blind_status === 'ok', JSON.stringify(r.out.versions))
}
r = await run('S2e', { review: (id, va, lens) => lens === 'applicability' ? ap('none') : okT([]) })
check('S2 empty files_read fails, re-run once only', r.out.versions.length === 2 && r.out.versions.every(v => v.blind_status === 'audit_failed'), JSON.stringify(r.out.versions))
check('S2 audit_failed phrase rule in writer prompt', r.prompts.write.includes('盲重实现未确认（隔离审计失败）') && r.prompts.write.includes('盲重实现缺席'))

// S3 blocked after 3 repairs keeps the blocking list
r = await run('S3', { gate: (p, ctx) => ({ gate_line: gate({ versions: ctx.expectVersions(p), verifier: { passed: 2, total: 3, failures: ['FAIL x'] } }) }), repair: () => ({ report_AF_md: 'R2', decisions_for_user: [], plan_changes: [], evidence_entries: 3, verifier_tail: '', tests_tail: '', files_changed: ['b'] }) })
check('S3 blocked with list and reason', r.out.status === 'blocked' && r.out.open_blocking_issues.length === 1 && /after 3 repairs/.test(r.out.reason) && r.calls.filter(c => c.startsWith('repair:')).length === 3, JSON.stringify([r.out.status, r.out.reason, r.out.open_blocking_issues]))
check('S3 decisions kept when repair returns none', JSON.stringify(r.out.write.decisions_for_user) === '["d1"]')

// S4 log-minor fails twice: still ready, flagged
r = await run('S4', { overreach: () => ({ issues: [{ severity: 'minor', where: 'w', problem: 'p', fix: 'f' }] }), 'log-minor': () => null })
check('S4 ready but minor not logged', r.out.status === 'ready_to_commit' && r.out.minor_issues_logged === false && r.out.open_minor_issues.length === 1 && r.calls.includes('log-minor:retry'), JSON.stringify([r.out.status, r.out.minor_issues_logged]))

// S5 code route variants
const codeClaim = claim(1, { kind: 'code_fact', uses_module: true })
const gapMath = (id, va, lens) => lens === 'applicability' ? ap('none') : (lens === 'math' && va === 'v1a1') ? badT('gap', 'make it an interface fact') : okT(lens === 'blind_replication' ? [own(id, va) + '/c.py'] : ['/repo/m.py'])
const rw = (over = {}) => () => ({ possible: true, claim: { ...codeClaim, statement: 'S1-code' }, changes: [{ field: 'statement', change: 'c', from_lens: 'math' }, { field: 'code', change: 'c', from_lens: 'math' }], code_change: 'add a guard', ...over })
r = await run('S5a', { 'attack:route1': () => ({ outcome: 'progress', claims: [codeClaim], unfinished_computations: [], what_failed: '', next_step: '' }), review: gapMath, rewrite: rw({ code_change: '' }) })
check('S5a code field without code_change -> given up', r.out.gave_up.length === 1 && /without a code_change/.test(r.out.gave_up[0].reason) && !r.calls.some(c => c.startsWith('code:')), JSON.stringify(r.out.gave_up))
const one = { 'attack:route1': () => ({ outcome: 'progress', claims: [codeClaim], unfinished_computations: [], what_failed: '', next_step: '' }), review: gapMath, rewrite: rw() }
const G = o => () => ({ gate_line: 'GATE ' + JSON.stringify(o) })
r = await run('S5b', { ...one, code: codeOk(), codecheck: G({ hashes: { module_sha: H(5), tests_sha: H(6), module_changed: true }, pytest: { passed: 119, failed: 0, errors: 2, exit: 1, tail: '119 passed, 2 errors', summary_found: true } }) })
check('S5b measured "2 errors" -> restore -> reverted, given up', r.calls.includes('restore:R1-1:v2') && r.out.code_changes[0].outcome === 'reverted' && r.out.gave_up.length === 1 && r.out.status === 'ready_to_commit', JSON.stringify([r.out.code_changes, r.out.reason]))
r = await run('S5c', { ...one, code: () => null, restore: G({ restore: { restored: false, error: 'x' } }) })
check('S5c restore fails twice -> blocked', r.out.status === 'blocked' && /could not be restored/.test(r.out.reason) && r.calls.includes('restore:R1-1:v2:retry'), JSON.stringify(r.out.reason))
r = await run('S5e', { ...one, backup: () => null })
check('S5e backup fails -> given up, no code agent', !r.calls.some(c => c.startsWith('code:')) && /backed up/.test(r.out.gave_up[0].reason))
r = await run('S5f', { ...one, code: codeOk(), codecheck: G({ hashes: { module_sha: H(3), tests_sha: H(4), module_changed: false }, pytest: { passed: 120, failed: 0, errors: 0, exit: 0, tail: '120 passed', summary_found: true } }) })
check('S5f "applied" but module unchanged -> reverted', r.out.code_changes[0].outcome === 'reverted')
r = await run('S5g', { ...one, backup: G({ backup: { created: [], module_sha: H(3), tests_sha: H(4), module_now: H(9), tests_now: H(4), matches_expected: false } }), code: codeOk() })
check('S5g module differs from the recorded reference at backup -> blocked, nothing restored', r.out.status === 'blocked' && /recorded in/.test(r.out.reason) && !r.calls.some(c => c.startsWith('restore:') || c.startsWith('code:')), JSON.stringify([r.out.reason, r.calls.slice(-3)]))
r = await run('S5i', { ...one, backup: () => null })
check('S5i backup agent fails twice -> given up', r.calls.includes('backup:R1-1:v2:retry') && /backed up/.test(r.out.gave_up[0].reason))
r = await run('S5m', { ...one, code: codeOk(), accept: () => null })
check('S5m accept cannot be recorded -> blocked', r.out.status === 'blocked' && /could not be recorded/.test(r.out.reason) && r.calls.includes('accept:R1-1:v2:retry'))
r = await run('S5j', { ...one, code: codeOk({ restore_line: 'GATE ' + JSON.stringify({ restore: { restored: false, matches_expected: false, error: 'no backup' } }) }) })
check('S5j code agent whose first restore failed -> change not accepted, restored, reverted', r.out.code_changes[0].outcome === 'reverted' && r.calls.includes('restore:R1-1:v2'), JSON.stringify(r.out.code_changes))
r = await run('S5k', { ...one, code: codeOk({ restore_line: 'step skipped' }) })
check('S5k code agent that skipped the restore -> reverted', r.out.code_changes[0].outcome === 'reverted')
// resume after a kill during the code agent: the cached backup line says module_now == backup, the live code agent's restore line is what counts
r = await run('S5l', { ...one, code: (p) => ({ restore_line: RESTORED, applied: true, summary: p.includes('--only restore --backup-dir') ? 'restored first, then applied' : 'NO RESTORE IN PROMPT' }) })
check('S5l the code agent prompt starts with the restore command', r.out.code_changes[0].outcome === 'applied' && r.out.code_changes[0].summary === 'restored first, then applied', JSON.stringify(r.out.code_changes))
r = await run('S5h', { ...one, code: codeOk(), codecheck: G({ hashes: { module_sha: H(5), tests_sha: H(6), module_changed: true }, pytest: { passed: 100, failed: 0, errors: 0, exit: 0, tail: '100 passed', summary_found: true } }) })
check('S5h fewer tests than the baseline -> reverted', r.out.code_changes[0].outcome === 'reverted')
r = await run('S5d', { 'attack:route1': () => ({ outcome: 'progress', claims: [codeClaim, claim(2, { kind: 'code_fact', uses_module: true })], unfinished_computations: [], what_failed: '', next_step: '' }), review: (id, va, lens) => id === 'R1-2' ? (lens === 'applicability' ? ap('none') : okT(lens === 'blind_replication' ? [own(id, va) + '/c.py'] : ['/repo/m.py'])) : gapMath(id, va, lens), rewrite: rw(), code: codeOk() })
const reasons = r.out.versions.map(v => `${v.id}v${v.version}a${v.attempt}:${v.review_reason}:${v.truth_label}`).join(',')
check('S5d code applied, v2 reviewed, other ok code_fact re-reviewed as stale', reasons === 'R1-1v1a1:first:候选,R1-2v1a1:first:独立复核,R1-1v2a1:rewrite:独立复核,R1-2v1a2:stale_after_code_change:独立复核', reasons)
check('S5d code change recorded', r.out.code_changes.length === 1 && r.out.code_changes[0].outcome === 'applied' && r.out.code_changes[0].epoch === 1)
pl = pyLedgerCheck(r); check('S5d python ledger agrees', pl.mismatches === 0 && pl.versions === 4, JSON.stringify(pl))

// S6 undeclared and empty rewrites
const gap1 = (id, va, lens) => lens === 'applicability' ? ap('none') : (lens === 'math' && va === 'v1a1') ? badT('gap') : okT(lens === 'blind_replication' ? [own(id, va) + '/c.py'] : ['/repo/m.py'])
r = await run('S6a', { review: gap1, rewrite: () => ({ possible: true, claim: { ...claim(1), statement: 'STRONGER' }, changes: [{ field: 'consequence', change: 'c', from_lens: 'applicability' }], code_change: '' }) })
check('S6a undeclared statement change rejected', r.out.gave_up.length === 1 && /undeclared change of statement/.test(r.out.gave_up[0].reason), JSON.stringify(r.out.gave_up))
r = await run('S6b', { review: gap1, rewrite: () => ({ possible: true, claim: claim(1), changes: [{ field: 'statement', change: 'c', from_lens: 'math' }], code_change: '' }) })
check('S6b nothing changed rejected', r.out.gave_up.length === 1 && /nothing changed/.test(r.out.gave_up[0].reason), JSON.stringify(r.out.gave_up))
r = await run('S6c', { review: gap1, rewrite: () => ({ possible: true, claim: { ...claim(1), premises: 'P1 narrower' }, changes: [{ field: 'premises', change: 'c', from_lens: 'applicability' }], code_change: '' }) })
check('S6c premises from applicability rejected', r.out.gave_up.length === 1 && /applicability/.test(r.out.gave_up[0].reason))
r = await run('S6d', { review: gap1, rewrite: () => ({ possible: true, claim: { ...claim(1), premises: 'P1 narrower' }, changes: [{ field: 'premises', change: 'c', from_lens: 'math' }], code_change: '' }) })
check('S6d legitimate narrowing re-reviewed', r.out.versions.length === 2 && r.out.versions[1].review_reason === 'rewrite' && r.out.truth_labels[0].version === 2, JSON.stringify(r.out.versions))

// S7 ledger statuses: unfinished by basename, unsourced, over cap, author-refuted
const c7 = [claim(1, { numbers: [num1(`${RD}/route1/stage2.json`)] }), claim(2, { numbers: [num1('/elsewhere/out.json')] }), claim(3, { author_status: 'refuted' }), claim(4), claim(5), claim(6), claim(7)]
r = await run('S7', { 'attack:route1': () => ({ outcome: 'partial', claims: c7, unfinished_computations: [{ description: 'stage2.json (stage 2 of the scan) still running', output_paths: [] }], what_failed: '', next_step: '' }) })
const st = r.out.ledger.map(c => `${c.id}:${c.ledger_status}`).join(',')
check('S7 ledger statuses', st === 'R1-1:excluded_unfinished,R1-2:excluded_unsourced,R1-3:author_refuted,R1-4:reviewed,R1-5:reviewed,R1-6:reviewed,R1-7:dropped_over_cap', st)

// S8 null/'' args give defaults; same-named routes each get a slot
r = await run('S8', { problem: () => ({ original_obstacle: 'o', well_posed: true, critique: 'c', template: tmpl, hidden_dependencies: [], closed_form_plausible: 'no', obstacle: 'O', why_it_matters: 'w', routes: [route('A'), route('A')], do_not_repeat: [], constraints: '' }),
  'attack:route1': () => ({ outcome: 'progress', claims: [claim(1), claim(2), claim(3)], unfinished_computations: [], what_failed: '', next_step: '' }),
  'attack:route2': () => ({ outcome: 'progress', claims: [claim(4, { numbers: [num1(`${RD}/route2/o.json`)] })], unfinished_computations: [], what_failed: '', next_step: '' }) }, { max_claims: null, fix_rounds: '', max_routes: null })
const st8 = r.out.ledger.map(c => `${c.id}:${c.ledger_status}`).join(',')
check('S8 defaults (3 claims) and per-route slots', st8 === 'R1-1:reviewed,R1-2:reviewed,R1-3:unreviewed_overflow,R2-1:reviewed', st8)

// S9 empty evidence table while numbers exist; frozen/module/scope/headings/test-count blocking
const variants = { empty_table: { verifier: { passed: 0, total: 0 } }, frozen: { frozen: { unchanged: false } }, module: { module: { violations: 3, details: ['x'] } }, snapshot_missing: { module: { violations: -1, details: [] } }, scope: { scope: { out_of_scope: ['.claude/x'], count: 1 } },
  headings: { record: { headings: 2 } }, long: { record: { chars: 13500 } }, tags: { record: { bad_tag_count: 1, bad_tags: ['x'] } }, fewer_tests: { pytest: { passed: 100, tail: '100 passed' } }, errors: { pytest: { errors: 2, tail: '118 passed, 2 errors' } }, part_error: { scope: { error: 'git failed' } } }
for (const [k, over] of Object.entries(variants)) {
  let n = 0
  r = await run('S9' + k, { gate: (p, ctx) => ({ gate_line: gate({ versions: ctx.expectVersions(p), ...(n++ === 0 ? over : {}) }) }), repair: () => ({ report_AF_md: 'R2', decisions_for_user: ['d1'], plan_changes: [], evidence_entries: 3, verifier_tail: '', tests_tail: '', files_changed: [] }) })
  check(`S9 ${k} blocks pass 1, clean after repair`, r.out.audits[0].blocking.length >= 1 && r.out.status === 'ready_to_commit' && r.calls.includes('repair:1'), JSON.stringify(r.out.audits[0]))
}
for (const [k, g] of Object.entries({ empty: {}, ledger_only: { ledger: { versions: 1, mismatches: 0, warnings: 0 } }, module_number: null, no_head_moved: null, short_hash: null })) {
  r = await run('S9p' + k, { gate: (p, ctx) => {
    if (g) return { gate_line: 'GATE ' + JSON.stringify(g) }
    const o = JSON.parse(gate({ versions: ctx.expectVersions(p) }).slice(5))
    if (k === 'module_number') o.module = 0
    if (k === 'no_head_moved') delete o.scope.head_moved
    if (k === 'short_hash') delete o.frozen.unchanged
    return { gate_line: 'GATE ' + JSON.stringify(o) } }, repair: () => ({ report_AF_md: 'R2', decisions_for_user: ['d1'], plan_changes: [], evidence_entries: 3, verifier_tail: '', tests_tail: '', files_changed: [] }) })
  check(`S9 incomplete gate line (${k}) blocks every pass`, r.out.status === 'blocked' && r.out.audits.every(a => a.blocking.length > 0), JSON.stringify(r.out.audits[0]))
}
const vS9 = { head_moved: { scope: { head_moved: true, head: 'def' } }, no_summary: { pytest: { summary_found: false } } }
for (const [k, over] of Object.entries(vS9)) {
  let n = 0
  r = await run('S9' + k, { gate: (p, ctx) => ({ gate_line: gate({ versions: ctx.expectVersions(p), ...(n++ === 0 ? over : {}) }) }), repair: () => ({ report_AF_md: 'R2', decisions_for_user: ['d1'], plan_changes: [], evidence_entries: 3, verifier_tail: '', tests_tail: '', files_changed: [] }) })
  check(`S9 ${k} blocks pass 1`, r.out.audits[0].blocking.length >= 1 && r.out.status === 'ready_to_commit')
}
r = await run('S9unparsable', { gate: () => ({ gate_line: 'Traceback ...' }), repair: () => ({ report_AF_md: 'R2', decisions_for_user: ['d1'], plan_changes: [], evidence_entries: 3, verifier_tail: '', tests_tail: '', files_changed: [] }) })
check('S9 unparsable gate line blocks', r.out.status === 'blocked' && /unparsable/.test(JSON.stringify(r.out.open_blocking_issues)))

// S10 ledger mismatch twice -> blocked; ledger retry label distinct
r = await run('S10', { ledger: () => ({ copy_line: 'GATE ' + JSON.stringify({ copy: { copied: 1, ignored_by_git: [] }, snapshot: { path: 'p', matches_expected: true } }), ledger_line: 'GATE {"assemble":{"missing":[],"unreadable":[]},"ledger":{"versions":1,"mismatches":2,"problems":["x"],"differing_parts":["versions.0"]},"freeze":{"frozen":true}}' }) })
check('S10 ledger mismatch blocked after retry', r.out.status === 'blocked' && r.calls.includes('ledger:retry') && /ledger.json does not match/.test(r.out.reason), r.out.reason)
check('S10 the retry is given only the differing part', (r.prompts['ledger:retry'].match(/^FILE /gm) || []).length === 1 && r.prompts['ledger:retry'].includes('ledger.parts/versions.0.json') && /Skip the copy/.test(r.prompts['ledger:retry']))

// S11 early exits keep the full shape
r = await run('S11', { problem: () => null })
check('S11 problem null twice -> blocked with full shape', r.out.status === 'blocked' && r.calls.includes('problem:retry') && 'truth_labels' in r.out && 'open_blocking_issues' in r.out && 'gave_up' in r.out)
r = await run('S11b', { check: () => null })
check('S11b auditor missing twice -> blocked, retry label distinct', r.out.status === 'blocked' && r.calls.includes('check:p1:retry') && /auditor returned nothing/.test(r.out.reason), JSON.stringify([r.out.reason, r.calls.slice(-4)]))
r = await run('S11c', { baseline: () => null })
check('S11c no baseline -> blocked', r.out.status === 'blocked' && /baseline/.test(r.out.reason))

// S12 bad configuration throws
for (const a of [{ scratch: 'rel/dir' }, { scratch: '/tmp/a b' }, { scratch: '/repo/sub' }, { root: '/repo/./x' }, { round: '../x' }, { python: 'python3; rm -rf /' }, { module: '/elsewhere/m.py' }]) {
  r = await run('S12', {}, a)
  check(`S12 rejects ${JSON.stringify(a)}`, r.err && !r.out, r.err ? '' : 'did not throw')
}

// S13 severity wrong -> 已驳回; rewrite allowed from it
r = await run('S13', { review: (id, va, lens) => lens === 'applicability' ? ap('none') : (lens === 'math' && va === 'v1a1') ? badT('wrong', 'the bound holds only for m>=2') : okT(lens === 'blind_replication' ? [own(id, va) + '/c.py'] : ['/repo/m.py']),
  rewrite: () => ({ possible: true, claim: { ...claim(1), premises: 'P1, m>=2' }, changes: [{ field: 'premises', change: 'add m>=2', from_lens: 'math' }], code_change: '' }) })
check('S13 wrong -> 已驳回 then narrowed v2 独立复核', r.out.versions[0].truth_label === '已驳回' && r.out.truth_labels[0].truth_label === '独立复核' && r.out.truth_labels[0].version === 2, JSON.stringify(r.out.versions))

// S14 not reproduced (substantive) is NOT re-run
r = await run('S14', { review: (id, va, lens) => lens === 'applicability' ? ap('none') : lens === 'blind_replication' ? { ...okT([own(id, va) + '/c.py']), reproduced_numbers: false } : okT(['/repo/m.py']) })
check('S14 not reproduced stays 候选 without re-run', r.out.versions.length === 1 && r.out.truth_labels[0].truth_label === '候选')

// S15 process re-run after another claim's code change re-runs all lenses (kept verdicts predate the change)
r = await run('S15', { 'attack:route1': () => ({ outcome: 'progress', claims: [codeClaim, claim(2, { uses_module: true })], unfinished_computations: [], what_failed: '', next_step: '' }),
  review: (id, va, lens) => id === 'R1-2' ? (lens === 'blind_replication' && va === 'v1a1' ? null : lens === 'applicability' ? ap('none') : okT(lens === 'blind_replication' ? [own(id, va) + '/c.py'] : ['/repo/m.py'])) : gapMath(id, va, lens), rewrite: rw(), code: codeOk() })
const v15 = r.out.versions.find(v => v.id === 'R1-2' && v.attempt === 2)
check('S15 rerun after code change is full', v15 && v15.review_reason === 'process_rerun_after_code_change' && ['math', 'blind_replication', 'applicability'].every(l => r.calls.includes(`review:R1-2:v1a2:${l}`)), JSON.stringify(r.out.versions))
pl = pyLedgerCheck(r); check('S15 python ledger agrees', pl.mismatches === 0, JSON.stringify(pl))
// S15b same without any code change: blind only, others kept
r = await run('S15b', { 'attack:route1': () => ({ outcome: 'progress', claims: [claim(2, { uses_module: true })], unfinished_computations: [], what_failed: '', next_step: '' }),
  review: (id, va, lens) => lens === 'blind_replication' && va === 'v1a1' ? null : lens === 'applicability' ? ap('none') : okT(lens === 'blind_replication' ? [own(id, va) + '/c.py'] : ['/repo/m.py']) })
check('S15b rerun without code change runs the blind lens only', r.calls.includes('review:R1-1:v1a2:blind_replication') && !r.calls.includes('review:R1-1:v1a2:math') && r.out.truth_labels[0].truth_label === '独立复核')
// S16 rewrite citing an unfinished computation is rejected
r = await run('S16', { 'attack:route1': () => ({ outcome: 'partial', claims: [claim(1)], unfinished_computations: [{ description: 'stage 2', output_paths: [`${RD}/route1/stage2.json`] }], what_failed: '', next_step: '' }), review: gap1,
  rewrite: () => ({ possible: true, claim: { ...claim(1), numbers: [num1(`${RD}/route1/stage2.json`)] }, changes: [{ field: 'numbers', change: 'c', from_lens: 'math' }], code_change: '' }) })
check('S16 unfinished number in a rewrite rejected', r.out.gave_up.length === 1 && /unfinished/.test(r.out.gave_up[0].reason), JSON.stringify(r.out.gave_up))
// S17 uses_module cannot be dropped by a rewrite
r = await run('S17', { 'attack:route1': () => ({ outcome: 'progress', claims: [claim(1, { uses_module: true })], unfinished_computations: [], what_failed: '', next_step: '' }), review: gap1,
  rewrite: () => ({ possible: true, claim: { ...claim(1, { uses_module: false }), premises: 'P1 narrower' }, changes: [{ field: 'premises', change: 'c', from_lens: 'math' }], code_change: '' }) })
pl = ledgerFromPrompt(r.prompts.ledger)
check('S17 uses_module stays true', pl.versions[1].uses_module === true)
// S18 a 独立复核 claim with the applicability lens missing gets one applicability-only re-run
r = await run('S18', { review: (id, va, lens) => lens === 'applicability' ? (va === 'v1a1' ? null : ap('none')) : okT(lens === 'blind_replication' ? [own(id, va) + '/c.py'] : ['/repo/m.py']) })
check('S18 applicability re-run', r.calls.includes('review:R1-1:v1a2:applicability') && !r.calls.includes('review:R1-1:v1a2:math') && r.out.truth_labels[0].v4_label === '独立复核', JSON.stringify(r.out.truth_labels))
// S19 canonical ledger sha: JS == Python on awkward text
r = await run('S19', { 'attack:route1': () => ({ outcome: 'progress', claims: [claim(1, { statement: '界 ≤ 0.52 “引号” \u0007 \u007f 😀 \\ back\\slash "q"   end', premises: 'tab\there\nnewline' })], unfinished_computations: [], what_failed: '', next_step: '' }) })
{
  const p = r.prompts.ledger, json = JSON.stringify(ledgerFromPrompt(p)), sha = /--ledger-sha ([0-9a-f]{64})/.exec(p)[1]
  const root = TMP('goalround-sha-')
  fs.writeFileSync(`${root}/l.json`, json)
  const py = execFileSync(PY, ['-c', `import sys,json; sys.path.insert(0, ${JSON.stringify(GATE.replace(/\/[^/]+$/, ''))}); import round_gate as g; print(g.canonical_sha(json.load(open(sys.argv[1], encoding='utf-8'))))`, `${root}/l.json`]).toString().trim()
  fs.rmSync(root, { recursive: true })
  check('S19 JS and Python canonical sha agree', py === sha, py + ' vs ' + sha)
  pl = pyLedgerCheck(r); check('S19 full python ledger check with sha', pl.mismatches === 0, JSON.stringify(pl))
}
// S20 JS pathOk == Python path_ok on awkward inputs
{
  const src = fs.readFileSync(process.argv[2] || fileURLToPath(new URL('../../../workflows/goal-round.js', import.meta.url)), 'utf8')
  const grab = name => { const m = new RegExp(`^const ${name} = .*$`, 'm').exec(src); return m[0] }
  const fns = ['strip', 'BAD_CHARS', 'normalised', 'under'].map(grab).join('\n') + '\n' + /const pathOk = [\s\S]*?\n}\n/.exec(src)[0]
  const iso = { forbid_prefix: ['/scr', '/repo/docs/research/goal-rounds', '/repo/docs/research/sycophancy-phase0-goal.md'], forbid_sub: ['/docs/research/goal-rounds/', '/sycophancy-phase0-goal.md', '/.claude/projects/', '/subagents/', '/tool-results/'], forbid_re: ['\\/tasks\\/[^/]+\\.output$'] }
  const jsOk = new Function('FORBID_PREFIX', 'FORBID_SUB', 'FORBID_RE', fns + '\nreturn pathOk')(iso.forbid_prefix, iso.forbid_sub, iso.forbid_re.map(x => new RegExp(x)))
  const own = '/scr/rT/review/R1-1_v1_a1_blind_replication'
  const cases = ['/scr\u2060/rT/route1/attack.json', '/tmp/a\u00adb.py', '/tmp/a\u202eb.py', '/tmp/a\u2066b.py', '/tmp/a\u180eb.py', '/tmp/x/tasks/abc.output﻿', '/tmp/x/tasks/abc.output\u001c', '/tmp/x/tasks/abc.output\u0085', '/tmp/ok.py ', ' /tmp/ok.py', '/tmp/ok.py\n', '/tmp/a​b.py', own + '/x.py', own, '/scr/rT/route1/a.py', '/repo/src/m.py', '/tmp/ok.py/', '/tmp/./x', '/tmp/x/..']
  const owns = [own, '', undefined]
  const inputs = []
  for (const o of owns) for (const c of cases) inputs.push([c, o === undefined ? null : o])
  const py = JSON.parse(execFileSync(PY, ['-c', `import sys,json; sys.path.insert(0, ${JSON.stringify(GATE.replace(/\/[^/]+$/, ''))}); import round_gate as g; iso=json.loads(sys.argv[1]); print(json.dumps([g.path_ok(c, o, iso) for c, o in json.loads(sys.argv[2])]))`, JSON.stringify(iso), JSON.stringify(inputs)]).toString())
  const diffs = inputs.filter((x, i) => jsOk(x[0], x[1] === null ? undefined : x[1]) !== py[i])
  check('S20 JS pathOk equals Python path_ok on awkward inputs', diffs.length === 0, JSON.stringify(diffs))
}

// S21 a fresh run that finds an earlier run's scratch or evidence directory is blocked
r = await run('S21', { baseline: () => ({ gate_line: 'GATE ' + JSON.stringify({ baseline: { count: 0, head: 'abc', sha256: H(7) }, pytest: { passed: 120, failed: 0, errors: 0, exit: 0, tail: '120 passed', summary_found: true }, hashes: { module_sha: H(3), tests_sha: H(4) }, fresh: { scratch_entries: 12, evidence_entries: 0 } }) }) })
check('S21 reused round name blocked before any agent', r.out.status === 'blocked' && /used before/.test(r.out.reason) && !r.calls.includes('problem'), r.out.reason)
r = await run('S21b', { baseline: () => ({ gate_line: 'GATE ' + JSON.stringify({ baseline: { count: 0, head: 'abc', sha256: H(7) }, pytest: { passed: 0, failed: 0, errors: 0, exit: -1, tail: 'timeout after 3600 s', summary_found: false }, hashes: { module_sha: H(3), tests_sha: H(4) }, fresh: { scratch_entries: 0, evidence_entries: 0 } }) }) })
check('S21b baseline without a pytest summary -> retry -> blocked', r.out.status === 'blocked' && r.calls.includes('baseline:retry'))
// S22 an audit-failed blind verdict is re-run only if it would otherwise have passed
for (const [k, bv, want] of [['wrong', { refuted: true, severity: 'wrong', fix: '' }, '已驳回'], ['not_reproduced', { reproduced_numbers: false }, '候选'], ['gap_no_fix', { refuted: true, severity: 'gap', fix: '' }, '候选']]) {
  r = await run('S22' + k, { review: (id, va, lens) => lens === 'applicability' ? ap('none') : lens === 'blind_replication' ? { ...okT(['relative/x.py']), ...bv } : okT(['/repo/m.py']) })
  check(`S22 audit-failed blind ${k} is kept, not re-run`, r.out.versions.length === 1 && r.out.truth_labels[0].truth_label === want && r.out.truth_labels[0].blind_status === 'audit_failed', JSON.stringify(r.out.versions))
}
// S23 a theorem rewrite whose code_change says "No code change." is still re-reviewed
r = await run('S23', { review: gap1, rewrite: () => ({ possible: true, claim: { ...claim(1), premises: 'P1 narrower' }, changes: [{ field: 'premises', change: 'c', from_lens: 'math' }], code_change: 'No code change.' }) })
check('S23 free text in code_change ignored without a declared code change', r.out.versions.length === 2 && r.out.truth_labels[0].version === 2 && !r.calls.some(c => c.startsWith('backup:')), JSON.stringify(r.out.gave_up))
// S24 a ledger retry that does not rerun the copy keeps the first attempt's copy line
{
  let n = 0
  r = await run('S24', { ledger: (p, ctx) => n++ === 0 ? { copy_line: 'GATE ' + JSON.stringify({ copy: { copied: 5, ignored_by_git: [] }, snapshot: { path: 'p', matches_expected: true } }), ledger_line: 'GATE {"assemble":{"missing":["not_reviewed"],"unreadable":[]},"ledger":{"versions":1,"mismatches":1,"problems":["sha"],"differing_parts":[]},"freeze":{"frozen":true}}' }
    : { copy_line: 'skipped', ledger_line: LEDGER_OK(ctx.expectVersions(p)) } })
  check('S24 ledger retry uses the earlier copy line', r.out.status === 'ready_to_commit' && r.calls.includes('ledger:retry'), r.out.reason)
}
// S25 a finished out.json is not excluded because an unfinished computation mentions scan_out.json
r = await run('S25', { 'attack:route1': () => ({ outcome: 'partial', claims: [claim(1)], unfinished_computations: [{ description: 'the scan writing scan_out.json is still running', output_paths: [`${RD}/route1/scan_out.json`] }], what_failed: '', next_step: '' }) })
check('S25 file-name token match, not substring', r.out.ledger[0].ledger_status === 'reviewed', JSON.stringify(r.out.ledger))
// S26 unvetted fields and non-integer numbers never reach the ledger
r = await run('S26', { 'attack:route1': () => ({ outcome: 'progress', claims: [claim(1, { numbers: [{ ...num1(), value_numeric: 0.00003 }] })], unfinished_computations: [{ description: 'x', output_paths: [], eta_hours: 1.5e-7 }], what_failed: '', next_step: '' }) })
{ const led = ledgerFromPrompt(r.prompts.ledger)
  check('S26 ledger carries only schema fields', !JSON.stringify(led).includes('value_numeric') && !JSON.stringify(led).includes('eta_hours'))
  pl = pyLedgerCheck(r); check('S26 python ledger agrees', pl.mismatches === 0, JSON.stringify(pl)) }
// S27 the module must not change outside a reviewed code change
r = await run('S27', { ledger: (p, ctx) => ({ copy_line: 'GATE ' + JSON.stringify({ copy: { copied: 5, ignored_by_git: [] }, snapshot: { path: 'p', matches_expected: false } }), ledger_line: LEDGER_OK(ctx.expectVersions(p)) }) })
check('S27 snapshot differs from the recorded module -> blocked', r.out.status === 'blocked' && /outside a reviewed code change/.test(r.out.reason), r.out.reason)
// S28 ##/### headings inside the round subsection block
{ let n = 0
  r = await run('S28', { gate: (p, ctx) => ({ gate_line: gate({ versions: ctx.expectVersions(p), ...(n++ === 0 ? { record: { inner_headings: 1 } } : {}) }) }), repair: () => ({ report_AF_md: 'R2', decisions_for_user: ['d1'], plan_changes: [], evidence_entries: 3, verifier_tail: '', tests_tail: '', files_changed: [] }) })
  check('S28 inner heading blocks pass 1', r.out.audits[0].blocking.some(b => /headings inside/.test(b.problem))) }
// S29 git-ignored evidence: the full list is returned
r = await run('S29', { ledger: (p, ctx) => ({ copy_line: 'GATE ' + JSON.stringify({ copy: { copied: 60, ignored_by_git: Array.from({ length: 60 }, (_, i) => `e/build/m${i}.json`), ignored_count: 60 }, snapshot: { path: 'p', matches_expected: true } }), ledger_line: LEDGER_OK(ctx.expectVersions(p)) }) })
check('S29 all 60 ignored evidence files returned', r.out.evidence_ignored_by_git.length === 60)

// S30 a process failure in the last fix round's review still gets its one re-run
r = await run('S30', { review: (id, va, lens) => lens === 'applicability' ? ap('none') : (lens === 'math' && va === 'v1a1') ? badT('gap') : (lens === 'blind_replication' && va === 'v2a1') ? null : okT(lens === 'blind_replication' ? [own(id, va) + '/c.py'] : ['/repo/m.py']),
  rewrite: () => ({ possible: true, claim: { ...claim(1), premises: 'P1 narrower' }, changes: [{ field: 'premises', change: 'c', from_lens: 'math' }], code_change: '' }) })
check('S30 v2 blind missing -> re-run after the fix rounds -> 独立复核', r.out.versions.map(v => `${v.version}a${v.attempt}:${v.review_reason}`).join(',') === '1a1:first,2a1:rewrite,2a2:process_rerun' && r.out.truth_labels[0].truth_label === '独立复核', JSON.stringify(r.out.versions))
// S31 a substantive negative is not worth a truth-lens re-run; a missing applicability lens still is
r = await run('S31', { review: (id, va, lens) => lens === 'applicability' ? (va === 'v1a1' ? null : ap('none')) : lens === 'math' ? badT('gap', '') : (va === 'v1a1' ? null : okT([own(id, va) + '/c.py'])) })
check('S31 math gap without fix + blind missing: only applicability re-run', r.calls.includes('review:R1-1:v1a2:applicability') && !r.calls.includes('review:R1-1:v1a2:blind_replication') && r.out.truth_labels[0].truth_label === '候选', JSON.stringify(r.calls.filter(c => c.startsWith('review'))))
// S32 the mechanical gate runs once more after the non-blocking issues are logged
{ let n = 0
  r = await run('S32', { overreach: () => ({ issues: [{ severity: 'minor', where: 'w', problem: 'p', fix: 'f' }] }), gate: (p, ctx) => ({ gate_line: gate({ versions: ctx.expectVersions(p), ...(n++ === 1 ? { verifier: { passed: 2, total: 3 } } : {}) }) }) })
  check('S32 final gate after log-minor blocks a broken state', r.out.status === 'blocked' && /after the non-blocking issues were logged/.test(r.out.reason) && r.calls.includes('gate:pfinal'), JSON.stringify([r.out.reason, r.calls.slice(-3)])) }
r = await run('S32b', { overreach: () => ({ issues: [{ severity: 'minor', where: 'w', problem: 'p', fix: 'f' }] }) })
check('S32b final gate clean -> ready', r.out.status === 'ready_to_commit' && r.calls.includes('gate:pfinal'))
// S33 ledger parts stay small for realistic content (no part has to be typed in one huge call)
{ const long = n => 'x'.repeat(n)
  const big = k => claim(k, { statement: long(600), premises: long(1500), does_not_claim: long(400), consequence: long(600), derivation_md: long(8000) })
  r = await run('S33', { problem: () => ({ original_obstacle: 'o', well_posed: true, critique: 'c', template: tmpl, hidden_dependencies: [], closed_form_plausible: 'no', obstacle: 'O', why_it_matters: 'w', routes: [route('A'), route('B'), route('C')], do_not_repeat: [], constraints: '' }),
    'attack:route1': () => ({ outcome: 'progress', claims: [1, 2, 3, 4, 5, 6].map(big), unfinished_computations: [], what_failed: long(2000), next_step: long(2000) }),
    'attack:route2': () => ({ outcome: 'progress', claims: [7, 8, 9, 10, 11, 12].map(k => ({ ...big(k), numbers: [num1(`${RD}/route2/o.json`)] })), unfinished_computations: [], what_failed: long(2000), next_step: long(2000) }),
    'attack:route3': () => ({ outcome: 'progress', claims: [13, 14, 15, 16].map(k => ({ ...big(k), numbers: [num1(`${RD}/route3/o.json`)] })), unfinished_computations: [], what_failed: long(2000), next_step: long(2000) }),
    review: (id, va, lens) => lens === 'applicability' ? { ...ap('gap'), note: long(3000) } : { ...okT(lens === 'blind_replication' ? [own(id, va) + '/c.py'] : ['/repo/m.py']), reason: long(4000), fix: long(2000) } }, { max_claims: 6 })
  const sizes = ledgerParts(r.prompts.ledger).map(([k, v]) => [k, JSON.stringify(v).length])
  const total = sizes.reduce((a, [, n]) => a + n, 0), maxp = Math.max(...sizes.map(([, n]) => n))
  console.log(`      S33 ledger: ${sizes.length} parts, total ${total} chars, largest ${maxp} (${sizes.find(([, n]) => n === maxp)[0]})`)
  check('S33 largest ledger part under 8000 characters with 16 long claims and long verdicts', maxp < 8000 && r.prompts.write.includes('reasons and fixes as returned'), String(maxp)) }
// S34 a resume note re-runs the ledger step live
r = await run('S34', {}, { resume_note: 'resumed after a restart' })
check('S34 resume note reaches the ledger prompt', r.prompts.ledger.includes('Resume note: resumed after a restart'))

// S35 a round that reviews nothing (honest dead ends) passes the ledger step
r = await run('S35', { 'attack:route1': () => ({ outcome: 'dead_end', claims: [], unfinished_computations: [], what_failed: 'x', next_step: 'y' }) })
check('S35 dead-end round: ready, empty versions part', r.out.status === 'ready_to_commit' && ledgerParts(r.prompts.ledger).some(([k, v]) => k === 'versions' && Array.isArray(v) && !v.length), r.out.reason)
pl = pyLedgerCheck(r); check('S35 python assembles an empty versions list', pl.mismatches === 0 && pl.versions === 0, JSON.stringify(pl))
r = await run('S35b', { 'attack:route1': () => ({ outcome: 'partial', claims: [claim(1, { author_status: 'refuted' })], unfinished_computations: [], what_failed: '', next_step: '' }) })
pl = pyLedgerCheck(r); check('S35b only an author-refuted claim: ledger agrees', r.out.status === 'ready_to_commit' && pl.mismatches === 0, JSON.stringify(pl))
// S36 unreviewed claims are one part each; a slip in one is retried alone
r = await run('S36', { 'attack:route1': () => ({ outcome: 'progress', claims: [1, 2, 3, 4, 5].map(k => claim(k)), unfinished_computations: [], what_failed: '', next_step: '' }) }, { max_claims: 1 })
{ const keys = ledgerParts(r.prompts.ledger).map(([k]) => k)
  check('S36 not_reviewed split per entry', ['not_reviewed.0', 'not_reviewed.3'].every(k => keys.includes(k)) && !keys.includes('not_reviewed'), keys.join(','))
  pl = pyLedgerCheck(r); check('S36 python assembles the split list', pl.mismatches === 0, JSON.stringify(pl))
  pl = pyLedgerCheck(r, led => { led.not_reviewed[2].statement = 'slip' }); check('S36 python names the one differing entry', /differing parts: \['not_reviewed\.2'\]/.test(pl.problems[0]), JSON.stringify(pl)) }
// S37 cutting never splits a surrogate pair
r = await run('S37', { review: (id, va, lens) => lens === 'applicability' ? { ...ap('gap'), note: 'x'.repeat(599) + '\u{1D53C}' + 'y'.repeat(30) } : okT(lens === 'blind_replication' ? [own(id, va) + '/c.py'] : ['/repo/m.py']) })
{ const note = ledgerFromPrompt(r.prompts.ledger).versions[0].verdicts.applicability.note
  check('S37 cut by code points', note.endsWith('\u{1D53C}…') && !/[\ud800-\udbff](?![\udc00-\udfff])/.test(note), JSON.stringify(note.slice(-4)))
  pl = pyLedgerCheck(r); check('S37 python ledger agrees', pl.mismatches === 0, JSON.stringify(pl)) }
// S38 a ledger line missing the assemble lists goes to the retry instead of throwing
{ let n = 0
  r = await run('S38', { ledger: (p, ctx) => n++ === 0 ? { copy_line: 'GATE ' + JSON.stringify({ copy: { copied: 5, ignored_by_git: [] }, snapshot: { path: 'p', matches_expected: true } }), ledger_line: 'GATE {"assemble":{"parts":12,"unreadable":[]},"ledger":{"versions":1,"mismatches":0},"freeze":{"frozen":true}}' }
    : { copy_line: 'skipped', ledger_line: LEDGER_OK(ctx.expectVersions(p)) } })
  check('S38 malformed ledger line retried', !r.err && r.out.status === 'ready_to_commit' && r.calls.includes('ledger:retry'), String(r.err)) }
// S39 the final gate pass is retried once when its agent returns nothing
{ let n = 0
  r = await run('S39', { overreach: () => ({ issues: [{ severity: 'minor', where: 'w', problem: 'p', fix: 'f' }] }), gate: (p, ctx) => (n++ === 1 ? null : { gate_line: gate({ versions: ctx.expectVersions(p) }) }) })
  check('S39 final gate retried', r.out.status === 'ready_to_commit' && r.calls.includes('gate:pfinal:retry'), JSON.stringify([r.out.reason, r.calls.slice(-3)])) }

const failed = results.filter(x => !x[1]).length
console.log(`${results.length - failed}/${results.length} checks pass`)
process.exit(failed ? 1 : 0)
