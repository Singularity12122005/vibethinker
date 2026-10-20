"""End-to-end test of round_gate.py in a throwaway git repository (round-protocol v5.1 §9.11).

Run:  python .claude/skills/goal/tests/gate_e2e.py [path/to/round_gate.py]   (python with pytest installed)
"""
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path
GATE = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parent.parent / 'round_gate.py'); PY = sys.executable
fails = 0
def check(name, cond, info=''):
    global fails
    fails += not cond
    print(('PASS' if cond else 'FAIL'), name, '' if cond else info)
def run(root, *a):
    out = subprocess.run([PY, GATE, str(root), 'rT', '--module', 'pkg/m.py', *a], capture_output=True, text=True)
    line = out.stdout.strip().splitlines()[-1]
    assert line.startswith('GATE '), out.stdout + out.stderr
    return json.loads(line[5:])
def git(root, *a): subprocess.run(['git', '-C', str(root), '-c', 'user.email=a@b', '-c', 'user.name=a', *a], check=True, capture_output=True)
base = Path(tempfile.mkdtemp(prefix='goalround-e2e-'))
root, scr, state = base / 'repo', base / 'scr' / 'rT', base / 'scr' / 'rT.state'
(root / 'pkg').mkdir(parents=True); (root / 'sycophancy_phase0' / 'tests').mkdir(parents=True); (root / 'docs/research').mkdir(parents=True)
MOD = 'import numpy as np\n\nPD_RTOL = 1e-9\n\n\ndef f(x):\n    """Doc.\n\n    Notes\n    -----\n    text\n    """\n    y = x + 1\n    return y\n'
(root / 'pkg/m.py').write_text(MOD)
(root / 'sycophancy_phase0/tests/test_analysis.py').write_text('def test_a():\n    assert True\n')
(root / 'sycophancy_phase0/conftest.py').write_text('import atexit, sys\natexit.register(lambda: print("warning: leaked semaphore", file=sys.stderr))\n')
(root / 'docs/research/sycophancy-phase0-goal.md').write_text('# A\n## 9\n### r3\nold\n')
(root / 'other.txt').write_text('x'); (root / 'notes.txt').write_text('committed notes')
(root / '.gitignore').write_text('build/\n__pycache__/\n')
git(root, 'init', '-q'); git(root, 'add', '.'); git(root, 'commit', '-qm', 'i')
(root / 'other.txt').write_text('dirty before the round'); (root / 'notes.txt').write_text('user edit before the round')
g = run(root, '--only', 'baseline,pytest', '--state-dir', str(state))
bl = json.loads((state / 'baseline.json').read_text())
check('baseline file: both dirty files with hashes and HEAD', sorted(p['path'] for p in bl['paths']) == ['notes.txt', 'other.txt'] and bl['head'] and g['baseline']['count'] == 2, g)
check('pytest counted despite stderr after the summary', g['pytest']['passed'] == 1 and g['pytest']['summary_found'], g['pytest'])
bsha = g['baseline']['sha256']
g = run(root, '--only', 'baseline', '--state-dir', str(root / 'inside'))
check('state dir inside the repository rejected', 'error' in g['baseline'], g)
# scratch material, including extensionless, .orig, .sh and a binary
for rel, txt in [('problem/problem.json', '{}'), ('route1/attack.json', '{}'), ('route1/out.json', '{"v": 0.41942966, "w": 0.95}'), ('route1/Makefile', 'all:\n'), ('route1/run.sh', 'echo\n'),
                 ('code/R1-1_v2/module.orig', MOD), ('route1/build/tv.json', '{"x": 1}'),
                 ('review/R1-1_v1_a1_blind_replication/verdict.json', json.dumps({'refuted': False, 'severity': 'none', 'reproduced_numbers': True, 'files_read': ['/x']}))]:
    (scr / rel).parent.mkdir(parents=True, exist_ok=True); (scr / rel).write_text(txt)
(scr / 'route1/arr.npy').write_bytes(b'\x93NUMPY\x00\x01')
g = run(root, '--only', 'copy,snapshot', '--copy-from', str(scr))
evd = root / 'docs/research/goal-rounds/rT'
check('copy by content: extensionless, .sh, .orig copied; binary skipped', g['copy']['copied'] == 8 and g['copy']['skipped'] == ['route1/arr.npy'], g['copy'])
check('copy reports git-ignored evidence', g['copy']['ignored_by_git'] == ['docs/research/goal-rounds/rT/route1/build/tv.json'], g['copy'])
# ledger + sha
sys.path.insert(0, str(Path(GATE).parent)); import round_gate as rg
iso = {'forbid_prefix': [str(base / 'scr')], 'forbid_sub': ['/tool-results/'], 'forbid_re': [r'\/tasks\/[^/]+\.output$']}
own = str(scr / 'review/R1-1_v1_a1_blind_replication')
ver = {'id': 'R1-1', 'version': 1, 'attempt': 1, 'premises': 'n>=2 and no clustering', 'verdicts': {'math': {'refuted': False, 'severity': 'none', 'reproduced_numbers': True, 'files_read': []}, 'blind_replication': {'refuted': False, 'severity': 'none', 'reproduced_numbers': True, 'files_read': ['/x'], 'review_dir': own}, 'applicability': None}, 'truth_label': '独立复核', 'v4_label': '候选', 'blind_status': 'ok', 'missing_lenses': ['applicability']}
led = {'scratch_round_dir': str(scr), 'evidence_dir': 'docs/research/goal-rounds/rT', 'isolation': iso, 'versions': [ver], 'final': [{'id': 'R1-1', 'version': 1, 'attempt': 1, 'truth_label': '独立复核', 'v4_label': '候选', 'blind_status': 'ok'}]}
(evd / 'review-verdicts').mkdir(); (evd / 'review-verdicts/ledger.json').write_text(json.dumps(led, ensure_ascii=False, indent=2))
exp = json.dumps({'versions': [{'id': 'R1-1', 'version': 1, 'attempt': 1, 'truth_label': '独立复核', 'v4_label': '候选', 'blind_status': 'ok'}], 'final': [{'id': 'R1-1', 'version': 1, 'attempt': 1, 'truth_label': '独立复核'}]}, ensure_ascii=False)
LSHA = rg.canonical_sha(led)
g = run(root, '--only', 'ledger,frozen', '--expect', exp, '--ledger-sha', LSHA)
check('ledger agrees incl. sha (pretty-printed file)', g['ledger']['mismatches'] == 0 and g['ledger']['versions'] == 1, g['ledger'])
H0 = g['frozen']['hash']
led2 = json.loads(json.dumps(led)); led2['versions'][0]['premises'] = 'n>=2'
(evd / 'review-verdicts/ledger.json').write_text(json.dumps(led2, ensure_ascii=False))
g = run(root, '--only', 'ledger,frozen', '--expect', exp, '--ledger-sha', LSHA)
check('dropped premise caught by sha and by the frozen hash', g['ledger']['mismatches'] == 1 and g['frozen']['hash'] != H0, g['ledger'])
(evd / 'review-verdicts/ledger.json').write_text(json.dumps(led, ensure_ascii=False, indent=2))
check('decide without review_dir: own dir test skipped', rg.decide({'math': ver['verdicts']['math'], 'blind_replication': {**ver['verdicts']['blind_replication'], 'review_dir': None, 'files_read': [str(scr / 'route1/attack.json')]}}, iso)['blind_status'] == 'audit_failed')
# record, evidence and full gate
arch = root / 'docs/research/sycophancy-phase0-goal.md'
arch.write_text(arch.read_text() + '### rT\n界 0.4194 [E:B1.h]，误用 0.95 [E:B1.w9] 和 10.9 [E:B1.w9]，引用 `[E:zz]`\n### r9\nx\n')
(evd / 'headline.json').write_text('{"v": 0.9}')
entries = [{'id': 'B1.h', 'printed': '0.4194', 'kind': 'lower', 'source': 'docs/research/goal-rounds/rT/route1/out.json', 'locator': {'json': ['v']}, 'conditions': 'c'},
           {'id': 'B1.w9', 'printed': '0.9', 'kind': 'point', 'source': 'docs/research/goal-rounds/rT/headline.json', 'locator': {'json': ['v']}, 'conditions': 'c'}]
(evd / 'evidence.json').write_text(json.dumps({'round': 'rT', 'environment': 'py', 'entries': entries}))
g = run(root, '--only', 'verifier,record')
check('writer-created source rejected by the verifier', g['verifier']['passed'] == 1 and g['verifier']['total'] == 2, g['verifier'])
check('tag value must be a whole number token (0.9 vs 0.95 and 10.9)', g['record']['tags'] == 3 and g['record']['bad_tag_count'] == 2, g['record'])
entries[1] = {'id': 'B1.w9', 'printed': '0.95', 'kind': 'point', 'source': 'docs/research/goal-rounds/rT/route1/out.json', 'locator': {'json': ['w']}, 'conditions': 'c'}
(evd / 'evidence.json').write_text(json.dumps({'round': 'rT', 'environment': 'py', 'entries': entries}))
arch.write_text(arch.read_text().replace('和 10.9 [E:B1.w9]', ''))
(evd / 'headline.json').unlink()
(root / 'pkg/m.py').write_text(MOD + '\n\ndef g():\n    return 2\n\n\nimport scipy\n')
(root / 'sycophancy_phase0/tests/test_analysis.py').write_text('def test_a():\n    assert True\n\ndef test_goal_rt_r1_1():\n    assert True\n')
g = run(root, '--expect', exp, '--ledger-sha', LSHA, '--state-dir', str(state), '--baseline-sha', bsha)
check('verifier passes', g['verifier']['passed'] == 2 and g['verifier']['total'] == 2, g['verifier'])
check('pytest 2 passed', g['pytest']['passed'] == 2, g['pytest'])
check('record clean', g['record']['headings'] == 1 and g['record']['bad_tag_count'] == 0, g['record'])
check('frozen unchanged', g['frozen']['hash'] == H0)
check('module: new function and new import allowed', g['module']['violations'] == 0, g['module'])
check('scope clean, HEAD unchanged', g['scope']['count'] == 0 and g['scope']['head_moved'] is False, g['scope'])
check('wrong baseline sha -> scope error', 'error' in run(root, '--only', 'scope', '--state-dir', str(state), '--baseline-sha', '0' * 64)['scope'])
# module mutations
def mod_violations(text):
    (root / 'pkg/m.py').write_text(text); return run(root, '--only', 'module')['module']['violations']
check('module: early return inserted into a reviewed function', mod_violations(MOD.replace('    y = x + 1\n', '    return -1\n    y = x + 1\n')) > 0)
check('module: reviewed function redefined later', mod_violations(MOD + '\n\ndef f(x):\n    return 0\n') > 0)
check('module: decorator added to a reviewed function', mod_violations(MOD.replace('def f(x):', '@staticmethod\ndef f(x):')) > 0)
check('module: docstring underline removed', mod_violations(MOD.replace('    -----\n', '')) > 0)
check('module: constant rebound by a new statement', mod_violations(MOD + '\nPD_RTOL = 0.5\n') > 0)
check('module: import rebinding a reviewed name', mod_violations(MOD + '\nfrom math import sqrt as f\n') > 0)
check('module: monkeypatch statement', mod_violations(MOD + '\nnp.linalg.eigvalsh = None\n') > 0)
check('module: comment-only change allowed', mod_violations(MOD.replace('import numpy as np\n', 'import numpy as np  # numerics\n')) == 0)
(root / 'pkg/m.py').write_text(MOD)
# scope mutations
(root / 'notes.txt').write_text('committed notes')            # user's baseline edit reverted to HEAD: gone from status
g = run(root, '--only', 'scope', '--state-dir', str(state), '--baseline-sha', bsha)
check('scope: reverted baseline edit caught', g['scope']['out_of_scope'] == ['notes.txt'], g['scope'])
(root / 'notes.txt').write_text('user edit before the round')
(root / 'oops.py').write_text('x'); git(root, 'add', 'oops.py'); git(root, 'commit', '-qm', 'agent commit')
g = run(root, '--only', 'scope', '--state-dir', str(state), '--baseline-sha', bsha)
check('scope: commit during the round -> HEAD moved', g['scope']['head_moved'] is True, g['scope'])
git(root, 'reset', '-q', '--soft', 'HEAD~1'); git(root, 'rm', '-q', '--cached', 'oops.py'); (root / 'oops.py').unlink()
(root / 'Report.md').write_text('r'); git(root, 'add', 'Report.md'); git(root, 'commit', '-qm', 'r')
git(root, 'mv', 'Report.md', 'Report2.md')
paths = rg._git_changed(root)
check('porcelain v2 rename: both sides, no mangled names', 'Report.md' in paths and 'Report2.md' in paths and all(not p.startswith(' ') for p in paths), paths)
git(root, 'mv', 'Report2.md', 'Report.md')
# --- third review: tag tokens
def tag_ok(line, printed):
    arch.write_text('# A\n## 9\n### rT\n' + line + '\n')
    (evd / 'evidence.json').write_text(json.dumps({'round': 'rT', 'environment': 'py', 'entries': [{'id': 'x', 'printed': printed, 'kind': 'point', 'source': 'docs/research/goal-rounds/rT/route1/out.json', 'locator': {'json': ['v']}, 'conditions': 'c'}]}))
    return run(root, '--only', 'record')['record']['bad_tag_count'] == 0
for line, pr in [('均值 12.5 [E:x]', '12'), ('偏差 −0.03 [E:x]', '0.03'), ('偏差 -0.03 [E:x]', '0.03'), ('误差 2.80e-6 [E:x]', '2.80'), ('误差 2.80×10⁻⁶ [E:x]', '2.80'), ('计数 12,345 [E:x]', '12'), ('计数 12,345 [E:x]', '345'), ('界为`0.9999`[E:x]', '0.4194')]:
    check(f'tag rejects {line!r} with printed {pr!r}', not tag_ok(line, pr))
for line, pr in [('界 0.4194. [E:x]', '0.4194'), ('约 53% [E:x]', '53'), ('1-0.5216 [E:x]', '0.5216'), ('0.3/0.6/0.9 [E:x]', '0.9'), ('偏差 −0.03 [E:x]', '-0.03'), ('形如 `[E:x]` 的标记', 'zz')]:
    check(f'tag accepts {line!r} with printed {pr!r}', tag_ok(line, pr))
arch.write_text('# A\n## 9\n### rT\n台账见下。\n### 台账\n界 0.9999 [E:x]\n### r9\nx\n')
g = run(root, '--only', 'record')
check('record: ### sub-heading inside the round subsection counted', g['record']['inner_headings'] == 1 and g['record']['chars'] > 20, g['record'])
# --- staged content
(root / 'notes.txt').write_text('AGENT CONTENT'); git(root, 'add', 'notes.txt'); (root / 'notes.txt').write_text('user edit before the round')
g = run(root, '--only', 'scope', '--state-dir', str(state), '--baseline-sha', bsha)
check('scope: staged out-of-scope content with restored working tree caught', 'notes.txt' in g['scope']['out_of_scope'], g['scope'])
git(root, 'reset', '-q', 'notes.txt')
git(root, 'add', '-A')
g = run(root, '--only', 'scope', '--state-dir', str(state), '--baseline-sha', bsha)
check('scope: git add -A staging the user\'s edits caught', {'notes.txt', 'other.txt'} <= set(g['scope']['out_of_scope']), g['scope'])
git(root, 'reset', '-q')
g = run(root, '--only', 'scope', '--state-dir', str(state), '--baseline-sha', bsha)
check('scope clean again after unstaging', g['scope']['count'] == 0, g['scope'])
# --- module: names the reviewed code reads, import-time effects, honest helpers
SNAP2 = MOD.replace('    y = x + 1\n', '    y = max(x, 0) + 1\n')
(root / 'pkg/m.py').write_text(SNAP2); run(root, '--only', 'snapshot')
check('module: shadowing a builtin read by reviewed code', mod_violations(SNAP2 + '\nfrom numpy import max\n') > 0)
check('module: new function named like a builtin the reviewed code reads', mod_violations(SNAP2 + '\ndef max(*a):\n    return 0\n') > 0)
check('module: class body rebinding a constant via globals()', mod_violations(SNAP2 + '\nclass _T:\n    globals()["PD_RTOL"] = 0.5\n') > 0)
check('module: class body monkeypatching numpy', mod_violations(SNAP2 + '\nclass _P:\n    np.linalg.eigvalsh = staticmethod(lambda a: a)\n') > 0)
check('module: default argument updating globals', mod_violations(SNAP2 + '\ndef _h(x, _=globals().update(f=lambda x: 42)):\n    return x\n') > 0)
check('module: honest helper with a call in a default and a dataclass', mod_violations(SNAP2 + '\nfrom dataclasses import dataclass\n\n\n@dataclass\nclass Cell:\n    m: int = 32\n\n\ndef _draw(n, rng=np.random.default_rng(0)):\n    return rng.normal(size=n)\n') == 0)
(root / 'pkg/m.py').write_text(MOD); run(root, '--only', 'snapshot')
# --- verifier: sources only regular frozen files; kind against the ledger
(evd / 'route1' / '__pycache__').mkdir(exist_ok=True); (evd / 'route1/__pycache__/n.json').write_text('{"v": 0.9999}')
(evd / 'writer_notes').mkdir(exist_ok=True); (evd / 'writer_notes/n.json').write_text('{"v": 0.9999}'); os.symlink('writer_notes', evd / 'route9')
before = run(root, '--only', 'frozen')['frozen']['hash']
ents = [{'id': 'p', 'printed': '0.9999', 'kind': 'point', 'source': 'docs/research/goal-rounds/rT/route1/__pycache__/n.json', 'locator': {'json': ['v']}, 'conditions': 'c'},
        {'id': 's', 'printed': '0.9999', 'kind': 'point', 'source': 'docs/research/goal-rounds/rT/route9/n.json', 'locator': {'json': ['v']}, 'conditions': 'c'}]
(evd / 'evidence.json').write_text(json.dumps({'round': 'rT', 'environment': 'py', 'entries': ents}))
g = run(root, '--only', 'verifier,frozen')
check('verifier rejects __pycache__ and symlinked sources', g['verifier']['passed'] == 0 and g['verifier']['total'] == 2, g['verifier'])
os.unlink(evd / 'route9')
check('frozen hash covers a symlinked top-level directory', run(root, '--only', 'frozen')['frozen']['hash'] != before)
shutil.rmtree(evd / 'writer_notes'); shutil.rmtree(evd / 'route1/__pycache__')
led3 = json.loads(json.dumps(led)); led3['versions'][0]['numbers'] = [{'name': 'fp', 'value': '0.0324', 'kind': 'upper', 'source': str(scr / 'route1/out.json')}]
(evd / 'review-verdicts/ledger.json').write_text(json.dumps(led3, ensure_ascii=False))
(evd / 'evidence.json').write_text(json.dumps({'round': 'rT', 'environment': 'py', 'entries': [{'id': 'fp', 'printed': '0.4194', 'kind': 'point', 'claim': 'R1-1', 'number': 'fp', 'source': 'docs/research/goal-rounds/rT/route1/out.json', 'locator': {'json': ['v']}, 'conditions': 'c'}]}))
g = run(root, '--only', 'verifier')
check('verifier: kind must match the ledger number named by claim/number', g['verifier']['passed'] == 0 and 'kind' in g['verifier']['failures'][0], g['verifier'])
(evd / 'review-verdicts/ledger.json').write_text(json.dumps(led, ensure_ascii=False, indent=2))
# --- pytest: counts from junit, not from what tests print
(root / 'sycophancy_phase0/conftest.py').write_text('import atexit\natexit.register(lambda: print("111 passed in 1.00s"))\n')
g = run(root, '--only', 'pytest', '--state-dir', str(state))
check('pytest: a fake summary printed at exit does not change the junit counts', g['pytest']['passed'] == 2 and g['pytest']['source'] == 'junit', g['pytest'])
(root / 'sycophancy_phase0/conftest.py').unlink()
# --- copy: non-UTF-8 name skipped; fresh; backup / restore / hashes
bad = os.fsencode(str(scr / 'route1')) + b'/r\xe9sultat.json'
with open(bad, 'wb') as fh: fh.write(b'{}')
g = run(root, '--only', 'copy', '--copy-from', str(scr))
check('copy: non-UTF-8 file name skipped and listed, not an error', 'error' not in g['copy'] and any('sultat' in x for x in g['copy']['skipped']), g['copy'])
os.unlink(bad)
g = run(root, '--only', 'fresh', '--copy-from', str(scr))
check('fresh: existing scratch and evidence reported', g['fresh']['scratch_entries'] > 0 and g['fresh']['evidence_entries'] > 0, g['fresh'])
g = run(root, '--only', 'fresh', '--copy-from', str(base / 'scr' / 'none'))
check('fresh: missing scratch dir is 0', g['fresh']['scratch_entries'] == 0, g['fresh'])
bdir = base / 'scr' / 'rT' / 'code' / 'R1-1_v9'
g = run(root, '--only', 'backup,hashes', '--backup-dir', str(bdir))
m0 = g['hashes']['module_sha']
check('backup created with the current hashes', sorted(g['backup']['created']) == ['module.orig', 'tests.orig'] and g['backup']['module_sha'] == m0)
(root / 'pkg/m.py').write_text(MOD + '\n\ndef h():\n    return 3\n')
g = run(root, '--only', 'backup', '--backup-dir', str(bdir))
check('backup never overwrites; reports the changed current file', g['backup']['created'] == [] and g['backup']['module_sha'] == m0 and g['backup']['module_now'] != m0, g['backup'])
g = run(root, '--only', 'restore,hashes', '--backup-dir', str(bdir))
check('restore puts the backed-up module back', g['restore']['restored'] and g['hashes']['module_sha'] == m0, g)
check('backup dir inside the repository rejected', 'error' in run(root, '--only', 'backup', '--backup-dir', str(root / 'bk'))['backup'])
# --- fourth review: references kept by the gate (expect.json, frozen.json), assembly, scope-aware module check
exp0 = json.loads((state / 'expect.json').read_text())
check('baseline wrote expect.json with the module and tests hashes', exp0['module_sha'] == rg._sha(root / 'pkg/m.py'), exp0)
bdir2 = base / 'scr' / 'rT' / 'code' / 'R2-1_v2'
run(root, '--only', 'accept', '--state-dir', str(state))      # this test edited the tests file after the baseline
g = run(root, '--only', 'backup', '--backup-dir', str(bdir2), '--state-dir', str(state))
check('backup matches the recorded reference', g['backup']['matches_expected'] is True, g['backup'])
(root / 'pkg/m.py').write_text(MOD + '\n\ndef k():\n    return 4\n')
g = run(root, '--only', 'hashes', '--state-dir', str(state))
check('hashes: module_changed against the reference', g['hashes']['module_changed'] is True and g['hashes']['matches_expected'] is False, g['hashes'])
g = run(root, '--only', 'accept,hashes', '--state-dir', str(state))
check('accept records the current files; afterwards they match', g['accept']['accepted'] and g['hashes']['matches_expected'] is True, g)
g = run(root, '--only', 'restore', '--backup-dir', str(bdir2), '--state-dir', str(state))
check('restore to a backup that is no longer the reference: matches_expected false', g['restore']['restored'] and g['restore']['matches_expected'] is False, g['restore'])
run(root, '--only', 'accept', '--state-dir', str(state))
g = run(root, '--only', 'snapshot', '--state-dir', str(state))
check('snapshot matches the reference', g['snapshot']['matches_expected'] is True, g['snapshot'])
g = run(root, '--only', 'freeze', '--state-dir', str(state))
check('freeze records frozen.json', g['freeze']['frozen'] and (state / 'frozen.json').is_file())
check('frozen unchanged right after freezing', run(root, '--only', 'frozen', '--state-dir', str(state))['frozen']['unchanged'] is True)
(evd / 'route1/out.json').write_text('{"v": 0.41942966, "w": 0.95, "edited": 1}')
check('frozen detects an edit against frozen.json', run(root, '--only', 'frozen', '--state-dir', str(state))['frozen']['unchanged'] is False)
(evd / 'route1/out.json').write_text('{"v": 0.41942966, "w": 0.95}')
# assembly from part files, and the parts named on a mismatch
pdir = evd / 'review-verdicts' / 'ledger.parts'; pdir.mkdir(parents=True, exist_ok=True)
parts = {}
for k, v in led.items():
    if k == 'versions':
        for i, x in enumerate(v):
            (pdir / f'versions.{i}.json').write_text(json.dumps(x, ensure_ascii=False)); parts[f'versions.{i}'] = rg.canonical_sha(x)[:16]
    else:
        (pdir / f'{k}.json').write_text(json.dumps(v, ensure_ascii=False)); parts[k] = rg.canonical_sha(v)[:16]
g = run(root, '--only', 'assemble,ledger', '--expect', exp, '--ledger-sha', LSHA, '--ledger-parts', json.dumps(parts))
check('assemble rebuilds a ledger with the workflow sha', g['assemble']['missing'] == [] and g['ledger']['mismatches'] == 0, g)
bad_v = dict(led['versions'][0], premises='n>=2'); (pdir / 'versions.0.json').write_text(json.dumps(bad_v, ensure_ascii=False)); (pdir / 'isolation.json').unlink()
g = run(root, '--only', 'assemble,ledger', '--expect', exp, '--ledger-sha', LSHA, '--ledger-parts', json.dumps(parts))
check('assemble reports the missing part; ledger names the differing parts', g['assemble']['missing'] == ['isolation'] and 'versions.0' in g['ledger']['differing_parts'], g)
(evd / 'review-verdicts/ledger.json').write_text(json.dumps(led, ensure_ascii=False, indent=2))
# module: a new helper's own locals are not protected; module-level names it resolves globally are
SNAP3 = MOD.replace('    y = x + 1\n', '    M = [[0]]\n    out = {}\n    y = x + 1\n')
(root / 'pkg/m.py').write_text(SNAP3); run(root, '--only', 'snapshot')
check('module: helper filling its own local M / out is allowed', mod_violations(SNAP3 + '\ndef _helper(n):\n    M = [[0] * n for _ in range(n)]\n    out = {}\n    for i in range(n):\n        M[i][i] = 1\n        out[i] = M[i]\n    return out\n') == 0)
check('module: helper body storing into a module-level import is flagged', mod_violations(SNAP3 + '\ndef _helper():\n    np.linalg.eigvalsh = None\n') > 0)
check('module: helper body declaring a reviewed constant global is flagged', mod_violations(SNAP3 + '\ndef _helper():\n    global PD_RTOL\n    PD_RTOL = 0.5\n') > 0)
check('module: a builtin used inside a reviewed function is protected', 'max' in rg._protected_names(MOD.replace('    y = x + 1\n', '    y = max(x, 0)\n'), __import__('ast').parse(MOD.replace('    y = x + 1\n', '    y = max(x, 0)\n'))))
check('module: locals of reviewed functions are not protected', 'y' not in rg._protected_names(MOD, __import__('ast').parse(MOD)))
(root / 'pkg/m.py').write_text(MOD); run(root, '--only', 'snapshot')
# unicode categories
check('path_ok rejects U+2060 inside a forbidden prefix', rg.path_ok(str(base / 'sc⁠r/rT/x.json'), '', iso) is False)
shutil.rmtree(base)
print('e2e', 'ok' if not fails else f'{fails} failures'); sys.exit(1 if fails else 0)
