"""阶段二各执行范围的冻结校验；旧阶段一文件不变。"""
from pathlib import Path
import hashlib
import json


def validate(out, name='factdiag7_stage2_prereg.json'):
    reg=json.loads((out/name).read_text(encoding='utf-8'))
    for filename,sha in reg['frozen_files'].items():
        if hashlib.sha256((out/filename).read_bytes()).hexdigest()!=sha:
            raise RuntimeError('阶段二冻结文件变化：'+filename)
    for filename,sha in reg['code_sha256'].items():
        if hashlib.sha256((Path(__file__).parent/filename).read_bytes()).hexdigest()!=sha:
            raise RuntimeError('阶段二代码变化：'+filename)
    return reg
