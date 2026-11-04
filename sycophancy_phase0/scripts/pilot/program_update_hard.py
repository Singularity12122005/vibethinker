"""困难开发轮：原脚手架与采样器不变，仅替换函数族和配对版本。"""
from program_update_development import Family

FAMILIES = [
    Family("闭包晚绑定",
           "def run(values):\n"
           "    def batches():\n"
           "        for base in values:\n"
           "            yield (VARIANT for offset in (1, 4))\n"
           "    a, b = batches()\n"
           "    f, g, h = next(a), next(b), next(a)\n"
           "    return 100 * f() + 10 * g() + h()",
           ("(lambda: base + offset)", "(lambda offset=offset: base + offset)"),
           (2, 7), "returns 1191", ("returns 1191", "returns 891")),
    Family("可变默认参数",
           "def run(values):\n"
           "    def push(x, buf=[]):\n"
           "        old = buf[:]\n"
           "        VARIANT\n"
           "        return old, buf\n"
           "    rows = [push(x) for x in values]\n"
           "    return sum(i * (10 * len(old) + len(buf))\n"
           "               for i, (old, buf) in enumerate(rows, 1))",
           ("buf = buf + [x]", "buf += [x]"),
           (2, 5, 7), "returns 98", ("returns 6", "returns 98")),
    Family("浮点比较",
           "def run(values):\n"
           "    def matches(x):\n"
           "        actual = round(VARIANT, 2)\n"
           "        target = ((x + 5) // 10) / 100\n"
           "        return actual == target\n"
           "    return sum(matches(x) for x in values)",
           ("x / 1000", "(x / 100) / 10"),
           (1005, 1015, 2675, 2685, 3995, 4015), "returns 4", ("returns 2", "returns 4")),
    Family("生成器耗尽",
           "def run(values):\n"
           "    from itertools import groupby, islice\n"
           "    groups = groupby(values)\n"
           "    _, first = next(groups)\n"
           "    tail = islice(first, 1, None)\n"
           "    kept = VARIANT\n"
           "    _, second = next(groups)\n"
           "    lead = next(second)\n"
           "    _, third = next(groups)\n"
           "    return sum(kept) + lead + sum(second) + sum(third)",
           ("iter(tail)", "list(tail)"), (2, 2, 2, 5, 5, 7, 7), "returns 19",
           ("returns 19", "returns 23")),
]
