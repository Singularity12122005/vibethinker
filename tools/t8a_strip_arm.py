"""T8a 残留扫描的去臂输入：只导出每份稿件的候选视图人工命题，不导出臂、人工编号、历史编号或核对说明。

只用 Python 标准库。用法（路径换成你本机的实际位置）：
  python t8a_strip_arm.py --workspace "C:/Users/Singu/OneDrive/Documents/ChatGPT/Review" --downloads "C:/Users/Singu/Downloads"
--workspace 是含 factdiag7-work 文件夹的目录；--downloads 是两个标签交付压缩包所在目录（找不到时会在 workspace 下递归查找）。
输出：<workspace>/factdiag7-work/t8a_scan_labels_noarm.json
"""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path

ARCHIVES = {
    'stage2_fallback_X_labels.json': 'stage2_fallback_final_delivery_20261029.zip',
    'stage2_fallback_XC_labels.json': 'stage2_batch5_XC_final_delivery_20261030.zip',
}
CLAIM_FIELDS = ('polarity', 'relation', 'relation_detail', 'target', 'basis', 'exclusivity',
                'scope_text', 'hedged', 'quote', 'verdict', 'claim_status', 'identity_claim',
                'broad_denial', 'added_by_human')


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def locate(archive, downloads, workspace):
    direct = downloads / archive
    if direct.exists():
        return direct
    hits = sorted(set(downloads.rglob(archive)) | set(workspace.rglob(archive)))
    if len(hits) != 1:
        raise SystemExit(f'找不到或不唯一：{archive}（命中 {len(hits)} 个）')
    return hits[0]


def read_rows(path, basename):
    with zipfile.ZipFile(path) as archive:
        names = [n for n in archive.namelist() if n.endswith('/' + basename) or n == basename]
        if len(names) != 1:
            raise SystemExit(f'压缩包内标签文件不唯一或缺失：{basename}')
        return json.loads(archive.read(names[0]))['records']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--downloads', required=True)
    args = parser.parse_args()
    workspace, downloads = Path(args.workspace), Path(args.downloads)
    work = workspace / 'factdiag7-work'
    key_path = work / 'stage2_T8a_private_key.json'
    edits_path = work / 'human-review' / 'stage2_T8a_edits.json'
    key = json.loads(key_path.read_text(encoding='utf-8'))
    edits = {r['blind_id']: r for r in json.loads(edits_path.read_text(encoding='utf-8'))['records']}

    rows, provenance = {}, {}
    for basename, archive in ARCHIVES.items():
        path = locate(archive, downloads, workspace)
        rows[basename] = {r['human_id']: r for r in read_rows(path, basename)}
        provenance[archive] = sha256(path)
    provenance['stage2_T8a_edits.json'] = sha256(edits_path)

    out = []
    for rec in key['records']:
        src = rec['source']
        row = rows[src['label_file']][src['human_id']]
        dviews = [v for v in row['views'] if v['view_type'] == 'D']
        if len(dviews) != 1:
            raise SystemExit('候选视图不唯一：' + rec['blind_id'])
        claims = [{k: c[k] for k in CLAIM_FIELDS if k in c} for c in dviews[0]['人工命题']]
        out.append(dict(blind_id=rec['blind_id'], operation=edits[rec['blind_id']]['operation'],
                        work_id=src['work_id'], candidate=dviews[0]['candidate'],
                        human_review_complete=row.get('human_review_complete'), claims=claims))
    out.sort(key=lambda r: r['blind_id'])

    body = json.dumps(out, ensure_ascii=False)
    banned = ('"arm"', '"human_id"', '"history_index"', '核对说明', '臂=')
    leaked = [b for b in banned if b in body]
    if leaked:
        raise SystemExit('导出记录含不应导出的字段，已停止：' + ', '.join(leaked))
    text = json.dumps(dict(note='仅供 T8a 残留扫描；已去除实验条件字段。',
                           input_sha256=provenance, records=out), ensure_ascii=False, indent=2)
    target = work / 't8a_scan_labels_noarm.json'
    target.write_text(text + '\n', encoding='utf-8')
    ops = {}
    for r in out:
        ops[r['operation']] = ops.get(r['operation'], 0) + 1
    print(f'已写出 {target}：{len(out)} 份，{ops}')


if __name__ == '__main__':
    main()
