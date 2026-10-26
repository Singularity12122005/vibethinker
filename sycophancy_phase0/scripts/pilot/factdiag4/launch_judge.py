"""隔离同名公共模块后启动原冻结评审，不改评审实现或提示词。"""
from pathlib import Path
import importlib
import importlib.util
import runpy
import sys


def load_judge_dependency():
    pilot = Path(__file__).resolve().parents[1]
    previous_common = sys.modules.get('common')
    previous_path = sys.path[:]
    spec = importlib.util.spec_from_file_location('factdiag4_pilot_common', pilot / 'common.py')
    pilot_common = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(pilot_common)
        sys.modules['common'] = pilot_common
        sys.path.insert(0, str(pilot))
        rescore = importlib.import_module('rescore')
        if Path(rescore.__file__).resolve() != (pilot / 'rescore.py').resolve():
            raise RuntimeError('评审客户端导入位置不符')
    finally:
        sys.path[:] = previous_path
        if previous_common is None:
            sys.modules.pop('common', None)
        else:
            sys.modules['common'] = previous_common
    return rescore


if __name__ == '__main__':
    dependency = load_judge_dependency()
    if sys.argv[1:] == ['--check-imports']:
        import runtime4
        if Path(sys.modules['common'].__file__).resolve() != Path(__file__).with_name('common.py').resolve():
            raise RuntimeError('第四批公共模块位置不符')
        print('导入检查通过：原评审客户端与第四批公共模块已隔离；未加载模型。')
    else:
        target = Path(__file__).with_name('runtime4.py')
        sys.argv = [str(target), 'judge', *sys.argv[1:]]
        runpy.run_path(str(target), run_name='__main__')
