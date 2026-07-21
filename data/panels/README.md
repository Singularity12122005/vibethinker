# Public evaluation fixtures

Only synthetic fixtures live here. `toy/panel.jsonl` contains one invented row
per supported domain and is not a benchmark. `negative/invalid-panels.json`
contains deliberately invalid synthetic contracts used by CPU tests.

Formal panels are supplied out of band and are identified only by a private
manifest hash. Do not add real prompts, frozen hash lists, candidate IDs,
model outputs, or provider credentials to this directory.
