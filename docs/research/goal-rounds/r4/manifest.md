# Round r4 manifest (goal archive §9 r4)

Root: `/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/goal_rounds/r4/` (session scratch, outside the repository).
Interpreter for every script: `/tmp/claude-0/venv/bin/python` (python 3.13.16 x86_64, numpy 2.5.4, scipy 1.18.1, mpmath 1.3.0 where used; 4 cores; 2026-10-19).
The problem-phase files were tagged numpy 2.5.3 when they were written; route B checked that this interpreter has numpy 2.5.4.
`__pycache__/` folders are omitted.

Ledger statuses: **reviewed** = A-C1, B1, C1 (all final status *candidate*); **unreviewed_overflow** = A-C2, A-C3, B2, B3, C2, C3; **author_refuted** = none.

## Repository files changed in this round (the only ones allowed)

| file | change |
| --- | --- |
| `/home/user/vibethinker/docs/research/sycophancy-phase0-goal.md` | §9 `### r4` record (A–F); §7 (candidates, 未审 line, r4 errors, "not adopted for now" route — moved out of the eliminated list in the repair pass, rewritten gaps / next attack with the r3 text kept); §6 r4 line; §8 L0 row; version line |
| `/home/user/vibethinker/sycophancy_phase0/tests/test_analysis.py` | three regression locks of the reviewed **candidate** cores: `test_goal_r4_a_c1_candidate_closed_form_sandwich`, `test_goal_r4_b1_candidate_lecam_constants`, `test_goal_r4_c1_candidate_reuse_identity` (+ helpers `_goal_r4_*`) |
| `/home/user/vibethinker/sycophancy_phase0/src/sycophancy_phase0/analysis/g6_iv.py` | unchanged (the tests need only the existing `binomial_factorial_joint_moment` and `endpoint_contrast_poly_cs`) |

## problem/ — problem-critique self-checks (not reviewed claims)

| script | outputs | content |
| --- | --- | --- |
| `problem/check1_size_width.py` | `check1_size_width.json`, `.out` | size / non-PD / width of degree-1 and degree-2 tests, narrow & wide worlds, lin & quad g, m = 32/128/512, HC1/CR1 (seed 20261019, 2000 reps) |
| `problem/check1b_compatible_edge.py` | `check1b_compatible_edge.json`, `.out` | half-variance, point-mass, narrow, double-variance worlds at m = 128/512 (seed 7) |
| `problem/check2_pilot_information.py` | `check2_pilot_information.json`, `.out` | pilot U-statistic estimates of V and lambda_min(H_w); type-0-only Le Cam bounds (seed 4) |
| `problem/check2b_lmin_at_128.py` | `check2b_lmin_at_128.json`, `.out` | the same pilot quantities at m = 32/128/512 |
| `problem/check2c_lecam_vs_m.py` | `check2c_lecam_vs_m.json`, `.out` | type-0-only (n = 100) and n = 200 single-type Hellinger bounds vs m (source of the 0.569 / 0.135 / 0.012 constants) |
| `problem/check3_two_stage_reuse.py` | `check3_two_stage_reuse.json`, `.out` | reuse vs fresh size for two pilot rules, narrow world (4000 reps) |

## A/ = `A__Overlap-and-PD-margin_certificate_from_pilot_U-statistics__upper_bound__sufficiency_direction_/`

| script | outputs | claim | status |
| --- | --- | --- | --- |
| `derivation.md` | — | A-C1 (§1), A-C2 (§2), A-C3 (§3) | — |
| `route_a_lib.py` | — (library) | A-C1, A-C2 | — |
| `a1_exact_check.py` | `a1_exact_check.json`, `.out` | A-C1 exact Fraction check + first-order table (deterministic) | reviewed, candidate |
| `a1b_largen_and_budget.py` | `a1b_largen_and_budget.json`, `.out` | A-C1 n = 20000 production ratios (seed 77), first-order m-budget | reviewed, candidate |
| `a2_two_stage_sim.py` | `a2_two_stage_sim.out`, `a2_raw_narrow_linear.npz`, `a2_raw_halfvar_linear.npz`, `a2_raw_wide_linear.npz`, `a2_raw_narrow_quad_narrow.npz`, `a2_raw_wide_quad_wide.npz` | A-C2 two-stage production simulation; all five cells finished after the attack's reporting time | unreviewed |
| `a2_summarize.py` | **not run in r4**; `a2_summary.json` does not exist | A-C2 availability / false-fire / reuse numbers | pending |
| `a3_rigorous_constants.py` | `a3_rigorous_constants.json`, `.out` | A-C3 Hoeffding box, DKW band, matrix Bernstein (seed 2026) | unreviewed |

## B/ = `B__Le_Cam_two-point_impossibility_for_the_32-pilot_and_explicit_failing_worlds_inside_the_compatible_set__lower_bound__necessity_direction_/`

| script | outputs | claim | status |
| --- | --- | --- | --- |
| `b_derivation.md` | — | B1, B2, B3 | — |
| `b1_lecam_exact.py` | `b1_lecam_exact.json`, `.out` | B1 exact affinities and Hellinger bounds; LR-test MC (seed 20261019) | reviewed, candidate |
| `b1b_np_exact_stages.py` | `b1b_np_exact_stages.json`, `.out` | B1 NP error sums by LR-test MC per stage (seed 20261020, 200000 pilots per side) | reviewed, candidate |
| `b2_failing_worlds_gclass.py` | `b2_failing_worlds_gclass.json`, `.out` | B2 54 cells, 10-point g grid, HC1+CR1 (base seed 4242) | unreviewed |
| `b2b_pd_event_invariance.py` | `b2b_pd_event_invariance.json`, `.out` | B2 PD-event invariance (seed 31337), pooled CIs | unreviewed |
| `b3_dkw_band_lp.py` | `b3_dkw_band_lp.json`, `.out` | B3 DKW inclusion (seed 777), LP world F_lp, its production test (seeds 100119 / 100503) | unreviewed |

## C/ = `C__Sequential_internal-pilot_design__32___128___re-assess__and_validity_under_reuse/`

| script | outputs | claim | status |
| --- | --- | --- | --- |
| `c_derivation.md` | — | C1 (§1–§2), C3 (§3) | — |
| `c_common.py` | — (library: width_predictor, pd_flag, pd_margin_hat) | C1–C3 | — |
| `c1_nested_mc.py --stage 1` | `c1_stage1.log`, `c1_stage1_narrow_lin.npz`, `c1_stage1_narrow_quad.npz`, `c1_stage1_narrow_cheb.npz`, `c1_stage1_halfvar_lin.npz` | C1/C2/C3 nested MC (1000 outer x 200 inner; seeds 4101988 / 4102092 / 4102067 / 4102063) | C1 reviewed; C2, C3 unreviewed |
| `c1_nested_mc.py --stage 1` (wide cell) | none (log stops at 600/1000) | — | not finished |
| `c1_nested_mc.py --stage 2` | none (no `c1_stage2.log` in the directory) | C3 128-stage availability, 512-stage constants | not run to completion |
| `c2_analyse.py` | `c2_analysis.json`, `.out` | ANOVA sigma_delta, uniform bounds, rule-specific terms (bootstrap seed 777) | C1 reviewed; C2/C3 parts unreviewed |
| `c3_tilt_moments.py` | `c3_tilt_moments.json`, `.out` | exact pilot shares and kappa (Fractions, no seed) | reviewed (C1) |
| `c4_identity_check.py` | `c4_identity_check.json`, `.out` | U-tilde formula vs MC, exact U_1 identity, ANOVA unbiasedness (seed 4104) | reviewed (C1) |

## Review directories (three lenses per reviewed claim)

Numbers quoted from a lens without an output file below come from that lens's verdict text in the ledger.

| directory | lens | scripts | outputs |
| --- | --- | --- | --- |
| `review_A-C1_math/` | math | `s1_indep_mc.py`, `s2_counterexample_Kdep_var.py`, `s3_clipping_sup.py`, `s4_sup_bruteforce.py`, `s5_degree_and_clipped_search.py`, `s6_mc_clipped_boundary.py`, `s7_gap_size_beta_worlds.py`, `s8_clipped_search_b0.py`, `s9_clipped_search_large_m.py` | none saved (verdict text) |
| `review_A-C1_blind_replication/` | blind replication | `formula.py`, `worlds.py`, `halfvar.py`, `halfvar2.py`, `brute.py`, `supclass.py`, `mc.py`, `extra.py` | none saved (verdict text) |
| `review_A-C1_scope/` | experiment scope | `s1_scope_numbers.py`, `s2_n200_production.py`, `s3_c2_eta_end_and_m64.py` | `s1_scope_numbers.json/.out`, `s2_n200_production.json/.out`, `s3_c2_eta_end_and_m64.json/.out`, `s4_narm32.out` |
| `review_B1_math/` | math | `rev_b1_exact.py`, `selftest.py` | `rev_b1_exact.out` (lattice-FFT NP brackets) |
| `review_B1_blind_replication/` | blind replication | `rep.py`, `run1.py`, `fft.py`, `bigmc.py`, `affinity.py`, `lrtest.py`, `theta.py`, `theta2.py`, `ftheta_guess.py`, `power.py`, `sens.py`, `time1.py` | `full_run.log` (grid NP values m = 32/128) |
| `review_B1_scope/` | experiment scope | `cluster_np.py`, `cluster_pass.py` | none saved (verdict text) |
| `review_C1_math/` | math | `rv1_kappa_mc.py`, `rv2_anova_recheck.py`, `rv3_ucl_coverage.py` | none saved (verdict text) |
| `review_C1_blind_replication/` | blind replication | `exact.py`, `kbar.py`, `wide.py`, `mc.py`, `rules.py` | `out_{narrow_lin,narrow_quad,narrow_cheb,half_lin}_{1,2}.txt`, `res_*_{1,2}.npz`, `res_narrow_lin_99.npz`, `rules_{narrow_lin,narrow_cheb,half_lin}_7.npz` |
| `review_C1_scope/` | experiment scope | `s1_clustered_sigma_delta.py`, `s2_analyse.py` | `s1.log`, `s1_iid.npz`, `s1_clu70.npz`, `s1_clu90.npz` |

Blind-replication isolation: the `files_read` audit passed for all three claims (prompt-level isolation plus audit, not file-system enforcement).

## synthesis/ — this synthesis stage

| file | content |
| --- | --- |
| `synthesis/draft_tests_r4.py` | draft of the three r4 tests (identical logic to the repository tests) |
| `synthesis/mutation_check.py` | mutation check: a wrong alpha sign, a dropped gamma'V2 gamma term, or a changed U_2 share makes the corresponding test fail; the fourth mutation (pilot of 1 inside 4) only trips the rule-count guard, as expected, since the identity holds for any split |
| `synthesis/mutation_debug.py` | locates the assertion tripped by that fourth mutation |
| `synthesis/pytest_test_analysis.out` | `pytest sycophancy_phase0/tests/test_analysis.py -q`: 27 passed in 28.70 s (re-run after all archive edits with `/tmp/claude-0/venv/bin/python -m pytest /home/user/vibethinker/sycophancy_phase0/tests/test_analysis.py -q`: 27 passed in 25.32 s) |
| `synthesis/.pytest_cache/` | pytest cache from running the draft |

## Not done in r4 (must not be reported as done)

- `A/a2_summarize.py` was not run; A-C2 has no availability, false-fire or reuse numbers.
- `C/c1_nested_mc.py --stage 2` and the wide stage-1 cell did not finish; C3's 128-stage availability and the residual probability of needing 512 are unknown.
- The corrected statements of A-C1, B1 and C1 have not been re-reviewed.
- The full `pytest -q` suite was not run in the synthesis stage (only `tests/test_analysis.py`); it was run in the repair stage (see `repair/` below).
- A-C3, B2, B3: the authors' self-assessed "proved" is not adopted by the archive (unreviewed, no derivation in the record, no pytest case).

## repair/ — the single repair pass (after the overreach and label checks)

Only the archive text was changed; `tests/test_analysis.py` and `analysis/g6_iv.py` were not modified in the repair pass.

| file | content |
| --- | --- |
| `repair/s2_analyse_rerun.out` | re-run of `review_C1_scope/s2_analyse.py` (seed 7): clustered-world sigma_delta UCLs, 4 decimals |
| `repair/s2_analyse_6dp.py`, `.out` | the same script with 6-decimal printing only (same seed and call order), used to round UCLs up |
| `repair/w1_q90_ratios.py`, `.out` | realised q90 / first-order width W_1 for every degree-2 cell with a known W_1 (check1, check1b, review_A-C1_scope s2/s3/s4): 37 cells with non-PD < 1%, ratio 1.083–1.902; all finite ratios > 1 |
| `repair/mutation_check_rerun.out`, `repair/mutation_debug_rerun.out` | re-run of `synthesis/mutation_check.py` (4/4 detected) and `mutation_debug.py` (the 4th mutation trips `assert checked > 100`) |
| `repair/pytest_test_analysis_repair.out`, `repair/pytest_test_analysis_final.out` | `pytest .../tests/test_analysis.py -q`: 27 passed in 22.18 s; after the last text edit 27 passed in 22.24 s |
| `repair/pytest_r4_three_tests.out` | `-k test_goal_r4_ --durations=0`: 3 passed in 4.52 s |
| `repair/pytest_full_suite.out` | full `pytest -q` in `sycophancy_phase0/`: 109 passed in 171.60 s, no warnings (pytest 9.1.1) |
| `repair/git_status_before_full_suite.txt`, `repair/git_status_after_full_suite.txt` | identical: only the archive and `tests/test_analysis.py` modified |

## Final record step under protocol v4 (2026-10-20)

Written after the re-review (not copies of scratch material): `detailed-record.md` (the pre-v4 §9 r4 text moved verbatim, plus every item of `review-verdicts/r4_remaining_after_loop.json` as an open non-blocking issue), `evidence.json` (checked by `.claude/skills/goal/verify_evidence.py`; output `final/verify_evidence.out`), `review-verdicts/r4_rereview.json` (narrowed statements of A-C1, B1, C1, B2-core with the fresh three-lens verdicts; all candidate), `final/pytest_test_analysis.out`. Re-review lens scripts and outputs: `rr-<claim>_<lens>/` (see `PATHS.md`). No test was added (no claim reached independent review); `tests/test_analysis.py` is unchanged in this step.

