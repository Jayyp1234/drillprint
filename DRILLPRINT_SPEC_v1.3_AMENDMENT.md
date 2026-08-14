# DRILLPRINT — Specification Amendment v1.3 (rc2, verification-hardened)

**Status:** Draft for author approval · 2026-08-10
**Applies to:** DRILLPRINT_SPEC.md v1.0 + v1.1 (3D twin) + v1.2 (operator flows & demo)
**Basis:** the end-to-end verification study of 2026-08-10 (`SPEC_STUDY.md`) — 40 confirmed findings. This rc2 draft additionally survived its own adversarial verification round (3 independent checkers: arithmetic, coverage, contradiction-hunting); the 4 blocking and 12 should-fix issues that round found in rc1 are folded in below.

**How to read this document:** each amendment has three parts — **Problem** (what is wrong in v1.2, with the verified numbers), **Change** (the new normative text; it *replaces* the cited section text), and **Why this choice** (reasoning, including alternatives rejected). Where a v1.2 value survives unchanged it is not restated.

---

## A1 — Detection windows, profiles, and the new ORDER and LOW-DEEP profiles

*Resolves: "30 s LOW window → 1 frame → zero hashes" (critical), "MID W=10 s → 4 frames" (major), "order-STFT parameters stored nowhere" (major), "no profile for sub-10 Hz channels" (Volve sub-finding), "deep-corner combs unresolvable" (rc1 verification).*

**Problem.** A query window must contain enough STFT frames to form anchor→target hash pairs (Δt ≥ 1 frame). v1.2's W = 30 s LOW window holds exactly **one** 25.6 s frame — zero pairs, zero hashes: stick-slip can never match. MID's W = 10 s holds 4 frames (Δt ≤ 3), reproducing ~10 % of library hash types. The order-domain STFT (§9) never received N/hop/window parameters at all. And two channel classes have no profile: Volve's ~0.1–1 Hz surface cadence, and deep/slow stick-slip corners whose comb spacing falls inside the LOW mainlobe.

**Change.** Replace the §6 profile table and §10 window defaults with:

| Profile | domain | rate | N | hop | Δf / Δorder | frame span | query window W | eval cadence | T_max | hashed? |
|---|---|---|---|---|---|---|---|---|---|---|
| LOW | time | 10 Hz | 256 | 64 | 0.039 Hz | 25.6 s | **120 s** | 6.4 s | **12** | yes |
| **LOW-DEEP** | time | 10 Hz | 512 | 128 | 0.0195 Hz | 51.2 s | **240 s** | 12.8 s | **12** | yes (deep wells) |
| MID | time | 100 Hz | 512 | 128 | 0.195 Hz | 5.12 s | **30 s** | 1.28 s | **16** | display only |
| HIGH | time | 400 Hz | 1024 | 256 | 0.39 Hz | 2.56 s | 10 s | 1.0 s | **8** | display only¹ |
| **ORDER** | order | 64 samples/rev | 256 | 64 | 0.25 order | 4 rev | **16 rev** | 1 rev | **10** | yes |
| **LOW-DECIM** | time | 1 Hz | 256 | 64 | 0.0039 Hz | 256 s | — | 64 s | — | **never** (display/badges only) |

¹ HIGH additionally hosts a *test-only* time-domain whirl fingerprint set in M2 — see A16.

- Eval cadences are defined in **data-time seconds** (or revolutions for ORDER); HIGH's 1.0 s deliberately spans 1.56 hops — the K=2 rule (A2) requires ≥ 1 hop of fresh data between counted evaluations, which every cadence satisfies.
- **LOW-DEEP** is selected automatically when the predicted f₀ (A4) is below **0.12 Hz** — deep/slow corners (long L, heavy BHA) have comb spacing of 1.3–2.4 LOW bins, inside the Hann mainlobe; halving Δf restores resolvability. Its hashing band is 0.04–2 Hz (A9).
- **LOW-DECIM** exists so ~1 Hz channels (Volve, decimated variants) can stream spectrograms and drive observability badges. It never produces hashes: at 1 Hz the harmonic comb is invisible (§8's own "a lone peak is not discriminative"), so matching is structurally impossible there and the profile is honest about it.

New invariant, asserted by a unit test at import time: **frames_per_window(W, profile) ≥ T_max + 3** for every hashed profile. (Verified: LOW 15 ≥ 15, LOW-DEEP 15 ≥ 15, ORDER 13 ≥ 13; display-only MID 20, HIGH 12 also pass their scheduling math.)

T_max is now **per-profile** and applies identically to library and query hashing (a library hash whose Δt exceeds the profile's T_max is never emitted, so library and query hash populations match by construction). The 6-bit Δt field covers all values. K_max = 63 and fan-out F = 8 are unchanged.

The ORDER profile's rfft yields 129 order bins (Nyquist = 32 orders), inside the 10-bit f₁ field. **Effective order bandwidth of a channel is min(32, 0.5 × f_s / f_rot) — every class's hashing band must sit inside it for the bound channel** (bounce orders 2–10 on ACC_AX at 100 Hz: limit is 21.4 orders at 140 RPM — passes at all spec RPMs).

**Why this choice.** Shrinking the LOW frame (N=128) for faster response was rejected: Δf would coarsen to 0.078 Hz and a 0.1 Hz comb lands 1.28 bins apart — inside the Hann mainlobe, unresolvable. Deep-string stick-slip genuinely needs long frames; the honest fix is longer windows (trivial memory at 10 Hz) plus honest latency targets (A2). W_ORDER is stated in **revolutions** because that is the domain's native clock — 16 rev = 8 s at 120 RPM.

---

## A2 — Latency targets and the two-tier alert model

*Resolves: "≤5 s stick-slip / ≤3 s whirl targets arithmetically impossible" (critical ×3). rc2: targets re-derived from the partial-window mechanism; Tier-1 calibration added; deep-corner scaling stated.*

**Problem.** v1.2 demands stick-slip alert ≤ 5 s. But the phenomenon's own period is 2–10 s, a LOW frame spans 25.6 s, and the K=2 debounce alone adds ≥ 2 evaluation intervals. The ≤ 3 s whirl/bounce target fails on debounce arithmetic alone.

**Change.** Replace §18's latency targets with a **two-tier alert model**:

**Tier 1 — ADVISORY (amber).** SSSI (§2) on a rolling window of 2 predicted periods (band-filtered torque), plus band-energy RMS watchers for whirl/bounce. Fast, class-suggestive, not episode-matched.
- **Calibration (normative — Tier 1 is held to the same standard as the §14 baseline):** thresholds are fit on a normal-only validation run to a budget of **≤ 2 advisories per data-hour**, frozen before any gate or benchmark is scored, and recorded in `report.json`. An uncalibrated advisory tier would be tunable-to-pass, reintroducing the unfalsifiability A19 removes.
- Targets: stick-slip advisory ≤ **20 s** at reference conditions (L ≤ 3000 m, ≥ 90 RPM); scales as ~2 predicted periods + margin for deeper/slower corners. Whirl/bounce advisory ≤ **5 s**.

**Tier 2 — CONFIRMED (red).** The fingerprint match under A3's corrected significance.
- **Mechanism note (this is where the numbers come from):** confirmation does *not* wait for a full query window. Score ≥ s_min = 8 aligned hashes needs roughly 3 dysfunction-bearing frames (~5 peaks/frame, F = 8 fan-out), i.e. ~6 revolutions of ORDER data, plus K = 2 evaluations at the 1-rev cadence → floor ≈ **4 s at 120 RPM** for whirl/bounce. Stick-slip floor is set by LOW frame fill (~2 frames post-onset ≈ 32–38 s) plus debounce.
- Targets (data-time, from onset; at 10 dB / at 0 dB SNR; reference conditions L ≤ 3000 m for stick-slip):
  - stick-slip ≤ **60 s / 90 s** (LOW-DEEP wells: ≤ 2× these — periods and frames both double)
  - whirl ≤ **8 s / 15 s** at ≥ 120 RPM; rev-scaled at lower speed (floor ≈ 8 rev + 2 rev): ≤ **16 s / 30 s** at 60 RPM
  - bit bounce ≤ **12 s / 20 s** at ≥ 120 RPM; same rev-scaling: ≤ **20 s / 30 s** at 60 RPM

Evaluation cadence is per-profile (A1) in **data-time**; K = 2 consecutive confident evaluations required, the second containing ≥ 1 hop of data absent from the first.

**Why this choice.** Two tiers preserve the product story instead of weakening it: amber gives the operator the fast reaction the old 5 s number wanted; red is the auditable proof moment — and §19's palette already encodes exactly this (amber = advisory, red = confirmed *exclusively*). Every number above is a derived floor plus margin, with the derivation stated so it can be re-checked when parameters move. At the demo's 8× replay even the 60 s stick-slip confirmation fires 7.5 s (wall) into its 35 s segment (A21).

---

## A3 — Match statistics: corrected significance

*Resolves: "confidence 0.99 fires on 2 random collisions; gate 2 fails; entropy overstated" (critical). rc2: per-profile entropy under the new T_max values; underflow claim corrected; the statistic now reaches the wire format and UI.*

**Problem.** Real hash entropy under the A1 target zones is **~16–17 bits** (LOW: ~100 in-band f₁ bins × 127 Δk × 12 Δt ≈ 17.2 bits; ORDER: 49 × 127 × 10 ≈ 15.9 bits) — not 24. At the spec's scale the background rate λ is small but the number of simultaneous tests is large: **two** coincidental matches give uncorrected confidence 0.998 > 0.99, and with ~9,000 episode-bins tested per evaluation, spurious crossings occur constantly. K=2 debounce does not save it (overlapping windows are correlated).

**Change.** Replace §10's decision logic:

1. **λ excluding the max bin:** λ = max( (matched_pairs − max_bin) / (n_bins − 1), 0.05 ).
2. **Corrected significance:** p_corr = n_episodes × n_δbins × P(Poisson(λ) ≥ score).
3. **Alert condition (Tier 2):** p_corr < **1e-4** AND score ≥ **s_min = 8**, sustained K = 2 evaluations with ≥ 1 hop of fresh data.
4. **Display statistic (normative, closes the loop to the UI):** `confidence := 1 − p_corr`, clamped to [0, 1]. This is the *only* confidence shown anywhere. `active_detections` entries carry `{class, tier, confidence, p_corr, score, sssi}` (A8's example updated accordingly); §19's example copy becomes "Stick-slip confirmed — SS-014 · score 34 · p < 1e-9 · period 4.6 s".
5. The Detection payload reports score, λ, p_corr, and the full histogram — the Alignment View is unchanged, just honest.

Verified margins: random background at λ = 0.063 reaching score 8: p_corr ≈ 5e-11. The per-profile T_max shrinkage can inflate λ toward ~0.3; even there p_corr ≈ 1e-5 — still under threshold, so **s_min = 8 holds for λ up to ~0.3** (assert this bound in a unit test against the built library's measured λ). A genuine match at score 25 vs λ = 2: p_corr ≈ 3e-15 — eleven orders of magnitude inside the threshold. State the honest 16–17-bit entropy figure in §8.

**Why this choice.** Merely raising the confidence threshold was rejected: without the n_episodes × n_δbins correction the threshold's meaning silently drifts whenever the library grows. Correcting for the number of tests makes the threshold stable across library versions, which §31's versioning story requires.

---

## A4 — Stick-slip sanity gates and the f₀ physics prior

*Resolves: "±25 % of 4L/c_t gate unsatisfiable; non-cycling corners; quarter-wave prior biased high" (critical + note). rc2 blocking fix: the gate now tests the model the code actually integrates — rc1 gated against a rod-inertia predictor the 2-DOF model doesn't contain, and would have failed all 18 of the study's measured periods.*

**Problem.** v1.2 gates the simulated limit-cycle period against 4L/c_t; the lumped model's period scales as √(J_b·L), so 10–12 of 15 sweep corners fail regardless of code quality. Low-severity corners settle into steady sliding — no limit cycle at all. And the quarter-wave prior sits 34–109 % above the true fundamental once BHA inertia is included.

**Change.**

1. **Two predictors, two jobs (do not mix them):**
   - **T_model = 2π·√(J_b / k)** — the natural period of *the 2-DOF system the code integrates* (which contains no rod inertia by construction, A6). **This is the gate basis.**
   - **T_field = 2π·√(J_eff / k)**, J_eff = J_b + I_rod/3, I_rod = ρ·J_p·L — the continuous-rod prior for *real wells* (verified against the exact transcendental solution to 0.1–4 % across the sweep; worst at long strings with light BHAs). This is prose/UI-for-real-data only.
2. **Period gate:** measured limit-cycle period ∈ **[1.0, 2.0] × T_model**. (Study data lands at 1.01–1.24 at 120 RPM and up to ~1.78 at 60 RPM — the stick dwell grows as commanded RPM falls; 2.0 gives margin without admitting nonsense.)
3. **Stability screen (before gating):** corners with torque swing < 5 % after the startup transient did not develop a limit cycle — **expected physics**, not failure. Relabel them NORMAL_DRILLING (honest negatives) and log them in the build report. Gates 4–5 apply only to corners that limit-cycle.
4. **Stick gate:** min downhole RPM during the cycle < 5 % of commanded surface RPM.
5. **Swing gate:** torque swing ≥ 15 % of mean (unchanged).
6. **UI prior:** draw the marker at 1/T with a shaded band down to 1/(2.0·T), labeled "predicted range" — where T = T_model for synthetic wells (the library's actual comb lands inside by construction) and T = T_field for real wells. §31's "f₀ from 4L/c_t" is corrected to cite this (v1.2 also inverted it — 4L/c_t is a period). 4L/c_t survives in prose as the classical upper-bound intuition, labeled as such.

**Why this choice.** A gate must test the model the code integrates — rc1's own failure to do this (caught in verification) is the best possible demonstration of the rule. Relabeling non-cycling corners as NORMAL beats dropping them: it grows the negative class with realistic near-threshold operation, exactly where false-positive immunity matters.

---

## A5 — Whirl kinematics: name the reference frames

*Resolves: "orbit animated at the wrong rate; §23 stray factor k; N_b never stated" (major).*

**Problem.** Rolling-without-slip yields **two** rates that v1.2 conflates. The BHA center orbits the borehole (inertial frame) at Ω_orbit = −ω·d_b/(d_h − d_b) = **−N_b·ω**. A pipe-mounted sensor sees the contact/bending line sweep at Ω_sensor = −ω·d_h/(d_h − d_b) = **−(N_b+1)·ω**. The fingerprint (order N_b+1) correctly uses the sensor rate; §27 wrongly drives the on-screen *orbit* with it (~17 % fast in the worked example). §23 adds an undefined factor k colliding with torsional stiffness.

**Change.**
1. §3 gains the frame table above, and states the worked example has **N_b = 5** (5 blades → 6-lobe pattern).
2. twin_state.whirl.phase_rad integrates **Ω_orbit = −N_b·ω**. Wall-contact flashes keep the M = j·N_b+1 lobe pattern. The integration lives in **`engine/twin_kinematics.py`** (pure, testable — twist, whirl phase, bounce phase; the api layer owns message assembly and cadence), which also settles the §15 engine-purity question for twin state.
3. §23: the stray k is deleted; **j is reserved for the lobe integer, c_t for the wave speed, document-wide**.

---

## A6 — The 2-DOF equation transcription

*Resolves: "dead ·0 term and c_t symbol collision" (major).*

**Change.** The §2 model reads, normatively:

```
J_t·θ̈_t + k·(θ_t − θ_b) + c·(θ̇_t − θ̇_b) = T_motor(t)
J_b·θ̈_b − k·(θ_t − θ_b) − c·(θ̇_t − θ̇_b) = −T_friction(θ̇_b)
```

c is the single string-damping coefficient, c = 2ζ√(k·J_b), ζ default 0.05. No separate top-side damping in v1 (fresh symbol c_top if ever added). Note the model deliberately contains no rod inertia — which is exactly why A4 gates against T_model, not T_field.

---

## A7 — Anti-aliasing: synth ring band and the order-resampling path

*Resolves: "150–300 Hz rings alias at f_s = 400" (major ×2), "bare numpy.interp folds ring energy to order 11" (major). rc2 blocking fix: the filter cutoff is now clamped to the channel's own Nyquist — rc1's formula asked scipy for an unbuildable filter on the 100 Hz bounce channel above ~117 RPM.*

**Change.**
1. §3/§12.2 reconciled: impact rings are synthesized at **100–160 Hz** (≤ 0.8 × Nyquist at f_s = 400). One band, both sections.
2. Generator gate (all synth modules): no synthesized component above **0.45 × f_s**.
3. §9 order path — anti-alias low-pass before angular interpolation, zero-phase, cutoff:
   **f_c = min( 0.8 × 32 × min(f_rot in window), 0.45 × f_s_channel )**, and **skip the filter entirely when 64 × f_rot ≥ f_s_channel** (angular resampling is then pure upsampling — nothing to anti-alias). Verified: on ACC_LAT (400 Hz) the first term governs at all spec RPMs (25.6 Hz at 60 RPM… 59.7 at 140 — always above the order-2–14 band top of 14–32.7 Hz, always below the 100–160 Hz rings, constant ratio 1.83×); on ACC_AX (100 Hz) the clamp takes over above ~117 RPM instead of crashing.
4. `order_domain.py` owns the filter; sub-Ω_min windows are order-invalid per A15, never divided through.
5. The per-channel **effective order bandwidth min(32, 0.5·f_s/f_rot)** rule of A1 is enforced at library build for every hashed (class, channel) pair.

---

## A8 — twin_state example and multi-turn twist

*Resolves: "example violates its own T/k rule by 12×; WOB with bit off bottom" (major/critical). rc2 fix: rc1 corrected the depth but kept twist computed at the old depth (0.06 % off — same failure class, smaller).*

**Change.** The normative example: `"bit_depth_m": 3014.1, "hole_depth_m": 3014.1` (on bottom, so WOB 82 kN is legitimate), torque 14.8 kN·m, and **`"twist_rad": 47.16`** — computed at the printed depth: k = G·J_p/L = 945,950 / 3014.1 = 313.85 N·m/rad; 14,800 / 313.85 = 47.16 rad (7.51 turns). The `active_detections` entry becomes `{"class": "STICK_SLIP", "tier": 2, "confidence": 0.9999, "p_corr": 1.0e-9, "score": 34, "sssi": 0.42}` per A3.4. §27 gains: choreography distributes the full multi-turn wind-up across joints (totals routinely exceed 2π; 7.5 turns over 3 km is the physically real — and more dramatic — picture). k derives from the well-context config (A13) with L = current bit depth.

---

## A9 — One normative band table

*Resolves: "2–3 conflicting band definitions per class; Nyquist violations; order 2–12 ≠ 5–80 Hz at any spec RPM; band clipping" (majors). rc2 blocking fix: the build rule is scoped to hashed channels — rc1's "every bound channel" was violated by its own WOB row.*

**Change.** §5 becomes the **single normative table**; §2/§3/§4/§23 cite it.

| Class | domain / profile | hashing band | display band² | hashed channels | display-only channels |
|---|---|---|---|---|---|
| STICK_SLIP | time / LOW (or LOW-DEEP if pred. f₀ < 0.12 Hz) | 0.1–4 Hz (LOW-DEEP: 0.04–2 Hz) | same | TORQUE_SURF (primary), RPM_DH | — |
| WHIRL_BACKWARD | order / ORDER | orders 2–14 (≈ 2–33 Hz over 60–140 RPM) | 5–50 Hz + 100–160 Hz rings | ACC_LAT_X, ACC_LAT_Y | — |
| WHIRL_FORWARD | order / ORDER | orders 0.5–1.5 (1× ± sidebands) | — | ACC_LAT_X, ACC_LAT_Y | — |
| BIT_BOUNCE | order / ORDER | **orders 2–10** (covers lines 3, 6, 9) | 1–20 Hz | ACC_AX (primary) | **WOB** (twin/HUD; badged "partial band — not matchable") |
| NORMAL_DRILLING | all | per bound class band | — | all hashed channels above | — |

² *Display band* = the Hz range rendered on the time-domain spectrogram. It is never hashed and never enters the build rule or badge logic; only hashing bands do.

Rules:
1. **Build rule (hashed bindings only):** band_top ≤ 0.45 × f_s for every (class, **hashed** channel) pair. Enumerated: STICK_SLIP/TORQUE_SURF 4 ≤ 4.5 ✓, /RPM_DH 4 ≤ 4.5 ✓; WHIRL/ACC_LAT_* 33 ≤ 180 ✓; BOUNCE/ACC_AX 21 Hz-equiv ≤ 45 ✓ and orders 2–10 ≤ effective order bandwidth 21.4 at 140 RPM ✓. WOB (0.45 × 10 = 4.5 Hz) is *display-only* precisely because it fails this rule — the same honest-badging treatment as 1 Hz torque.
2. **Badge logic is band-aware:** a channel "sees" a class only if the class's full *hashing* band fits under 0.45 × f_s (and, in ORDER, inside the effective order bandwidth). 1 Hz torque and 10 Hz WOB badge as "fundamental/partial band — insufficient for matching."
3. Full-gauge rolling whirl (order d_h/(d_h−d_b) ≈ 15–35 at realistic clearances) is **out of scope for v1**, stated in one sentence so nobody sizes filters expecting it.

---

## A10 — Canonical channel registry and class bindings

*Resolves: "three naming schemes; BENDING/HOOKLOAD unproduced" (major). rc2 fix: the normal generator's producer row no longer recreates the BENDING bug — rc1 left NORMAL_DRILLING bound to channels §12.4 never emitted, which would have voided gate 2's pump-comb test.*

**Change.** One registry table (§16, mirrored as store data — A12):

| Channel | uom | f_s | produced by | consumed by |
|---|---|---|---|---|
| TORQUE_SURF | kN·m | 10 | synth §12.1, **§12.4**, Volve, live | STICK_SLIP (hashed), SSSI, twin |
| RPM_SURF | rpm | 10 | all synth, Volve, live | order resampler, twin |
| RPM_DH | rpm | 10 | synth §12.1 | STICK_SLIP (hashed), twin |
| ACC_LAT_X / _Y | g | 400 | synth §12.2, **§12.4** | WHIRL_* (hashed) |
| ACC_AX | g | 100 | synth §12.3, **§12.4** | BIT_BOUNCE (hashed) |
| WOB | kN | 10 | synth §12.3, **§12.4**, Volve, live | BIT_BOUNCE (display), twin |
| HOOKLOAD | kN | 10 | **synth §12.3 (new)**, Volve | twin |
| BIT_DEPTH, HOLE_DEPTH, BLOCK_POS | m | 1 | **scenario player (new)**, from well config | twin, rig strip |

Rules: §5/§11 bindings use these exact names (bare "TORQUE"/"ACC_LAT" retired). ACC_LAT binding = each of X/Y fingerprinted; either fires the class. **BENDING dropped from v1.** §12.3 adds HOOKLOAD = buoyed string weight − WOB + axial oscillation. **§12.4 (normal) emits the full surface set — TORQUE_SURF, RPM_SURF, WOB, ACC_AX, ACC_LAT_X/Y — with the pump comb injected on TORQUE_SURF and WOB** (SPP is out of scope in v1; pump pressure pulsation couples into both mechanically, and gate 2 needs the comb on a stick-slip-bound channel to be a real false-positive test). Scenario player emits the three rig-context channels at 1 Hz from well config, making §29's "every animated quantity traceable to a stream field" literally true. twin_state gains the explicit field ← channel map; §13 gains the Volve mnemonic→name table.

---

## A11 — Generator parameter table: durations, constants, sweeps, noise policy

*Resolves: "durations nowhere; constants unpinned; sweeps unenumerated; §12.5 ambiguity" (major). rc2: RPM profiles pinned with numbers; estimates restated with their assumptions.*

**Change.** New normative table in §12:

**Durations:** stick-slip **180 s**; whirl **60 s**; bounce **60 s**; normal **120 s**. (Benchmark/scenario *runs* are generated to any needed length with query-side seeds and are distinct from library episodes — A19/A21.)

**Pinned constants:** T_c = 6 kN·m; T_s = ratio × T_c; J_t = 1000 kg·m²; ω_s = 1 rad/s; ζ = 0.05 → c = 2ζ√(k·J_b); PI top drive K_p = 500 N·m·s/rad, K_i = 50 N·m/rad; lobe integer **j = 1** (M = N_b + 1).

**RPM profiles (pinned):** const = **120 RPM**; ramp = **80→140 RPM** linearly over the episode (whirl — matches gate 3 and §34) and **80→130 RPM** for bounce (keeps order 9 ≤ 19.5 Hz inside the display band); dither = **120 ± 10 RPM at 0.1 Hz**.

**Sweeps:** stick-slip L{1500, 2250, 3000, 4000, 5000} × Ω{60, 90, 120} × ratio{1.3, 1.6, 2.0} × J_b{100, 200, 400} = **135** (non-cycling corners → NORMAL per A4; deep corners auto-select LOW-DEEP per A1); whirl N_b{4,5,6} × severity{1–3} × RPM-profile{const, ramp, dither} = **27**; bounce severity{1–3} × RPM-profile = **9**; normal **5** variants (2 with pump combs at SPM {60, 110} → triplex comb fundamentals 3.0 / 5.5 Hz, on TORQUE_SURF + WOB per A10).

**Noise policy (replaces "applied to all"):** the library is **clean**; SNR {20, 10, 3, 0} dB, gain ±20 %, dropouts 100–500 ms, and 1 Hz decimation apply **query-side only** (benchmark runs and scenario data). Wang's convention; the only reading under which "benchmark at each SNR" means anything.

**Size/build estimates (with assumptions stated):** ≈ 270k stick-slip + 210k whirl + ~40k bounce (ACC_AX only, per A9) + normal at ~10–20 % of its peak-cap budget (noise rarely survives the median+8 dB gate; the build report records actuals) ≈ **0.5–0.6 M hashes, ~20 MB** — consistent with §18's 10⁶ scale. Build budget: 1–2 s per stiff ODE run × 135 + synthesis + hashing + insert — **≤ 5 min holds without heroics**; CI measures and records it.

---

## A12 — Store schema v2

*Resolves: "no approval state; no profile/channel columns; no index DDL (17× miss without it); t_anchor units" (majors). rc2: class_bindings gains the role column A9 needs.*

**Change.** `store/schema.sql`:

```sql
CREATE TABLE libraries (
  version      TEXT PRIMARY KEY,
  created      TEXT NOT NULL,
  notes        TEXT,
  status       TEXT NOT NULL DEFAULT 'built'
               CHECK (status IN ('built','validated','approved')),
  approved_by  TEXT,
  approved_at  TEXT
);
CREATE TABLE app_state (key TEXT PRIMARY KEY, value TEXT);
  -- 'active_library_version', 'project_stage', ...
CREATE TABLE episodes (
  id TEXT PRIMARY KEY,
  slug TEXT UNIQUE,              -- 'stick_slip/L3000_rpm120_ts1.6_jb200'
  class TEXT NOT NULL,
  library_version TEXT NOT NULL REFERENCES libraries(version),
  duration_s REAL NOT NULL,
  params_json TEXT NOT NULL
);
CREATE TABLE episode_channels (
  episode_id TEXT REFERENCES episodes(id),
  channel TEXT NOT NULL, fs REAL NOT NULL
);
CREATE TABLE fingerprints (
  hash INTEGER NOT NULL,         -- 24-bit packed
  episode_id TEXT NOT NULL REFERENCES episodes(id),
  channel TEXT NOT NULL,
  profile TEXT NOT NULL,         -- 'LOW'|'LOW_DEEP'|'ORDER'
  domain TEXT NOT NULL,          -- 'time'|'order'
  t_anchor INTEGER NOT NULL      -- hop-frame index within the episode
);
CREATE INDEX idx_fp_lookup  ON fingerprints(hash, profile, domain);
CREATE INDEX idx_fp_episode ON fingerprints(episode_id);
CREATE TABLE profiles (          -- the A1 table, as data
  name TEXT PRIMARY KEY, domain TEXT, fs REAL, n INTEGER, hop INTEGER,
  samples_per_rev INTEGER, t_max INTEGER, window_w TEXT, hashed INTEGER
);
CREATE TABLE class_bindings (    -- the A9/A10 tables, as data
  class TEXT, channel TEXT,
  role TEXT CHECK (role IN ('hashed_primary','hashed','display')),
  min_fs REAL
);
```

The matcher filters postings on (hash, profile, domain) **and** active library version **and** the class's `hashed*` channels — §11's per-class binding lives here. `t_anchor` = hop-frame index; δ computed in frames, δ-bin width 3 frames. `POST /libraries/{v}/activate` rejects status ≠ 'approved' (§31's gate, enforced). The episode **slug** is the canonical address for UI copy and synthetic scenario sources.

---

## A13 — Repo layout and stack additions

*Resolves: "half of Part VI/VII homeless" (major). rc2: twin kinematics module, dual-serve mode, import format, Volve segment registry added.*

**Change.** §15's tree gains:

```
drillprint/
├── cli.py               # typer: drillprint {library,bench,demo} — [project.scripts] entry
├── engine/twin_kinematics.py   # pure: twist, whirl/bounce phase integration (A5)
├── config/              # well-context schema + loader (well01.yaml: L, N_b, d_h, d_b, channels)
├── scenarios/           # *.json manifests (§32)
├── frontend_dist/       # committed UI build — serves the §33 zero-network demo
├── data/
│   ├── volve/           # user-placed (A18) — never committed; segments.yaml registry
│   └── demo_cache/      # prebuilt flagship fingerprint DB + pre-generated run data
```

Stack gains **typer**. `config/` is the single source for L (→ k), N_b (→ orders, bit geometry), hole/bit diameters, channel set. The `drillprint` CLI is the canonical user surface (`library build --config`, `library import`, `bench run --library`, `demo`); module entry points remain for CI; docs/UI empty-states reference the CLI only. **`library import` format:** CSV or parquet with columns `t0, t1, class, channels...` per labeled interval. **Volve segment registry:** `data/volve/segments.yaml` maps segment id → file, t-span, provenance — the resolver for `volve:` scenario sources. **Dual-serve mode:** frontend reads its API base from env-injected config — same-origin default for `drillprint demo`; explicit base + CORS allowlist for the Render/Vercel hosted split. `--record` deferred to v1.4 unless its headless-capture dependency is explicitly accepted. Tests-tree comment corrected to cite **§22**.

---

## A14 — /ws/monitor contract v2 and the stream clock

*Resolves: "three vs five types; no timestamps; dual-source choreography; wall-clock breaks determinism" (majors). rc2: live-mode epoch defined; hold/lerp ownership split; tier semantics in choreography.*

**Change.**
1. §17 enumerates **five** types: `spectral_frame`, `constellation`, `detection`, `twin_state`, `scenario_event`.
2. Every message carries **`t` — the stream clock**: data-time seconds since the run epoch. Scenario/replay runs: epoch = 0.0. **LIVE mode: epoch latches at the session's first accepted ingest frame; t = t0_wall − t0_first** — so monitor t is run-relative in both modes and "nothing changes between simulate and live" stays true. Wall-clock never appears in the data plane. Constellation peaks carry t in the same clock (+ revolution index in ORDER).
3. `spectral_frame` carries its uint8 scale: `{db_floor, db_ceil}`.
4. **Choreography derives exclusively from `twin_state.active_detections`.** Entries carry `tier` (A3.4): **tier 2 triggers motion choreography; tier 1 drives amber HUD/emissive only — never a motion signature** (§19's "red exclusively for confirmed" extended to motion). Single-socket TCP ordering then satisfies §29's 200 ms gate.
5. `latency_ms` and measured-wall-time diagnostics live in a `diag` sub-object, **excluded from the determinism hash** (A20).
6. twin_state cadence: one message per **40 ms of data-time**. Fields carry the latest channel-native sample (**zero-order hold server-side; clients lerp for display** — ownership stated, ending the duplicated-interpolation ambiguity).
7. New REST: `GET /scenarios`.

---

## A15 — Ingestion contracts: gaps, alignment, Ω_min, backpressure

*Resolves: "alignment/dropouts/ordering unowned" (major). rc2: the ≤ 1 hop gap case — exactly where §12.5's dropouts land — is now defined; backpressure added.*

**Change.** `ingest/sessions.py` contracts:
1. **Monotonic t0 per channel**; violations dropped and counted (surfaced in `/health`).
2. **Gap policy, complete:** gaps **≤ 1 hop** (in the profile's own hop unit) are linearly interpolated, counted, and flagged in the frame's `diag`; gaps **> 1 hop** skip every matcher window they overlap, flagged in the monitor stream. Inequality is deliberate and non-strict on the interpolate side: a 500 ms dropout = exactly 1.0 ORDER hop at 120 RPM → interpolated. No zero-filling anywhere. Benchmark runs inherit this policy, so dropout robustness is measured as "how quickly matching resumes" — the honest metric.
3. **Aligned-view API:** `sessions.get_window(channels, t_span)` returns time-aligned arrays; RPM_SURF is interpolated onto the vibration grid **here**; `order_domain.py` consumes only aligned pairs. Alignment ownership: sessions.py, full stop.
4. **Ω_min guard:** windows with min RPM < **10 RPM** are order-invalid (badged; no order evaluation; no division).
5. **Backpressure:** bounded per-channel ingest buffers; above **30 s** of backlog the server drops-oldest and NACKs the frame (`{"ack": false, "reason": "backlog"}`), counted in `/health`.
6. Registry entries (A10) carry profile assignment and class observability — the scheduler is data-driven.

---

## A16 — De-circularizing the order-invariance test

*Resolves: "invariance proof circular; no RPM channel emitted" (major). rc2: the negative arm is made real — under A1/A9 the production library has no time-domain whirl hashes, so "fails in time domain" would have been vacuously true.*

**Change.**
1. §12.2 emits **RPM_SURF at 10 Hz as a measured channel**: ±1 RPM Gaussian noise, optional 100 ms latency corner. The generator's internal profile is not exported; resampler/matcher consume only the measured channel.
2. **M2 test artifact:** a *test-only* time-domain (HIGH-profile) fingerprint set built from the constant-RPM whirl episodes — never shipped in a production library. The invariance suite asserts all four cells: constant-RPM query matches BOTH the time-domain test set and the ORDER library; ramp-RPM query **fails** the time-domain set (smearing — the §9 contribution, now demonstrated against real content) and **matches** the ORDER library at high confidence.
3. One **Jeffcott-integrated episode** as a physics cross-check: must match the signal-synthesized ORDER library, defending against "you synthesized the answer in."

---

## A17 — Milestone resequencing

*Resolves: "M1's flagship test requires M2's module" (major).*

**Change.** M1 (Synthesis) tests only what needs no resampling: A4's gates (T_model period gate, stability screen, stick/swing), whirl/bounce **line presence in Hz** at RPM-proportional frequencies, time-domain smearing under ramp. M2 owns `order_domain.py`, the A7 filter, and the full A16 invariance suite. Backend halves of frontend-coupled gates split out: gate 4 backend = observability metadata emitted; gate 6 backend = twin_state log self-consistent (A8 test values; whirl phase continuity at −N_b·ω; null-safety). Rendered-state audit and 30 fps stay in M6 (user-led frontend).

---

## A18 — Volve licensing resolution

*Resolves: "§13 forbids scripted access while §33 bundles Volve in-repo and gate 7 demands detections from it" (major).*

**Change.**
1. §13's posture wins: **no Volve data in the repo until the current Equinor license text is verified to permit redistribution of extracts with attribution.** If permitted: `LICENSE-data` + provenance metadata accompany the cache. If not: user-placed only.
2. Flagship segment 4 becomes **optional**: absent data → scenario player skips it with the caption "Volve data not present — see README"; the demo runs as a 3-segment show.
3. Gate 7 asserts segments 1–3 from a clean clone. **Gate 7b** (only when Volve data present) asserts playback, spectrogram streaming (on LOW-DECIM per A1 for ~1 Hz channels), and correct badges — **never a guaranteed detection** (at 1–10 s cadence some segments are entirely blind to every class; the UI must say so).

---

## A19 — Benchmark protocol v2

*Resolves: "no scoring rules; no baseline calibration; 'win decisively' unfalsifiable" (major). rc2: T_tol now ≥ the A2 targets it scores (rc1 scored A2-compliant detections as false positives); late ≠ FP.*

**Change.**
1. **Event scoring.** Event = [onset, offset] from generator metadata. TP = first correct-class Tier-2 alert within [onset, onset + T_tol], inclusive. **T_tol per class = 1.3 × the applicable A2 Tier-2 target at the run's RPM and SNR, rounded up** — concretely: stick-slip 120 s; whirl 20 s (≥ 120 RPM) / 40 s (60 RPM); bounce 26 s / 40 s. Invariant, asserted in the bench code: **T_tol ≥ the A2 target for the same conditions.** Wrong-class or on-normal alerts = FP. **Late correct-class alerts = FN plus a separately-reported late count — never FP.** One detection credited per event. Latency = alert − onset, data-time.
2. **Runs:** ≥ 10 composite runs × ≥ 30 min data-time per SNR; seeds = base + run_index, recorded; rates per **data-hour**.
3. **Split:** clean library (A11); queries freshly generated, disjoint seeds *and* parameter draws (unchanged — this was sound).
4. **Calibration:** baseline thresholds fit on a normal-only validation run to **1 FA/data-hour**, frozen. Tier-1 advisories calibrated the same way to ≤ 2/data-hour (A2). DrillPrint Tier-2 thresholds fixed by A3. Then everything is scored and reported as-is; "should win decisively" is deleted as normative language.

---

## A20 — Demo determinism and the cold-start cache

*Resolves: "byte-identical reset impossible; 'from cache' undefined" (major).*

**Change.**
1. **Virtual clock.** Run epoch t = 0.0; all cadences in data-time (A14); replay speed only paces delivery.
2. **Canonical output log** = ordered /ws/monitor messages with `diag` stripped. M7 hashes it across two runs — byte-identical, since the data plane reads no wall clock and all RNGs are seeded.
3. **Cache = prebuilt artifact.** `data/demo_cache/` ships the approved flagship fingerprint DB (~20 MB) + pre-generated run data. "Builds from cache" = **file copy + activate (< 1 s)**. Missing cache → full build with a console warning that the 15 s guarantee doesn't apply. CI asserts the cached path ≤ 15 s on its machine class, documented as such.

---

## A21 — Flagship timeline reconciliation

*Resolves: "manifest 20 s vs script 15 s; 115 s vs 2 min; ±2 s names no clock" (major). rc2: run-source addressing defined; §32 example corrected.*

**Change.**
1. **Units:** manifest `t`/`dur` = wall-clock presentation seconds; `speed` multiplies data consumption → segments consume 120 / 280 / 240 / 240 s of data.
2. Segment 1 = **15 s**; segments 15 + 35 + 30 + 30 = 110 s + 10 s close (screen switch) = 120 s. One story across §32/§34.
3. **Sources reference generated runs**, form `run:<scenario>/<segment-id>` (e.g. `run:flagship/seg2_stick_slip`), resolving to a run manifest in `data/demo_cache/` that records generator, params, seed, duration. Synthetic library episodes keep the A12 slug form for UI copy; `volve:` sources resolve via `data/volve/segments.yaml` (A13). **§32's example is rewritten accordingly** — e.g. segment 2's run manifest records `stick_slip, L=3000, rpm=120, ratio=1.6, jb=200, seed=1042, dur=280` (the old "sev2" matched no stick-slip sweep axis).
4. Gate 7 timestamps: **wall-clock ± 2 s**, expected times computed from A2 at 8× — stick-slip Tier-2 fires ~5–7.5 s wall into its 35 s segment; whirl ~1–2 s in (fill at the ramp's 80 RPM start). The beats land with margin.

---

## A22 — Editorial corrections (apply verbatim)

1. §15 tree comment: "see **§22** acceptance gates" (was §19).
2. §31: "f₀ from **1/T** per A4.6" (4L/c_t is a period; v1.2 inverted it).
3. SSSI = "surface **stick-slip severity** index" everywhere.
4. §2 waveform prose: "full harmonic comb at n·f₀, roll-off shaped by the friction nonlinearity (between sawtooth ~1/n and square-like odd-dominant)"; M1 asserts comb *spacing* = f₀, never an odd/even pattern (the model's own 2f₀ is ~5× stronger than 3f₀).
5. §20: "§0.1" → "§0, item 1".
6. Manifests reference libraries as `{"library": "v3", "required_status": "approved"}`; "v3-approved" retired.
7. §16 example t0 updated to a 2026 epoch (cosmetic; LIVE-mode clock per A14.2).
8. Part V-B renumbered Part VIII at next re-issue (or one-line note); References move to the end.
9. c_t reserved for wave speed; j for the lobe integer (A5/A6).
10. §6's "1 Hz torque can still see stick-slip" qualified per A9 badge logic: fundamental only — insufficient for matching.

## A23 — Peak-picking determinism pins

§7 additions — two real determinism holes and three reproducibility pins: **(real)** tie-break for equal-magnitude peaks = (lower k, then lower m) — §12.5's dropouts create exact-tie plateaus and §33 demands byte-identical reruns; ε = 1e-12 applied after per-channel normalization; β default = **8** dB. **(confirmatory, for cross-implementation reproducibility — the spec already implies them, per the study's own refutation pass)** Hann is the periodic form (`sym=False`; the §6 formula already is periodic Hann), and `maximum_filter` boundary handling is pinned to `mode='constant', cval=-inf` (provably equivalent to reflect for a max filter, pinned anyway so two implementations can't differ).

---

## Rewritten acceptance gates (consolidated)

1. **Gate 1 (stick-slip, reference conditions L ≤ 3000 m, ≥ 90 RPM):** 0 dB SNR run → Tier-1 advisory ≤ 20 s; Tier-2 ≤ 90 s with p_corr < 1e-4, score ≥ 8; SSSI reported. (LOW-DEEP wells: doubled targets, same statistics.)
2. **Gate 2 (false alerts):** 1 h data-time of pump-comb normal runs per SNR → **zero Tier-2 alerts AND Tier-1 within its calibrated ≤ 2/h budget**.
3. **Gate 3 (RPM ramp):** whirl under 80→140 ramp → sustained Tier-2 in ORDER; the same query matches the M2 time-domain test set at constant RPM but fails it under the ramp (all four A16 cells asserted).
4. **Gate 4 (backend half):** replay runs; spectrograms stream (LOW-DECIM for ~1 Hz channels); band-aware badges correct, including "entirely blind" and "partial band" channels; stick-slip-band findings labeled "surface-cadence limited."
5. **Gate 5:** `GET /bench/report` complete per A19, baseline + Tier-1 calibration records included.
6. **Gate 6 (backend half):** twin_state log self-consistent — twist_rad = torque/k exactly (A8 values); whirl phase continuous at Ω_orbit = −N_b·ω; tier semantics per A14.4; null-safe; rig-context channels present for synthetic runs.
7. **Gate 7:** `drillprint demo` from clean clone (cache present) → cold start ≤ 15 s; segments 1–3 fire expected detections at expected wall times ± 2 s; **segment 1: zero Tier-2 AND zero Tier-1**; sustained whirl detection through the ramp; determinism hash identical across two runs. **Gate 7b** (Volve present): segment 4 plays with honest badges; no detection guarantee.

---

## Traceability: findings → amendments

| Finding (SPEC_STUDY.md) | Amendment |
|---|---|
| LOW window → 1 frame → zero hashes (critical) | A1 |
| Latency gates impossible (critical ×3) | A1, A2 |
| Poisson threshold fires on 2 collisions; entropy overstated (critical) | A3 |
| §12.1 gate unsatisfiable; non-cycling corners; quarter-wave bias (critical + note) | A4 |
| Whirl frame conflation; §23 stray k; N_b unstated (major ×2) | A5, A22.9 |
| ODE ·0 term, c_t collision (major) | A6 |
| Ring band aliases at 400 Hz (major ×2) | A7 |
| Order resampling lacks anti-alias filter (major) | A7 |
| twin_state twist 12× off; WOB off-bottom (major + critical) | A8 |
| Band tables conflict; Nyquist violations; order-vs-Hz impossibility; clipping (major ×4 + minor) | A9 |
| Three naming schemes; BENDING/HOOKLOAD unproduced (major) | A10 |
| Durations/constants/sweeps unpinned; §12.5 ambiguity (major) | A11 |
| Schema gaps (major ×2) | A12 |
| Repo homes missing (major) | A13, A14.7 |
| Message-contract drift; timestamps; choreography sourcing (major) | A14 |
| Ingestion alignment/gaps/ordering unowned (major) | A15 |
| Invariance circularity; RPM channel missing (major) | A16 |
| M1 needs M2; frontend-coupled gates (major) | A17 |
| Volve license contradiction; gate 7 overreach; no slow-channel profile (major) | A18, A1 |
| Benchmark unreproducible; baseline unfalsifiable; gate-2 flakiness (major) | A19, A3, A2 |
| Determinism impossible; cache undefined (major) | A20, A14.5 |
| Demo timeline disagreement; clock/addressing ambiguity (major + minor) | A21 |
| MID window 4 frames (major) | A1 |
| Peak-picking determinism (minor) | A23 |
| Sawtooth/odd-harmonic misattribution (minor) | A22.4 |
| Cross-refs, inversions, naming minors | A22 |

**rc1 → rc2 (issues found by this amendment's own verification round):** A4 gate re-based on T_model (rc1 failed all 18 measured periods); A9 rule scoped to hashed channels + WOB demoted to display (rc1 self-violating); A7 cutoff clamped to channel Nyquist (rc1 unbuildable on ACC_AX > 117 RPM); A8 twist recomputed at the printed depth (47.16); A2 targets re-derived from partial-window mechanism + Tier-1 calibration added; A19 T_tol ≥ A2 targets + late ≠ FP; A3 per-profile entropy + underflow claim corrected + statistic wired into UI/twin; A16 negative arm made non-vacuous; A15 ≤ 1 hop gap defined + backpressure; A10 normal-generator producers fixed + pump-comb carrier pinned; A11 RPM profiles pinned; A1 LOW-DEEP + LOW-DECIM profiles added; live-mode epoch defined; §32 example and run addressing fixed; A23 reworded to match the study's refutation results.

---

*End of amendment v1.3-rc2. On approval, fold into a re-issued DRILLPRINT_SPEC v1.3 master, then begin M0.*
