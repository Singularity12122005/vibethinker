# VERL v0.8.0 Math RL checkpoint patches

Qwen2.5 64K 与 Qwen3.5 128K Math RL 共用同一份 epoch-boundary checkpoint 和
`COMMITTED` marker 修改。

先在干净的 VERL `v0.8.0` checkout 应用公共补丁，再按主线选择一个包导入补丁：

```bash
git -C /path/to/verl checkout v0.8.0
git -C /path/to/verl apply \
  /path/to/patches/verl-math-rl/0001-checkpoint-schedule-and-commit-marker.patch

# Qwen2.5 选择：
git -C /path/to/verl apply \
  /path/to/patches/verl-math-rl/0002-qwen25-package-import.patch

# Qwen3.5 选择（不要与 Qwen2.5 adaptation 同时应用）：
git -C /path/to/verl apply \
  /path/to/patches/verl-math-rl/0002-qwen35-package-import.patch
```

应用后必须让本项目包在所有 VERL worker 的 `PYTHONPATH` 中可见。两个 adaptation
只改变 checkpoint helper 的 Python import；reward 与 reward manager 仍由各自主线
配置中的显式文件路径注入。

源 runtime 中还能确认若干 Qwen3.5 专用行为，但缺少可核验的干净提交历史，因此只在
`manifest.yaml` 标为 `documented_only`，不反推伪造 patch。
