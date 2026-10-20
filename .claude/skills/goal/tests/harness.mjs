// Runs .claude/workflows/goal-round.js (the real file) with stub agents, one scenario at a time (round-protocol v5.1 §9.11).
import fs from 'fs'
import { fileURLToPath } from 'url'
const SCRIPT = process.argv[2] || fileURLToPath(new URL('../../../workflows/goal-round.js', import.meta.url))
const src = fs.readFileSync(SCRIPT, 'utf8').replace(/^export const meta =/m, 'const meta =')
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor
const body = new AsyncFunction('args', 'agent', 'parallel', 'pipeline', 'phase', 'log', src)

const ROOT = '/repo', SCR = '/scr', RD = `${SCR}/rT`
const H = (n) => 'a'.repeat(64 - String(n).length) + n
const tmpl = { decision: 'd', inputs_and_their_generating_mechanism: 'i', model_class_or_compatible_set: 'm', property_and_quantifiers: 'p', success_failure_criterion: 's', out_of_scope: 'x' }
const route = n => ({ name: n, tools: '', core_claim: '', how_it_implies: '', failure_point: '', cheapest_check: '' })
const num1 = (src = `${RD}/route1/out.json`) => ({ name: 'x', value: '1', kind: 'point', source: src, conditions: 'c', environment: 'py3.11' })
const claim = (k, extra = {}) => ({ author_id: 'C' + k, kind: 'theorem', statement: 'S' + k, premises: 'P' + k, numbers: [num1()], derivation_md: 'd', script_path: `${RD}/route1/s.py`, uses_module: false, does_not_claim: 'n', consequence: 'q', author_status: 'proved', ...extra })
const okT = files => ({ refuted: false, severity: 'none', reason: 'ok', fix: '', strongest_attack_tried: 'a', reproduced_numbers: true, files_read: files })
const badT = (sev, fix = 'narrow it') => ({ refuted: true, severity: sev, reason: sev, fix, strongest_attack_tried: 'a', reproduced_numbers: false, files_read: ['/repo/m.py'] })
const ap = sev => ({ severity: sev, premises_not_holding: sev === 'gap' ? ['clustering'] : [], note: 'n', consequence_follows: sev === 'none' })
const own = (id, va, lens = 'blind_replication') => `${RD}/review/${id}_${va.replace("a", "_a")}_${lens}`
function gate(over = {}) {
  const g = { verifier: { passed: 3, total: 3, failures: [] }, pytest: { passed: 120, failed: 0, errors: 0, exit: 0, tail: '120 passed in 9s', summary_found: true },
    ledger: { versions: over.versions ?? 0, mismatches: 0, warnings: 0, problems: [], warning_list: [] }, record: { headings: 1, chars: 9000, inner_headings: 0, tags: 3, bad_tags: [], bad_tag_count: 0 },
    frozen: { hash: H(1), files: 10, unchanged: true }, module: { violations: 0, details: [] }, scope: { out_of_scope: [], count: 0, head_moved: false, head: 'abc' } }
  for (const [k, v] of Object.entries(over)) if (k !== 'versions') g[k] = typeof v === 'object' && v !== null && !Array.isArray(v) && typeof g[k] === 'object' ? { ...g[k], ...v } : v
  return 'GATE ' + JSON.stringify(g)
}
const defaults = {
  baseline: () => ({ gate_line: 'GATE ' + JSON.stringify({ baseline: { count: 1, head: 'abc', file: '/scr/rT.state/baseline.json', sha256: H(7) }, pytest: { passed: 120, failed: 0, errors: 0, exit: 0, tail: '120 passed', summary_found: true }, hashes: { module_sha: H(3), tests_sha: H(4) }, fresh: { scratch_entries: 0, evidence_entries: 0 } }) }),
  backup: (p, ctx) => ({ gate_line: 'GATE ' + JSON.stringify({ backup: { created: ['module.orig', 'tests.orig'], module_sha: ctx.module, tests_sha: ctx.tests, module_now: ctx.module, tests_now: ctx.tests, matches_expected: ctx.module === ctx.expect && ctx.tests === ctx.expectTests } }) }),
  codecheck: (p, ctx) => { ctx.module = H(5); ctx.tests = H(6); return { gate_line: 'GATE ' + JSON.stringify({ hashes: { module_sha: H(5), tests_sha: H(6), module_changed: ctx.module !== ctx.expect, matches_expected: ctx.module === ctx.expect }, pytest: { passed: 121, failed: 0, errors: 0, exit: 0, tail: '121 passed', summary_found: true } }) } },
  accept: (p, ctx) => { ctx.expect = ctx.module; ctx.expectTests = ctx.tests; return { gate_line: 'GATE ' + JSON.stringify({ accept: { accepted: true } }) } },
  problem: () => ({ original_obstacle: 'o', well_posed: true, critique: 'c', template: tmpl, hidden_dependencies: [], closed_form_plausible: 'no', obstacle: 'O', why_it_matters: 'w', routes: [route('A'), route('B')], do_not_repeat: [], constraints: '' }),
  'attack:route1': () => ({ outcome: 'progress', claims: [claim(1)], unfinished_computations: [], what_failed: '', next_step: '' }),
  'attack:route2': () => ({ outcome: 'dead_end', claims: [], unfinished_computations: [], what_failed: 'x', next_step: '' }),
  review: (id, va, lens) => lens === 'applicability' ? ap('gap') : okT(lens === 'blind_replication' ? [own(id, va) + '/check.py'] : ['/repo/m.py']),
  ledger: (p, ctx) => ({ copy_line: 'GATE ' + JSON.stringify({ copy: { copied: 5, skipped: [], ignored_by_git: [], ignored_count: 0 }, snapshot: { path: 'p', sha256: ctx.module, matches_expected: ctx.module === ctx.expect } }), ledger_line: LEDGER_OK(ctx.expectVersions(p)) }),
  write: () => ({ report_AF_md: 'R', decisions_for_user: ['d1'], plan_changes: [], evidence_entries: 3, verifier_tail: '3/3 entries pass', tests_tail: '120 passed', files_changed: ['a'] }),
  gate: (p, ctx) => ({ gate_line: gate({ versions: ctx.expectVersions(p) }) }),
  overreach: () => ({ issues: [] }), check: () => ({ issues: [] }),
  rewrite: () => null, code: () => null, repair: () => null,
  restore: (p, ctx) => { ctx.module = ctx.expect; ctx.tests = ctx.expectTests; return { gate_line: 'GATE ' + JSON.stringify({ restore: { restored: true, module_sha: ctx.module, tests_sha: ctx.tests, matches_expected: true } }) } },
  'log-minor': () => ({ appended: true, files_changed: ['detailed-record.md'] }),
}
export async function run(name, stubs, args = {}) {
  const calls = [], logs = [], prompts = {}
  const S = { ...defaults, ...stubs }
  const ctx = { expectVersions: p => { const m = /--expect '(\{.*?\})'/.exec(p); return m ? JSON.parse(m[1]).versions.length : -1 }, calls, prompts, module: H(3), tests: H(4), expect: H(3), expectTests: H(4) }
  const agent = async (prompt, opts) => {
    const L = opts.label; calls.push(L); prompts[L] = prompt
    const [head, ...rest] = L.split(':')
    let f = S[L] || S[head]
    if (!f) throw new Error('no stub for ' + L)
    if (head === 'review') { const [id, va, lens] = rest; return f(id, va, lens, prompt, ctx) }
    return f(prompt, ctx, rest)
  }
  const parallel = async t => Promise.all(t.map(f => f().catch(e => { logs.push('THREW ' + e.message); return null })))
  const pipeline = async (xs, ...st) => Promise.all(xs.map(async (x, i) => { let v = x; try { for (const s of st) v = await s(v, x, i); return v } catch (e) { logs.push('stage threw ' + e.message); return null } }))
  let out, err = null
  try { out = await body({ round: 'rT', root: ROOT, scratch: SCR, python: '/py', ...args }, agent, parallel, pipeline, () => {}, m => logs.push(m)) } catch (e) { err = e }
  return { name, out, err, calls, logs, prompts }
}
const RESTORED = 'GATE ' + JSON.stringify({ restore: { restored: true, module_sha: H(3), tests_sha: H(4), matches_expected: true } })
function LEDGER_OK(versions) { return 'GATE ' + JSON.stringify({ assemble: { parts: 12, missing: [], unreadable: [] }, ledger: { versions, mismatches: 0, warnings: 0, problems: [], differing_parts: [] }, freeze: { hash: H(1), files: 10, frozen: true } }) }
// the ledger the script hands to the ledger agent, rebuilt from its FILE parts in manifest order
function ledgerParts(p) {                     // [key, value] in prompt order; a part's JSON ends at the next real newline
  const out = [], re = /(?:^|\n)FILE \S+\/ledger\.parts\/(\S+)\.json\n/g
  let m
  while ((m = re.exec(p))) { const start = re.lastIndex, end = p.indexOf('\n', start); out.push([m[1], JSON.parse(p.slice(start, end < 0 ? p.length : end))]) }
  return out
}
function ledgerFromPrompt(p) {
  const led = {}
  for (const [k, v] of ledgerParts(p)) { if (k.startsWith('versions.')) (led.versions = led.versions || []).push(v); else led[k] = v }
  return led
}
const codeOk = (over = {}) => () => ({ restore_line: RESTORED, applied: true, summary: 's', ...over })
export { claim, okT, badT, ap, own, gate, num1, RD, H, route, tmpl, codeOk, RESTORED, LEDGER_OK, ledgerFromPrompt, ledgerParts }
