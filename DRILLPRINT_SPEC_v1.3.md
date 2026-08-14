# DRILLPRINT — Deterministic Spectral Fingerprinting for Real-Time Drilling Dysfunction Recognition

**Technical Specification & Build Document v1.3**
Author: Johnpaul Okeke · August 2026 · v1.3 re-issue: August 2026
Target: backend + engine implementation; interface built in parallel.

---

## Changelog v1.2 → v1.3

Verification-hardened re-issue; the following amendments are folded into the body:

- A1 — Detection windows, profiles, and the new ORDER, LOW-DEEP and LOW-DECIM profiles (§6, §10).
- A2 — Latency targets and the two-tier alert model (§18).
- A3 — Match statistics: corrected significance (§8, §10).
- A4 — Stick-slip sanity gates and the f₀ physics prior (§2, §12.1, §20, §31).
- A5 — Whirl kinematics: reference frames named (§3, §24, §27).
- A6 — The 2-DOF equation transcription corrected (§2).
- A7 — Anti-aliasing: synth ring band and the order-resampling path (§3, §9, §12).
- A8 — twin_state example and multi-turn twist (§24, §27).
- A9 — One normative band table (§5).
- A10 — Canonical channel registry and class bindings (§5, §12, §13, §16, §24).
- A11 — Generator parameter table: durations, constants, sweeps, noise policy (§12).
- A12 — Store schema v2 (§15).
- A13 — Repo layout and stack additions (§15, §33).
- A14 — /ws/monitor contract v2 and the stream clock (§17, §24, §27).
- A15 — Ingestion contracts: gaps, alignment, Ω_min, backpressure (§16).
- A16 — De-circularized order-invariance test (§12.2, §21).
- A17 — Milestone resequencing (§21, §29).
- A18 — Volve licensing resolution (§13, §32, §33, §35).
- A19 — Benchmark protocol v2 (§14).
- A20 — Demo determinism and the cold-start cache (§33).
- A21 — Flagship timeline reconciliation (§32, §34, §35).
- A22 — Editorial corrections (document-wide).
- A23 — Peak-picking determinism pins (§7).

Structural: Part V-B (3D digital twin, §24–§29) moves after Part VII and is retitled
Part VIII, keeping its section numbers; the References (§23) move to the very end of
the document, keeping their number.

---

## 0. Thesis

DrillPrint recognizes drilling dysfunctions (stick-slip, bit whirl, bit bounce) from streaming rig
sensor data the same way Shazam recognizes a song from a noisy bar recording: by reducing the
signal to a sparse constellation of time–frequency peaks, hashing peak pairs combinatorially,
and detecting *time-offset-consistent clusters* of hash matches against a fingerprint library.

Why this stands out at a research level:

1. **Deterministic, not ML.** Every detection decomposes into an auditable chain:
   raw samples → STFT frames → peaks → hashes → offset histogram → score. No training, no
   black box, no dataset bias. This is a deliberate counter-position to the ML-detector
   literature (and to the author's own ML work — DrillGuard), demonstrating *range*.
2. **Physics-anchored fingerprints.** Unlike music, drilling dysfunctions have *predictable*
   spectral structure derivable from first principles (drillstring torsional natural frequency,
   whirl kinematics — the sensor-frame line at Ω = −ω(N_b + 1); the inertial orbit runs at
   −N_b·ω (§3) — and bit-bounce at 3× rotary for tricone bits). The fingerprint
   library is therefore not just empirical — parts of it can be *generated from the physics*
   and validated against field data. This physics ⇄ signal-theory bridge is the core
   intellectual contribution.
3. **RPM-invariance via order-domain resampling.** Naïve Shazam matching breaks when the
   "song" changes tempo. Drilling signals change tempo constantly (RPM varies). DrillPrint
   resamples signals from the time domain into the *angle domain* (samples per revolution),
   making fingerprints invariant to rotary speed. This is the adaptation that elevates the
   project from "Shazam clone on different data" to a genuine methodological transfer.
4. **Enterprise-shaped delivery.** WITSML-style channel ingestion, API-first FastAPI service,
   versioned fingerprint libraries, live WebSocket streaming, benchmark tab with
   precision/recall against a naïve FFT-threshold baseline.

Working one-liner: *"Shazam for drilling dysfunctions — deterministic, explainable,
physics-grounded, real-time."*

---

# PART I — THE PHYSICS

## 1. The drillstring as a dynamic system

A drillstring is a slender torsional-axial-lateral waveguide: kilometres of drillpipe
(low stiffness, low inertia per length) terminated by a bottomhole assembly, BHA
(drill collars + bit: high inertia, high stiffness). Energy enters at the top drive
(surface rotation at commanded RPM) and at the bit-rock interface (cutting forces,
friction). Three vibration families matter:

| Mode      | Axis        | Canonical dysfunction | Primary surface/downhole observable |
|-----------|-------------|-----------------------|--------------------------------------|
| Torsional | rotation θ  | Stick-slip            | Surface torque, downhole RPM         |
| Lateral   | x, y        | Whirl (fwd/bwd)       | Radial/tangential acceleration, bending moment |
| Axial     | z           | Bit bounce            | Axial acceleration, hookload, WOB    |

These are coupled (e.g., stick-slip's slip phase can trigger whirl; whirl impacts can
excite axial modes), but their *spectral signatures* are separable — which is exactly
what makes fingerprinting viable.

## 2. Stick-slip (torsional)

**Mechanism.** The BHA is held by friction (bit-rock + wellbore wall contact). The top
drive keeps rotating, winding the drillpipe like a torsion spring. When stored torque
exceeds static friction, the BHA releases and over-speeds (downhole RPM reaching 2–4×
surface RPM, momentarily even reversing), then re-sticks. The cycle repeats at the
drillstring's fundamental torsional natural frequency.

**Spectral signature (the fingerprint's physical basis):**
- Fundamental torsional oscillation at ~0.1–0.5 Hz for typical string lengths
  (field-reported LFTO fundamental ≈ 0.3 Hz; characteristic surface-torque period
  2–8 s, increasing with measured depth). Hashing/display bands: see the normative
  band table in §5 (0.1–4 Hz on the LOW profile; 0.04–2 Hz on LOW-DEEP).
- Waveform is **sawtooth-like** in surface torque (slow wind-up, sharp release) →
  a **full harmonic comb at n·f₀**, roll-off shaped by the friction nonlinearity
  (between sawtooth ~1/n and square-like odd-dominant). The *harmonic comb structure*
  is the constellation the fingerprinter will latch onto. Tests assert comb *spacing*
  = f₀, never an odd/even amplitude pattern (the 2-DOF model's own 2f₀ is ~5× stronger
  than 3f₀).
- Torque swing typically ~15%+ of mean surface torque in developed stick-slip.
- **Period prediction — two predictors, two jobs (do not mix them):**
  - **T_model = 2π·√(J_b / k)** — the natural period of *the 2-DOF system the code
    integrates* (which contains no rod inertia by construction — see the model below).
    This is the basis for every synthesis sanity gate (§12.1).
  - **T_field = 2π·√(J_eff / k)**, J_eff = J_b + I_rod/3, I_rod = ρ·J_p·L — the
    continuous-rod prior for *real wells* (verified against the exact transcendental
    solution to 0.1–4 % across the sweep; worst at long strings with light BHAs).
    Prose/UI-for-real-data use only.
  - The classical quarter-wave estimate f₀ ≈ (1/4)·(c_t / L), with torsional wave
    speed c_t = √(G/ρ) ≈ 3,100 m/s in steel (G ≈ 79.6 GPa, ρ ≈ 7,850 kg/m³);
    L = 3,000 m → f₀ ≈ 0.26 Hz — survives as the classical *upper-bound intuition*
    only: it sits well above the true fundamental once BHA inertia is included. The
    engine's physics prior is **f₀ = 1/T** (T = T_model for synthetic wells, T_field
    for real wells), letting the engine *predict* where to look given bit depth — a
    physics prior injected into the matcher.
- **UI prior:** the spectrogram marker is drawn at 1/T with a shaded band down to
  1/(2.0·T), labeled "predicted range" — where T = T_model for synthetic wells (the
  library's actual comb lands inside by construction) and T = T_field for real wells.

**Lumped-parameter model (used for synthetic fingerprint generation, §12):**
a 2-DOF torsional pendulum —

```
J_t·θ̈_t + k·(θ_t − θ_b) + c·(θ̇_t − θ̇_b) = T_motor(t)
J_b·θ̈_b − k·(θ_t − θ_b) − c·(θ̇_t − θ̇_b) = −T_friction(θ̇_b)
```

- J_t: top-drive + drawworks equivalent inertia (≈ 500–2,000 kg·m²)
- J_b: BHA inertia (≈ 100–400 kg·m²)
- k: drillpipe torsional stiffness, k = G·J_p / L, with polar second moment
  J_p = (π/32)(D_o⁴ − D_i⁴). For 5" drillpipe (D_o=0.127 m, D_i=0.1086 m) → J_p ≈ 1.19e-5 m⁴;
  L = 3,000 m → k ≈ 316 N·m/rad.
- c: the single string-damping coefficient, **c = 2ζ√(k·J_b)**, ζ default 0.05. No
  separate top-side damping in v1 (a fresh symbol, c_top, if ever added — **c_t is
  reserved for the torsional wave speed, document-wide**).
- The model deliberately contains **no rod inertia** — which is exactly why the §12.1
  period gate tests against T_model, not T_field.
- T_motor: top-drive control — model as stiff PI speed controller tracking Ω_set
  (this reproduces the realistic surface response: near-constant RPM, oscillating torque)
- T_friction: velocity-weakening friction at the bit — **Stribeck model**:

```
T_f(θ̇_b) = [T_c + (T_s − T_c)·exp(−|θ̇_b|/ω_s)]·sign(θ̇_b) + c_v·θ̇_b
```

  T_s: static (breakaway) torque, T_c: Coulomb torque, ω_s: Stribeck velocity
  (≈ 0.5–2 rad/s), c_v: viscous term. The T_s > T_c drop is what makes the
  equilibrium unstable and generates the limit cycle. Numerically, regularize the
  sign() with tanh(θ̇_b/ε), ε ≈ 1e-3, or implement Karnopp's zero-velocity band to
  avoid chatter; integrate with SciPy `solve_ivp` (LSODA or Radau — the system is stiff).

**Severity index (industry-aligned, shown in UI):** surface stick-slip severity index
SSSI = (T_max − T_min) / (2·T_mean) over a window band-filtered around f₀ —
mirrors the patented surface-detection approach and gives DrillPrint a
conventional metric to display *next to* its fingerprint confidence.

## 3. Bit / BHA whirl (lateral)

**Mechanism.** The bit or BHA center of rotation walks around the borehole instead of
spinning about its own axis. *Forward* whirl: center orbits in the direction of rotation
(mass-imbalance-driven, synchronous-ish). *Backward* whirl: friction at the wall causes
the assembly to roll around the borehole opposite to rotation — the gearing effect
produces high-frequency, high-g lateral vibration; the most destructive lateral mode.

**Spectral signature:**
- Strong lateral-acceleration energy; hashing/display bands per the normative table in
  §5 (hashing: orders 2–14 in the order domain, ≈ 2–33 Hz over 60–140 RPM; display:
  5–50 Hz plus the 100–160 Hz impact rings).
- **Backward whirl kinematics (deterministic!) — rolling without slip yields TWO
  rates in two reference frames; never conflate them:**

  | Frame | Rate | What it is | Used for |
  |---|---|---|---|
  | Inertial (borehole) | Ω_orbit = −ω·d_b/(d_h − d_b) = **−N_b·ω** | the BHA/bit center's orbit around the borehole | twin orbit animation (§24, §27) |
  | Pipe-mounted sensor | Ω_sensor = −ω·d_h/(d_h − d_b) = **−(N_b+1)·ω** | the rate at which the contact/bending line sweeps past a sensor on the pipe | the spectral line the fingerprint hashes (order N_b+1) |

  Borehole diameter d_h, BHA/bit diameter d_b; small clearance ⇒ very high whirl rate.
  For cutter-induced bit whirl on a PDC bit with N_b blades, the sensor-frame line is
  **Ω = −ω(N_b + 1)** (validated in field/test data — worked example with **N_b = 5**,
  i.e. 5 blades → 6-lobe pattern: 2.5 Hz bit rotation → 15 Hz backward whirl line,
  observed at 17.5 Hz absolute including the 2.5 Hz rotation). Multi-lobe
  generalization M = j·N_b + 1 contacts per revolution (**j is reserved for the lobe
  integer, document-wide**).
- Because Ω is a *fixed multiple of instantaneous rotary speed*, whirl lines in the
  spectrogram are **RPM-proportional** — they migrate when RPM changes. This is the
  single strongest argument for order-domain resampling (§9): in the angle domain,
  whirl energy sits at a *constant order* (e.g., order N_b+1), turning a smeared,
  drifting ridge back into a sharp, hashable peak.
- Accompanied by broadband impact noise (wall contacts) and, for forward whirl,
  a 1×-rotary line from imbalance.

**Synthetic model (§12):** Jeffcott-style rotor on nonlinear wall contact — or, for the
fingerprint library, direct signal synthesis: sum of (a) 1× rotary line, (b) whirl line at
order −(N_b+1) with amplitude modulation, (c) impact train (per wall contact, M impacts/rev,
each a decaying **100–160 Hz** ring — ≤ 0.8 × Nyquist at f_s = 400; no synthesized
component may exceed 0.45 × f_s, §12), (d) broadband noise. Signal-level synthesis is
defensible because the *fingerprint* only encodes spectral peak geometry.

## 4. Bit bounce (axial)

**Mechanism.** Axial resonance of the string interacting with a patterned (cammed)
hole bottom — classically tri-lobed for roller-cone bits — causes the bit to
periodically lift off and impact bottom.

**Spectral signature:**
- Strong axial acceleration / WOB / hookload energy; bands per the normative table in
  §5 (hashing: orders 2–10 on ACC_AX, covering lines 3, 6, 9; display: 1–20 Hz).
- For tricone bits: dominant line at **3× rotary speed** (three cones → three-lobed
  bottom pattern). 120 RPM = 2 Hz rotary → 6 Hz axial line, plus harmonics.
- Again RPM-proportional ⇒ constant *order 3* in the angle domain.

**Synthetic model:** axial spring-mass with bottomhole contact: m·z̈ + c·ż + k_a·z =
F_WOB − F_contact(z, φ), F_contact active only when z touches the lobed surface profile
s(φ) = s₀·cos(3φ). Or direct synthesis: 3×-order line + impact train + harmonics.

## 5. Dysfunction taxonomy → fingerprint classes

The engine's fingerprint library is organized by **class → episode → channel**. The
table below is the **single normative band table** — §2/§3/§4 and the References (§23)
cite it; no other band figure in this document is normative.

| Class | domain / profile | hashing band | display band² | hashed channels | display-only channels |
|---|---|---|---|---|---|
| STICK_SLIP | time / LOW (or LOW-DEEP if pred. f₀ < 0.12 Hz) | 0.1–4 Hz (LOW-DEEP: 0.04–2 Hz) | same | TORQUE_SURF (primary), RPM_DH | — |
| WHIRL_BACKWARD | order / ORDER | orders 2–14 (≈ 2–33 Hz over 60–140 RPM) | 5–50 Hz + 100–160 Hz rings | ACC_LAT_X, ACC_LAT_Y | — |
| WHIRL_FORWARD | order / ORDER | orders 0.5–1.5 (1× ± sidebands) | — | ACC_LAT_X, ACC_LAT_Y | — |
| BIT_BOUNCE | order / ORDER | **orders 2–10** (covers lines 3, 6, 9) | 1–20 Hz | ACC_AX (primary) | **WOB** (twin/HUD; badged "partial band — not matchable") |
| NORMAL_DRILLING | all | per bound class band | — | all hashed channels above | — |

² *Display band* = the Hz range rendered on the time-domain spectrogram. It is never
hashed and never enters the build rule or badge logic; only hashing bands do.

Rules:
1. **Build rule (hashed bindings only):** band_top ≤ 0.45 × f_s for every
   (class, **hashed** channel) pair. Enumerated: STICK_SLIP/TORQUE_SURF 4 ≤ 4.5 ✓,
   /RPM_DH 4 ≤ 4.5 ✓; WHIRL/ACC_LAT_* 33 ≤ 180 ✓; BOUNCE/ACC_AX 21 Hz-equiv ≤ 45 ✓
   and orders 2–10 ≤ effective order bandwidth 21.4 at 140 RPM ✓. WOB
   (0.45 × 10 = 4.5 Hz) is *display-only* precisely because it fails this rule — the
   same honest-badging treatment as 1 Hz torque.
2. **Badge logic is band-aware:** a channel "sees" a class only if the class's full
   *hashing* band fits under 0.45 × f_s (and, in ORDER, inside the effective order
   bandwidth of §6). 1 Hz torque and 10 Hz WOB badge as "fundamental/partial band —
   insufficient for matching."
3. Full-gauge rolling whirl (order d_h/(d_h−d_b) ≈ 15–35 at realistic clearances) is
   **out of scope for v1** — stated so nobody sizes filters expecting it.

Class bindings use the exact channel names of the §16 registry (bare "TORQUE" /
"ACC_LAT" spellings are retired); the ACC_LAT binding means each of X/Y is
fingerprinted independently — either fires the class.

NORMAL_DRILLING episodes matter: matching *against* healthy baselines both suppresses
false positives and enables the "drift from healthy" story (predictive-maintenance
framing) without any extra machinery.

---
# PART II — THE MATHEMATICS

## 6. From signal to spectrogram

**Sampling.** Rig channels arrive at wildly different rates: standard surface WITSML
channels ~1 Hz; high-frequency surface torque/RPM 50–200 Hz; downhole memory-mode
accelerometers 400–1,600 Hz. The engine treats sample rate f_s as per-channel metadata.
Nyquist: content above f_s/2 is invisible — so channel choice bounds detectable classes
(at 1 Hz, torque sees only the stick-slip *fundamental* — insufficient for matching,
per §5's band-aware badge logic; whirl needs ≥100 Hz lateral acceleration). The UI must
show, per channel, which dysfunction classes are *observable* given f_s — an
honest-engineering touch reviewers notice.

**DFT.** For a frame x[n], n = 0..N−1:

X[k] = Σ_{n=0}^{N−1} x[n]·e^{−j2πkn/N},  frequency resolution Δf = f_s/N.

FFT computes this in O(N log N). Use `scipy.fft.rfft` (real input → N/2+1 bins).

**STFT.** Slide a window w[n] of length N with hop H:

S[m, k] = Σ_n x[n + mH]·w[n]·e^{−j2πkn/N}

Spectrogram = |S[m,k]|² (use log-magnitude, dB, for peak picking).

**Windowing.** Rectangular windows leak (−13 dB sidelobes) and would bury the harmonic
combs we need. Use **Hann**: w[n] = 0.5(1 − cos(2πn/N)), −31.5 dB sidelobes, and
50–75% overlap (H = N/4 or N/2) so amplitude tracking is smooth (COLA-compliant).

**Parameter sets (defaults — expose all in config):**

| Profile | domain | rate | N | hop | Δf / Δorder | frame span | query window W | eval cadence | T_max | hashed? |
|---|---|---|---|---|---|---|---|---|---|---|
| LOW | time | 10 Hz | 256 | 64 | 0.039 Hz | 25.6 s | **120 s** | 6.4 s | **12** | yes |
| **LOW-DEEP** | time | 10 Hz | 512 | 128 | 0.0195 Hz | 51.2 s | **240 s** | 12.8 s | **12** | yes (deep wells) |
| MID | time | 100 Hz | 512 | 128 | 0.195 Hz | 5.12 s | **30 s** | 1.28 s | **16** | display only |
| HIGH | time | 400 Hz | 1024 | 256 | 0.39 Hz | 2.56 s | 10 s | 1.0 s | **8** | display only¹ |
| **ORDER** | order | 64 samples/rev | 256 | 64 | 0.25 order | 4 rev | **16 rev** | 1 rev | **10** | yes |
| **LOW-DECIM** | time | 1 Hz | 256 | 64 | 0.0039 Hz | 256 s | — | 64 s | — | **never** (display/badges only) |

¹ HIGH additionally hosts a *test-only* time-domain whirl fingerprint set in M2 —
see §12.2 and §21.

- Eval cadences are defined in **data-time seconds** (or revolutions for ORDER);
  HIGH's 1.0 s deliberately spans 1.56 hops — the K=2 rule (§18) requires ≥ 1 hop of
  fresh data between counted evaluations, which every cadence satisfies.
- **LOW-DEEP** is selected automatically when the predicted f₀ (§2) is below
  **0.12 Hz** — deep/slow corners (long L, heavy BHA) have comb spacing of 1.3–2.4
  LOW bins, inside the Hann mainlobe; halving Δf restores resolvability. Its hashing
  band is 0.04–2 Hz (§5).
- **LOW-DECIM** exists so ~1 Hz channels (Volve, decimated variants) can stream
  spectrograms and drive observability badges. It never produces hashes: at 1 Hz the
  harmonic comb is invisible (§8's own "a lone peak is not discriminative"), so
  matching is structurally impossible there and the profile is honest about it.

New invariant, asserted by a unit test at import time: **frames_per_window(W, profile)
≥ T_max + 3** for every hashed profile. (Verified: LOW 15 ≥ 15, LOW-DEEP 15 ≥ 15,
ORDER 13 ≥ 13; display-only MID 20, HIGH 12 also pass their scheduling math.)

T_max is **per-profile** and applies identically to library and query hashing (a
library hash whose Δt exceeds the profile's T_max is never emitted, so library and
query hash populations match by construction). The 6-bit Δt field covers all values.
K_max = 63 and fan-out F = 8 are unchanged from the Shazam defaults (§8).

The ORDER profile's rfft yields 129 order bins (Nyquist = 32 orders), inside the
10-bit f₁ field. **Effective order bandwidth of a channel is
min(32, 0.5 × f_s / f_rot) — every class's hashing band must sit inside it for the
bound channel** (bounce orders 2–10 on ACC_AX at 100 Hz: limit is 21.4 orders at
140 RPM — passes at all spec RPMs).

Rationale: stick-slip needs fine Δf near 0.1–0.5 Hz (long frames are fine — the
phenomenon evolves over tens of seconds); whirl needs time resolution (impacts) with
adequate Δf. Shrinking the LOW frame (N=128) for faster response is rejected: Δf would
coarsen to 0.078 Hz and a 0.1 Hz comb lands 1.28 bins apart — inside the Hann
mainlobe, unresolvable. Deep-string stick-slip genuinely needs long frames; the honest
fix is longer windows (trivial memory at 10 Hz) plus honest latency targets (§18).
W_ORDER is stated in **revolutions** because that is the domain's native clock —
16 rev = 8 s at 120 RPM. Running 2–3 parallel STFT profiles per channel group is the
correct architecture (cheap: these are tiny FFTs).

## 7. Peak picking → constellation map

Convert the dense spectrogram to a sparse set of (t, f) landmark points:

1. Log-magnitude: L[m,k] = 20·log10(|S[m,k]| + ε), with **ε = 1e-12 applied after
   per-channel normalization**.
2. **Local maximum test:** candidate iff L[m,k] ≥ all neighbors in a
   (2Δm+1)×(2Δk+1) neighborhood (default Δm=3, Δk=3). Implement with
   `scipy.ndimage.maximum_filter` — one vectorized pass; boundary handling pinned to
   `mode='constant', cval=-inf` (provably equivalent to reflect for a max filter,
   pinned anyway so two implementations can't differ).
3. **Adaptive threshold:** keep iff L[m,k] ≥ median(L[m, :]) + β dB (β default **8**).
   Median-per-frame makes it robust to overall level shifts (mud weight changes,
   sensor gain) — same reason Shazam survives volume differences.
4. **Density cap:** at most P peaks per frame (default 5), strongest first —
   uniform constellation density is what keeps hash counts predictable.
5. **Determinism pins:** tie-break for equal-magnitude peaks = **(lower k, then
   lower m)** — dropout interpolation (§16) creates exact-tie plateaus and §33 demands
   byte-identical reruns. The Hann window is the periodic form (`sym=False`; the §6
   formula already is periodic Hann).

Output: constellation C = {(m_i, k_i)} — the sparse skeleton robust to noise, exactly
Wang's insight: peaks survive noise and distortion because they are *locally* the
strongest energy; everything else can be discarded.

## 8. Combinatorial hashing (the Shazam core)

Single peaks are not discriminative (a 0.3 Hz peak is just "a 0.3 Hz peak").
**Pairs** of peaks with their time relationship are.

For each **anchor** peak (t₁, f₁), pair it with each **target** peak (t₂, f₂) inside a
target zone: 1 ≤ (t₂ − t₁) ≤ T_max frames, |k₂ − k₁| ≤ K_max bins, up to F targets
per anchor (fan-out, default F = 8, K_max = 63 bins; **T_max is per-profile — §6 —
and applies identically to library and query hashing**).

Hash = pack(f₁_quantized : 10 bits | Δf_signed : 8 bits | Δt : 6 bits) → 24-bit packed
int (fits any KV store; SQLite INTEGER). Stored value = (episode_id, t₁).

Properties (all inherited from Wang's analysis):
- **Specificity multiplies:** two frequencies + a time delta carry **~16–17 effective
  bits of entropy** under the §6 target zones (LOW: ~100 in-band f₁ bins × 127 Δk ×
  12 Δt ≈ 17.2 bits; ORDER: 49 × 127 × 10 ≈ 15.9 bits) vs ~10 for a lone peak → far
  fewer spurious collisions → smaller candidate sets → speed.
- **Combinatorial redundancy compensates:** F pairings per anchor means losing any
  single peak to noise destroys only a fraction of hashes; matching needs only a
  *subset* to survive.
- **Locality:** each hash is computed from a ≤ few-second neighborhood, so a match
  can begin anywhere inside a dysfunction episode — crucial for streaming detection.
- Cost: F× storage, F× probe rate — the classic Shazam 10× trade for ~10,000× search
  speedup. At our scale (hundreds of episodes, not 40M songs) this is trivially cheap,
  which is worth *saying* in the demo: the algorithm is engineered for a scale far
  beyond what drilling needs — headroom is the point.

## 9. RPM-invariance: order-domain (angular) resampling — the key adaptation

Shazam assumes the recording and the reference play at the same speed. Drilling
violates this: whirl and bounce lines live at *fixed multiples of rotary speed*
(orders), so a 100→130 RPM change moves every peak by 30% and breaks time-domain
hashes.

**Solution — order tracking, standard in rotating-machinery diagnostics, novel in
this fingerprinting context:** use the rotary speed channel Ω(t) (always available at
surface) to compute cumulative shaft angle φ(t) = ∫Ω dt, then resample the vibration
signal at **uniform Δφ** (64 samples/rev) via interpolation. The STFT of the
angle-domain signal has axes (revolutions, **order**) instead of (seconds, Hz):

- whirl at Ω = −ω(N_b+1) (the sensor-frame line, §3) → constant **order N_b+1** line
- tricone bounce at 3× → constant **order 3** line
- 1× imbalance → order 1

Fingerprints hashed in the order domain are **invariant to RPM and to RPM drift**
within an episode. Run stick-slip fingerprinting in the *time* domain (its physics is
clocked by string length, not RPM) and whirl/bounce in the *order* domain. This dual-
domain design is the paper-worthy methodological contribution — name it explicitly in
the demo ("time-domain fingerprints for string-clocked modes, order-domain for
rotation-clocked modes").

Implementation (normative):
- Angular resampling operates on **aligned channel pairs only**:
  `sessions.get_window` (§16) interpolates RPM_SURF onto the vibration grid;
  `order_domain.py` consumes only aligned pairs, computes φ(t) = ∫Ω dt, and resamples
  to the φ-grid with `numpy.interp`. The ORDER STFT parameters are the §6 profile row.
- **Anti-alias low-pass before angular interpolation** (owned by `order_domain.py`),
  zero-phase, cutoff
  **f_c = min( 0.8 × 32 × min(f_rot in window), 0.45 × f_s_channel )**, and **skip
  the filter entirely when 64 × f_rot ≥ f_s_channel** (angular resampling is then pure
  upsampling — nothing to anti-alias). Verified: on ACC_LAT (400 Hz) the first term
  governs at all spec RPMs (25.6 Hz at 60 RPM … 59.7 Hz at 140 — always above the
  order-2–14 band top of 14–32.7 Hz, always below the 100–160 Hz rings, constant
  ratio 1.83×); on ACC_AX (100 Hz) the clamp takes over above ~117 RPM.
- Windows whose minimum RPM falls below the Ω_min guard (10 RPM, §16) are
  **order-invalid** — badged, never order-evaluated, never divided through.
- Store the domain tag in every fingerprint record.
- The per-channel **effective order bandwidth min(32, 0.5·f_s/f_rot)** rule (§6) is
  enforced at library build for every hashed (class, channel) pair.

## 10. Matching: offset-histogram / diagonal alignment

Query = the last W of a live channel — a rolling window sized per profile (§6: 120 s
LOW, 240 s LOW-DEEP, 16 rev ORDER; MID and HIGH are display-only), evaluated at the
profile's cadence in data-time. Fingerprint it identically → query hashes {(h, t_q)}.

For each hash, look up all library postings (episode_id, t_lib). For every match
compute the candidate offset δ = t_lib − t_q and accumulate a per-episode histogram
over δ (bin width = 3 frames).

**Decision logic:** random collisions scatter δ uniformly; a true match — the query
genuinely containing the episode's pattern — piles matches into ONE δ bin (the
scatterplot of (t_q, t_lib) forms a diagonal line, hence "diagonal alignment").
Score(episode) = max_δ histogram(δ).

**Significance, corrected for multiplicity (not just score):**

1. **λ excluding the max bin:** λ = max( (matched_pairs − max_bin) / (n_bins − 1), 0.05 ).
2. **Corrected significance:** p_corr = n_episodes × n_δbins × P(Poisson(λ) ≥ score).
3. **Alert condition (Tier 2, §18):** p_corr < **1e-4** AND score ≥ **s_min = 8**,
   sustained over K = 2 consecutive evaluations, the second containing ≥ 1 hop of
   data absent from the first.
4. **Display statistic (normative):** `confidence := 1 − p_corr`, clamped to [0, 1].
   This is the *only* confidence shown anywhere. `active_detections` entries carry
   `{class, tier, confidence, p_corr, score, sssi}` (§24); §19's example copy is
   "Stick-slip confirmed — SS-014 · score 34 · p < 1e-9 · period 4.6 s".
5. The Detection payload reports score, λ, p_corr, and the full histogram — and the
   UI can *show* the histogram spike, which is the single most convincing visual in
   the product: proof, not vibes.

Verified margins: random background at λ = 0.063 reaching score 8: p_corr ≈ 5e-11.
Per-profile T_max shrinkage can inflate λ toward ~0.3; even there p_corr ≈ 1e-5 —
still under threshold, so **s_min = 8 holds for λ up to ~0.3** (assert this bound in a
unit test against the built library's measured λ). A genuine match at score 25 vs
λ = 2: p_corr ≈ 3e-15 — eleven orders of magnitude inside the threshold. Correcting
for the number of tests (n_episodes × n_δbins) keeps the threshold's meaning stable as
the library grows across versions — which §31's versioning story requires.

**Class decision:** best episode per class → class score; a Tier-2 (confirmed) alert
fires on the condition above. (Tier-1 advisories come from the SSSI / band-energy
watchers of §18 — never from the matcher.) Emit: class, tier, matched episode,
confidence, score, λ, p_corr, δ*, matched hash list (for the explainability
drill-down), SSSI (if torsional), dominant orders (if order-domain).

**Complexity:** per evaluation, hashing is O(N log N) on tiny N; lookup is O(matches)
via hash index. Sub-millisecond per query window on any laptop — quote real measured
numbers in the benchmark tab.

## 11. Failure modes & mitigations (design honestly around these)

- **Frame-quantization jitter:** peak lands on adjacent STFT frame/bin between library
  and query → mitigate with δ bin width ≥ 3 frames and target-zone tolerance already
  built into fan-out.
- **Episode self-similarity:** stick-slip is quasi-periodic → multiple δ bins light up
  at multiples of the limit-cycle period. Expected and *informative*: report the comb
  spacing as the measured stick-slip period. Handle by taking max bin but displaying
  the full histogram.
- **Cross-class leakage:** severe stick-slip's slip phase briefly excites lateral
  energy → possible weak WHIRL score. Mitigate with per-class channel binding (a class
  only matches on its designated `hashed*` channels — the §16 registry names, enforced
  in the store, §15) and report co-detections honestly.
- **Non-stationarity within window:** RPM ramp mid-window smears time-domain
  fingerprints → order domain fixes rotation-clocked classes; for stick-slip, W is
  short relative to depth-driven f₀ drift, so negligible.
- **Library bias:** synthetic episodes must sweep parameters (depth/L, RPM, WOB,
  friction levels) so the library covers the operating envelope; augment with any
  real labeled data (Volve) available.

---
# PART III — DATA: SYNTHESIS, REPLAY, VALIDATION

## 12. Synthetic episode generation (`synth/`)

Every dysfunction class gets a physics-driven generator with a parameter sweep, so the
library is *derived*, not hand-drawn. Generators return (signal dict per channel,
metadata dict) at a declared f_s.

**Normative generator parameter table:**

- **Durations:** stick-slip **180 s**; whirl **60 s**; bounce **60 s**; normal
  **120 s**. (Benchmark/scenario *runs* are generated to any needed length with
  query-side seeds and are distinct from library episodes — §14, §32.)
- **Pinned constants:** T_c = 6 kN·m; T_s = ratio × T_c; J_t = 1000 kg·m²;
  ω_s = 1 rad/s; ζ = 0.05 → c = 2ζ√(k·J_b); PI top drive K_p = 500 N·m·s/rad,
  K_i = 50 N·m/rad; lobe integer **j = 1** (M = N_b + 1).
- **RPM profiles (pinned):** const = **120 RPM**; ramp = **80→140 RPM** linearly over
  the episode (whirl — matches gate 3 and §34) and **80→130 RPM** for bounce (keeps
  order 9 ≤ 19.5 Hz inside the display band); dither = **120 ± 10 RPM at 0.1 Hz**.
- **Sweeps:** stick-slip L{1500, 2250, 3000, 4000, 5000} × Ω{60, 90, 120} ×
  ratio{1.3, 1.6, 2.0} × J_b{100, 200, 400} = **135** corners (non-cycling corners →
  NORMAL_DRILLING per §12.1; deep corners auto-select LOW-DEEP per §6); whirl
  N_b{4, 5, 6} × severity{1–3} × RPM-profile{const, ramp, dither} = **27**; bounce
  severity{1–3} × RPM-profile = **9**; normal **5** variants (2 with pump combs at
  SPM {60, 110} → triplex comb fundamentals 3.0 / 5.5 Hz, injected on TORQUE_SURF +
  WOB per §16).
- **Noise policy:** the library is **clean**; SNR {20, 10, 3, 0} dB, gain ±20 %,
  dropouts 100–500 ms, and 1 Hz decimation apply **query-side only** (benchmark runs
  and scenario data). Wang's convention; the only reading under which "benchmark at
  each SNR" means anything.
- **Generator gate (all synth modules):** no synthesized component above
  **0.45 × f_s**.
- **Size/build estimates (with assumptions stated):** ≈ 270k stick-slip + 210k whirl
  + ~40k bounce (ACC_AX only, per §5) + normal at ~10–20 % of its peak-cap budget
  (noise rarely survives the median+8 dB gate; the build report records actuals) ≈
  **0.5–0.6 M hashes, ~20 MB** — consistent with §18's 10⁶ scale. Build budget: 1–2 s
  per stiff ODE run × 135 + synthesis + hashing + insert — **≤ 5 min holds without
  heroics**; CI measures and records it.

**12.1 `synth/stick_slip.py`** — integrate the 2-DOF model of §2 with
`scipy.integrate.solve_ivp(method="LSODA")`, PI-controlled top drive, Stribeck bit
friction (tanh-regularized). Output channels: TORQUE_SURF (= PI controller output),
RPM_SURF, RPM_DH (= θ̇_b), all at 10 Hz. Sweep per the table above (135 corners).
Sanity gates (unit-tested):

1. **Stability screen (before gating):** corners with torque swing < 5 % after the
   startup transient did not develop a limit cycle — **expected physics**, not
   failure. Relabel them NORMAL_DRILLING (honest negatives — they grow the negative
   class with realistic near-threshold operation, exactly where false-positive
   immunity matters) and log them in the build report. The remaining gates apply only
   to corners that limit-cycle.
2. **Period gate:** measured limit-cycle period ∈ **[1.0, 2.0] × T_model** (§2 — the
   gate tests the model the code actually integrates). Reference behaviour: measured
   periods land at 1.01–1.24 × T_model at 120 RPM and up to ~1.78 at 60 RPM — the
   stick dwell grows as commanded RPM falls; 2.0 gives margin without admitting
   nonsense.
3. **Stick gate:** min downhole RPM during the cycle < 5 % of commanded surface RPM.
4. **Swing gate:** torque swing ≥ 15 % of mean.
5. **Comb gate:** spectral comb *spacing* = 1/T_measured — never an odd/even amplitude
   pattern (§2).

**12.2 `synth/whirl.py`** — signal-level synthesis at 400 Hz on ACC_LAT_X/Y:
order-1 imbalance line + backward-whirl line at order (N_b+1) with slow AM +
impact train of M = j·N_b+1 decaying **100–160 Hz** rings per revolution + pink noise.
Drive with a *time-varying RPM profile* (pinned above) — the generator must prove
order-domain invariance by construction. Sweep N_b ∈ {4, 5, 6}, severity ∈ 3 levels,
RPM profiles ∈ {const, ramp, dither}. **The generator emits RPM_SURF at 10 Hz as a
measured channel** (±1 RPM Gaussian noise, optional 100 ms latency corner); the
generator's internal RPM profile is never exported — resampler and matcher consume
only the measured channel, which de-circularizes the §9 invariance proof (§21, M2).
One **Jeffcott-integrated episode** is added as a physics cross-check: it must match
the signal-synthesized ORDER library, defending against "you synthesized the answer
in."

**12.3 `synth/bit_bounce.py`** — axial contact model or direct synthesis at 100 Hz on
ACC_AX + WOB: order-3 fundamental + harmonics (orders 6, 9) + lift-off impact train +
noise; same RPM-profile treatment (bounce ramp = 80→130 RPM). Also emits
**HOOKLOAD = buoyed string weight − WOB + axial oscillation** at 10 Hz.

**12.4 `synth/normal.py`** — colored noise shaped to typical drilling PSDs + weak
order-1 line + slow trends; **emits the full surface set — TORQUE_SURF, RPM_SURF,
WOB, ACC_AX, ACC_LAT_X/Y — with the pump comb injected on TORQUE_SURF and WOB** (SPP
is out of scope in v1; pump pressure pulsation couples into both mechanically, and
the false-alert gate needs the comb on a stick-slip-bound channel to be a real
false-positive test). Two of the five variants carry pump combs (SPM 60 / 110) —
pump strokes create their own comb; include it so the matcher demonstrably does NOT
confuse pump noise with dysfunction; this is a benchmark scenario.

**12.5 Noise & channel realism:** per the noise policy above, all realism
corruptions — additive Gaussian + pink noise at SNR ∈ {20, 10, 3, 0} dB, random gain
(±20%), random dropouts (100–500 ms), 1 Hz decimated variants of every channel (to
demo the observability logic of §6) — are applied **query-side only**; library
episodes stay clean.

## 13. Field data replay (Volve)

The Equinor Volve open dataset includes real-time drilling logs (WITSML) with surface
channels (torque, RPM, SPP, hookload, WOB) at ~1–10 s cadence for multiple wells.
Build `replay/volve_loader.py` that reads exported CSV/LAS
extracts, maps mnemonics to DrillPrint channel names, and replays at true or
accelerated wall-clock speed through the same ingestion path as live data.

**Licensing posture (normative):** no Volve data ships in the repo until the current
Equinor license text is verified to permit redistribution of extracts with
attribution. If permitted: a `LICENSE-data` file + provenance metadata accompany the
cache. If not: user-placed only — the user places files under `data/volve/` (do NOT
attempt to script downloads; access requires accepting Equinor's license). The
**segment registry** `data/volve/segments.yaml` maps segment id → file, t-span,
provenance — the resolver for `volve:` scenario sources (§32).

**Mnemonic → channel map (extend as extracts require):**

| WITSML mnemonic | DrillPrint channel |
|---|---|
| TQA | TORQUE_SURF |
| RPMA | RPM_SURF |
| WOBA / SWOB | WOB |
| HKLD | HOOKLOAD |
| DBTM | BIT_DEPTH |
| DMEA | HOLE_DEPTH |
| BPOS | BLOCK_POS |

Volve's ~1 Hz surface cadence streams on the LOW-DECIM profile (§6): spectrograms and
observability badges, never hashes. That cadence limits Volve to stick-slip-band
content — and at ~1 Hz only the fundamental is visible, insufficient for matching
(§5 badge logic); say so in the UI rather than overclaiming. Synthetic HIGH-rate
channels carry the whirl demo.

## 14. Benchmark protocol (`bench/`)

- **Split:** library episodes vs held-out query episodes generated with *different
  random seeds and parameter draws* (no query episode in the library). The library is
  clean; all §12.5 corruptions are query-side.
- **Runs:** windowed classification over long composite runs (normal → dysfunction →
  normal, randomized order/durations): **≥ 10 composite runs × ≥ 30 min data-time per
  SNR level**; seeds = base + run_index, recorded; all rates reported per
  **data-hour**.
- **Event scoring:** an event = [onset, offset] from generator metadata. TP = first
  correct-class Tier-2 alert within [onset, onset + T_tol], inclusive. **T_tol per
  class = 1.3 × the applicable §18 Tier-2 target at the run's RPM and SNR, rounded
  up** — concretely: stick-slip 120 s; whirl 20 s (≥ 120 RPM) / 40 s (60 RPM); bounce
  26 s / 40 s. Invariant, asserted in the bench code: **T_tol ≥ the §18 target for
  the same conditions.** Wrong-class or on-normal alerts = FP. **Late correct-class
  alerts = FN plus a separately-reported late count — never FP.** One detection
  credited per event. Latency = alert − onset, in data-time.
- **Metrics:** precision, recall, F1 per class; detection latency (data-time from
  onset to first Tier-2 alert); false alerts per data-hour on pure-normal runs; late
  counts.
- **Baseline:** naïve band-energy threshold detector (band-pass RMS + threshold per
  class) — the honest incumbent. **Calibration:** baseline thresholds are fit on a
  normal-only validation run to **1 FA/data-hour**, then frozen. Tier-1 advisories
  are calibrated the same way to their ≤ 2/data-hour budget (§18). DrillPrint Tier-2
  thresholds are fixed by §10. Then everything is scored and reported as-is.
- **Output:** `bench/report.json` consumed by the dashboard's Benchmark tab
  (confusion matrix, PR curves, latency histogram, calibration records) —
  recomputable with one command: `python -m bench.run --full`.

---

# PART IV — SYSTEM ARCHITECTURE

## 15. Stack & repo layout

Backend: **Python 3.11+, FastAPI, NumPy/SciPy, SQLite (upgradeable to Postgres),
uvicorn, WebSockets, typer**. No ML deps. Frontend (built separately by the user):
**React + Vite**, canvas/WebGL spectrogram. Deploy: API on Render/Railway, UI on
Vercel — or fully local via `drillprint demo` (dual-serve mode, below).

```
drillprint/
├── cli.py                   # typer: drillprint {library,bench,demo} — [project.scripts] entry
├── engine/                  # pure DSP core — ZERO web/framework imports
│   ├── stft.py              # windowing, STFT profiles, log-magnitude
│   ├── order_domain.py      # angular resampling + anti-alias filter (§9)
│   ├── peaks.py             # constellation extraction (§7)
│   ├── hashing.py           # combinatorial hashing, pack/unpack (§8)
│   ├── matcher.py           # offset histogram, corrected significance (§10)
│   ├── sssi.py              # surface stick-slip severity index (§2)
│   ├── twin_kinematics.py   # pure: twist, whirl/bounce phase integration (§24)
│   └── types.py             # Frame, Peak, Hash, Detection dataclasses
├── store/
│   ├── schema.sql           # schema v2 (below)
│   └── fingerprint_db.py    # bulk insert, hash→postings lookup, versioning, approval
├── synth/                   # §12 generators + cli: python -m synth.build_library
├── replay/                  # volve_loader.py, stream_player.py, scenario_player.py
├── ingest/
│   ├── channels.py          # WITSML-shaped channel registry (§16)
│   └── sessions.py          # per-connection ring buffers, alignment, window scheduler
├── api/
│   ├── main.py              # FastAPI app, OpenAPI metadata
│   ├── routes_library.py    # CRUD: libraries, episodes, fingerprint stats
│   ├── routes_stream.py     # WS: /ws/ingest (data in), /ws/monitor (frames+detections out)
│   └── routes_bench.py      # GET /bench/report
├── config/                  # well-context schema + loader (well01.yaml: L, N_b, d_h, d_b, channels)
├── scenarios/               # *.json manifests (§32)
├── frontend_dist/           # committed UI build — serves the §33 zero-network demo
├── data/
│   ├── volve/               # user-placed (§13) — never committed; segments.yaml registry
│   └── demo_cache/          # prebuilt flagship fingerprint DB + pre-generated run data
├── bench/                   # §14
├── tests/                   # pytest — see §22 acceptance gates
└── pyproject.toml
```

**Hard rule:** `engine/` is importable and testable with no server
running; every module has doctest-style examples; every public function type-hinted.
`engine/twin_kinematics.py` keeps the twin-state derivation pure and testable; the
api layer owns message assembly and cadence.

**Store schema v2 (`store/schema.sql`):**

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
CREATE TABLE profiles (          -- the §6 table, as data
  name TEXT PRIMARY KEY, domain TEXT, fs REAL, n INTEGER, hop INTEGER,
  samples_per_rev INTEGER, t_max INTEGER, window_w TEXT, hashed INTEGER
);
CREATE TABLE class_bindings (    -- the §5/§16 tables, as data
  class TEXT, channel TEXT,
  role TEXT CHECK (role IN ('hashed_primary','hashed','display')),
  min_fs REAL
);
```

The matcher filters postings on (hash, profile, domain) **and** the active library
version **and** the class's `hashed*` channels — §11's per-class binding lives here.
`t_anchor` = hop-frame index within the episode; δ is computed in frames, δ-bin width
3 frames. `POST /libraries/{v}/activate` rejects status ≠ 'approved' (§31's gate,
enforced). The episode **slug** is the canonical address for UI copy and synthetic
scenario sources.

**CLI & config:** `config/` is the single source for L (→ k), N_b (→ orders, bit
geometry), hole/bit diameters, and the channel set. The `drillprint` CLI is the
canonical user surface (`library build --config`, `library import`, `bench run
--library`, `demo`); module entry points remain for CI; docs and UI empty-states
reference the CLI only. **`library import` format:** CSV or parquet with columns
`t0, t1, class, channels...` per labeled interval. **Dual-serve mode:** the frontend
reads its API base from env-injected config — same-origin default for
`drillprint demo`; explicit base + CORS allowlist for the Render/Vercel hosted split.

## 16. Ingestion contract (WITSML-shaped)

DrillPrint does not implement full WITSML — it adopts its *shape* so the integration
story to real rig infrastructure (WITSML stores, SLB Agora-class edge platforms) is
one adapter away:

```json
{ "channelSet": "rig01.surface",
  "channels": [
    {"mnemonic": "TQA",  "name": "TORQUE_SURF", "uom": "kN.m", "fs": 10.0},
    {"mnemonic": "RPMA", "name": "RPM_SURF",    "uom": "rpm",  "fs": 10.0},
    {"mnemonic": "ALX",  "name": "ACC_LAT_X",   "uom": "g",    "fs": 400.0}
  ]}
```

**Canonical channel registry (one naming scheme, mirrored as store data — §15):**

| Channel | uom | f_s | produced by | consumed by |
|---|---|---|---|---|
| TORQUE_SURF | kN·m | 10 | synth §12.1, **§12.4**, Volve, live | STICK_SLIP (hashed), SSSI, twin |
| RPM_SURF | rpm | 10 | all synth, Volve, live | order resampler, twin |
| RPM_DH | rpm | 10 | synth §12.1 | STICK_SLIP (hashed), twin |
| ACC_LAT_X / _Y | g | 400 | synth §12.2, **§12.4** | WHIRL_* (hashed) |
| ACC_AX | g | 100 | synth §12.3, **§12.4** | BIT_BOUNCE (hashed) |
| WOB | kN | 10 | synth §12.3, **§12.4**, Volve, live | BIT_BOUNCE (display), twin |
| HOOKLOAD | kN | 10 | **synth §12.3**, Volve | twin |
| BIT_DEPTH, HOLE_DEPTH, BLOCK_POS | m | 1 | **scenario player**, from well config | twin, rig strip |

Rules: §5/§11 class bindings use these exact names. **BENDING is dropped from v1.**
The scenario player emits the three rig-context channels at 1 Hz from well config,
making §29's "every animated quantity traceable to a stream field" literally true.

Data frames over `/ws/ingest`:
`{"t0": 1786320000.000, "name": "TORQUE_SURF", "values": [...], "fs": 10.0}` —
batched arrays, not per-sample JSON. Server maintains per-channel ring buffers
(deque of numpy blocks) and schedules matcher evaluations per §10.

**`ingest/sessions.py` contracts:**
1. **Monotonic t0 per channel**; violations dropped and counted (surfaced in
   `/health`).
2. **Gap policy, complete:** gaps **≤ 1 hop** (in the profile's own hop unit) are
   linearly interpolated, counted, and flagged in the frame's `diag`; gaps **> 1
   hop** skip every matcher window they overlap, flagged in the monitor stream. The
   inequality is deliberately non-strict on the interpolate side: a 500 ms dropout =
   exactly 1.0 ORDER hop at 120 RPM → interpolated. No zero-filling anywhere.
   Benchmark runs inherit this policy, so dropout robustness is measured as "how
   quickly matching resumes" — the honest metric.
3. **Aligned-view API:** `sessions.get_window(channels, t_span)` returns time-aligned
   arrays; RPM_SURF is interpolated onto the vibration grid **here**;
   `order_domain.py` consumes only aligned pairs. Alignment ownership: sessions.py,
   full stop.
4. **Ω_min guard:** windows with min RPM < **10 RPM** are order-invalid (badged; no
   order evaluation; no division).
5. **Backpressure:** bounded per-channel ingest buffers; above **30 s** of backlog
   the server drops-oldest and NACKs the frame (`{"ack": false, "reason":
   "backlog"}`), counted in `/health`.
6. Registry entries carry profile assignment and class observability — the scheduler
   is data-driven.

## 17. Outbound stream & REST surface

`/ws/monitor` pushes **five** message types (frontend renders all five):

1. `spectral_frame` — downsampled log-magnitude STFT column(s) per channel/profile
   (uint8-quantized, base64) for the scrolling spectrogram; carries its uint8 scale:
   `{db_floor, db_ceil}`.
2. `constellation` — new peaks [(t, f_or_order)] to overlay; peak times in the
   stream clock (+ revolution index in ORDER).
3. `detection` — full Detection object: class, tier, episode, confidence
   (= 1 − p_corr), score, lambda, p_corr, aligned_count, delta_star, histogram
   (binned), sssi, dominant_orders, matched_hashes (capped list for the drill-down),
   library_version.
4. `twin_state` — the 3D twin's state vector (§24).
5. `scenario_event` — captions and camera events from the scenario player (§32).

**The stream clock:** every message carries **`t`** — data-time seconds since the run
epoch. Scenario/replay runs: epoch = 0.0. **LIVE mode: the epoch latches at the
session's first accepted ingest frame; t = t0_wall − t0_first** — so monitor t is
run-relative in both modes and "nothing changes between simulate and live" (§31)
stays true. Wall-clock never appears in the data plane. `latency_ms` and
measured-wall-time diagnostics live in a `diag` sub-object, **excluded from the
determinism hash** (§33).

REST: `GET /libraries`, `POST /libraries/{v}/activate` (approval-gated, §15),
`GET /episodes?class=`, `GET /scenarios`, `GET /bench/report`, `GET /health`, plus
auto-generated OpenAPI at `/docs` — the API-first, integrable-service posture.

## 18. Performance targets (assert in tests, quote in demo)

**Alerting is two-tier** — amber advisory for speed, red confirmed for proof (§19's
palette encodes exactly this: amber = advisory, red = confirmed *exclusively*):

**Tier 1 — ADVISORY (amber).** SSSI (§2) on a rolling window of 2 predicted periods
(band-filtered torque), plus band-energy RMS watchers for whirl/bounce. Fast,
class-suggestive, not episode-matched.
- **Calibration (normative — Tier 1 is held to the same standard as the §14
  baseline):** thresholds are fit on a normal-only validation run to a budget of
  **≤ 2 advisories per data-hour**, frozen before any gate or benchmark is scored,
  and recorded in `report.json`. An uncalibrated advisory tier would be
  tunable-to-pass, reintroducing the unfalsifiability §14 removes.
- Targets: stick-slip advisory ≤ **20 s** at reference conditions (L ≤ 3000 m,
  ≥ 90 RPM); scales as ~2 predicted periods + margin for deeper/slower corners.
  Whirl/bounce advisory ≤ **5 s**.

**Tier 2 — CONFIRMED (red).** The fingerprint match under §10's corrected
significance.
- **Mechanism note (this is where the numbers come from):** confirmation does *not*
  wait for a full query window. Score ≥ s_min = 8 aligned hashes needs roughly 3
  dysfunction-bearing frames (~5 peaks/frame, F = 8 fan-out), i.e. ~6 revolutions of
  ORDER data, plus K = 2 evaluations at the 1-rev cadence → floor ≈ **4 s at
  120 RPM** for whirl/bounce. Stick-slip floor is set by LOW frame fill (~2 frames
  post-onset ≈ 32–38 s) plus debounce.
- Targets (data-time, from onset; at 10 dB / at 0 dB SNR; reference conditions
  L ≤ 3000 m for stick-slip):
  - stick-slip ≤ **60 s / 90 s** (LOW-DEEP wells: ≤ 2× these — periods and frames
    both double)
  - whirl ≤ **8 s / 15 s** at ≥ 120 RPM; rev-scaled at lower speed (floor ≈ 8 rev +
    2 rev): ≤ **16 s / 30 s** at 60 RPM
  - bit bounce ≤ **12 s / 20 s** at ≥ 120 RPM; same rev-scaling: ≤ **20 s / 30 s**
    at 60 RPM

Evaluation cadence is per-profile (§6) in **data-time**; K = 2 consecutive confident
evaluations required, the second containing ≥ 1 hop of data absent from the first.
Every number above is a derived floor plus margin, with the derivation stated so it
can be re-checked when parameters move. At the demo's 8× replay even the 60 s
stick-slip confirmation fires 7.5 s (wall) into its 35 s segment (§34).

Other targets:
- Matcher evaluation ≤ 10 ms per window at 10⁶ stored hashes (measure; will be far
  under).
- Sustained ingest ≥ 5 channels × 400 Hz on one core.
- Library build (full synthetic sweep) ≤ 5 min on a laptop (§12 build budget;
  CI-measured).

---
# PART V — INTERFACE SPECIFICATION
*(User builds this in parallel; this section is the design contract so backend message
shapes and frontend expectations never drift.)*

## 19. Design direction — "instrument, not dashboard template"

The product must read as a **rig-floor instrument**: the visual language of drilling
control cabins and mud-logging units, not a SaaS admin template. Deliberate direction:

- **Palette (choose for meaning, not fashion):** deep drilling-fluid green-black
  base (#0B1512-family), phosphor-trace green for live signal traces, amber for
  advisory states (Tier 1, §18), signal-red *reserved exclusively* for confirmed
  detections (Tier 2) — color is a severity code, never decoration. Avoid the generic
  AI looks (cream+serif+clay, black+acid-green as ambient styling, faux-newspaper
  hairlines).
- **Typography:** an engineering-grade monospaced/semi-mono family for all numerics
  and channel mnemonics (tabular figures mandatory — values must not jitter), paired
  with a compact grotesque for labels. Type is the personality; keep it disciplined.
- **Signature element (the one memorable thing):** the **Alignment View** — when a
  detection fires, the offset histogram animates its spike rising out of the Poisson
  noise floor beside the (t_query, t_library) diagonal scatter. This is the
  mathematical proof rendered as the hero moment. Nothing else on screen animates
  as strongly. This view is what people will remember and what no ML product can show.
- **Copy:** plain, operational, active voice. "Stick-slip confirmed — SS-014 ·
  score 34 · p < 1e-9 · period 4.6 s". Errors state cause + action. Empty library
  state invites: "Build the fingerprint library to begin — `drillprint library build
  --config well01.yaml`".

## 20. Screens

1. **Monitor (main).** Left: channel rail (live sparklines, fs badge, observability
   badges per §5/§6 — greyed classes the channel physically cannot see, "partial
   band" badges where only the fundamental fits). Center: scrolling
   spectrogram (canvas; time or order domain toggle) with constellation overlay;
   detected-episode hash pairs flash-connect on match. Right: detection feed (newest
   pinned, tier, confidence, SSSI where relevant). Bottom strip: rig context (bit
   depth, RPM, WOB from replay metadata) + the predicted-f₀ marker drawn ON the
   spectrogram axis — at 1/T with a shaded band down to 1/(2.0·T), labeled
   "predicted range" (T = T_model for synthetic wells, T_field for real wells, §2) —
   physics prior made visible.
2. **Detection drill-down (modal/route).** The Alignment View (signature), matched
   hash table, episode provenance (generator params or Volve well/interval),
   library version — the full audit chain of §0, item 1.
3. **Library.** Versions, per-class episode counts, hash counts, approval status,
   activate/rollback.
4. **Benchmark.** Renders `bench/report.json`: confusion matrix, PR curves, latency
   histogram, DrillPrint-vs-baseline table, calibration records, measured
   performance numbers of §18.
5. **About/Method.** One screen of the math with the three equations that matter
   (STFT, hash tuple, Ω = −ω(N_b+1)) — the "advanced research side" made legible to
   a NAICE/ATCE-audience visitor in 60 seconds.

Accessibility floor: keyboard focus visible, reduced-motion variant (histogram spike
appears without animation), all state colors double-encoded with icons/text.

---

# PART VI — BUILD PLAN

## 21. Milestones (each ends green on `pytest` + a runnable artifact)

- **M0 — Engine core (pure DSP).** `stft.py`, `peaks.py`, `hashing.py`, `matcher.py`,
  `types.py` + unit tests: known sinusoid → correct bin; synthetic constellation →
  exact hash set; planted offset → histogram spike at δ*; corrected-significance
  (p_corr) sanity, including the s_min = 8 vs λ ≤ ~0.3 bound of §10; the
  frames_per_window(W, profile) ≥ T_max + 3 import-time invariant of §6.
- **M1 — Synthesis.** All four generators + the §12 physics sanity gates as tests —
  only what needs no resampling: the §12.1 gate battery (stability screen; period ∈
  [1.0, 2.0] × T_model; stick; swing; comb *spacing* = f₀, never an odd/even
  pattern), whirl/bounce **line presence in Hz** at RPM-proportional frequencies,
  and time-domain smearing under an RPM ramp.
- **M2 — Order domain.** `order_domain.py` + the §9 anti-alias filter + the full
  de-circularized invariance suite: build a *test-only* time-domain (HIGH-profile)
  fingerprint set from the constant-RPM whirl episodes — never shipped in a
  production library — and assert all four cells: constant-RPM query matches BOTH
  the time-domain test set and the ORDER library; ramp-RPM query **fails** the
  time-domain set (smearing — the §9 contribution, demonstrated against real
  content) and **matches** the ORDER library at high confidence. Plus the Jeffcott
  cross-check episode (§12.2). This suite IS the §9 contribution, as tests.
- **M3 — Store + library build.** SQLite schema v2, bulk insert (executemany, WAL),
  `python -m synth.build_library` full sweep ≤ 5 min, version activation +
  approval-state enforcement.
- **M4 — Streaming service.** FastAPI app, WS ingest/monitor (five message types,
  stream clock), replay player, twin_state emission + gate-6 backend tests (§29),
  end-to-end test: replay composite run → assert detection messages with correct
  classes and tiers, latencies within §18.
- **M5 — Bench.** Full protocol of §14 + report.json (including calibration
  records) + one-command reproduction.

Order matters: no web code before M2 passes. Keep every matcher decision
reconstructable from stored data (explainability is a feature, not a log).

## 22. Acceptance gates (the demo script, as tests)

1. **Gate 1 (stick-slip; reference conditions L ≤ 3000 m, ≥ 90 RPM):** 0 dB SNR
   run → Tier-1 advisory ≤ 20 s; Tier-2 ≤ 90 s with p_corr < 1e-4, score ≥ 8; SSSI
   reported. (LOW-DEEP wells: doubled targets, same statistics.)
2. **Gate 2 (false alerts):** 1 h data-time of pump-comb normal runs per SNR →
   **zero Tier-2 alerts AND Tier-1 within its calibrated ≤ 2/h budget**.
3. **Gate 3 (RPM ramp):** whirl under 80→140 ramp → sustained Tier-2 detection in
   ORDER; the same query matches the M2 time-domain test set at constant RPM but
   fails it under the ramp (all four §21/M2 cells asserted).
4. **Gate 4 (backend half):** replay runs; spectrograms stream (LOW-DECIM for ~1 Hz
   channels); band-aware badges correct, including "entirely blind" and "partial
   band" channels; any stick-slip-band findings labeled "surface-cadence limited."
5. **Gate 5:** `GET /bench/report` complete per §14; baseline + Tier-1 calibration
   records included.
6. **Gate 6** — twin choreography/state: defined with the twin build additions, §29.
7. **Gates 7 / 7b** — demo boot & flagship scenario: defined with the demo build
   additions, §35.

---

# PART VII — OPERATOR FLOWS & DEMO MODE

*Principle: the demo is a product feature, not a presentation hack. Everything below is
built, tested code — including the 2-minute presentation itself.*

## 30. Positioning statement (bake into About screen + paper narrative)

The current state of the art splits into (a) deployed index/threshold detectors (SSSI-
style surface torque-swing indices) — simple, robust, but class-blind and episode-blind;
and (b) ML classifiers reporting 96–100% same-well accuracy but with a documented
generalization gap: limited applicability beyond the training field/BHA, with severe-
event detection falling to ~60% on unseen wells (TMLR 2025; SPE/IADC 2024 discussion of
AI generalization limits). **DrillPrint is a training-free, physics-derived answer to
that generalization problem:** the fingerprint library is computed from first principles
(string-length-clocked torsional modes; blade-count-clocked whirl orders) plus parameter
sweeps — deploying to a new well means recomputing physics priors, not collecting
labeled downhole data. Detection is deterministic retrieval with per-alert proof.
This paragraph, nearly verbatim, is the answer to "why not just use ML?"

## 31. Engineer workflow (the product's real lifecycle)

Four stages, each one screen/command, linear left-to-right in the UI header
(BUILD → VALIDATE → SIMULATE → LIVE), state persisted per project:

**Stage 1 — BUILD.** Define the well context (string length, bit blades N_b, channel
set with f_s) → the UI shows *predicted* signatures before any data exists (f₀ from
**1/T** per §2's predictors — T_model for synthetic wells, T_field for real ones;
4L/c_t is a *period* and survives only as the classical upper-bound intuition — whirl
order N_b+1, bounce order 3) → generate/import episodes:
`drillprint library build --config well01.yaml` (synthetic sweep) and/or
`drillprint library import data/labeled/ --class STICK_SLIP` (real labeled intervals).
Output: versioned library with per-class episode + hash counts.

**Stage 2 — VALIDATE.** One command: `drillprint bench run --library v3` → §14
protocol → report.json → Benchmark screen. Gate: engineer explicitly "approves"
a library version (stored as status='approved' with name/timestamp, §15) before it
can go live — the enterprise change-control gesture, enforced by the store:
`POST /libraries/{v}/activate` rejects anything not approved.

**Stage 3 — SIMULATE.** Scenario runner (§32). Replay composite runs or Volve data
against the approved library at 1×–60× speed with the full Monitor + 3D twin live.
This stage IS the demo mode.

**Stage 4 — LIVE.** Same pipeline, ingest switched from replay player to `/ws/ingest`
(the monitor clock stays run-relative — the epoch latches at first ingest, §17). The
point (say it in the demo): *nothing changes between simulate and live except the
data source* — the replay player and a rig feed hit the identical code path.

## 32. Scenario system

A scenario is a JSON manifest — data + narration + camera choreography in one file:

```json
{ "id": "flagship_2min", "title": "Full dysfunction sweep",
  "library": "v3", "required_status": "approved", "speed": 8.0,
  "segments": [
    {"t": 0,  "source": "run:flagship/seg1_normal_pumpnoise", "dur": 15,
     "caption": "Normal drilling — pump noise present, no alerts"},
    {"t": 15, "source": "run:flagship/seg2_stick_slip", "dur": 35,
     "caption": "Stick-slip onset", "camera": "bha_close"},
    {"t": 50, "source": "run:flagship/seg3_whirl_ramp", "dur": 30,
     "caption": "Backward whirl under RPM ramp — order-domain match", "camera": "bit_orbit"},
    {"t": 80, "source": "volve:F-9A/seg_2210", "dur": 30, "optional": true,
     "caption": "Real North Sea field data — Volve", "camera": "overview"}],
  "hotkeys": {"space": "pause", "1..4": "jump_segment", "d": "open_drilldown",
              "b": "benchmark_screen", "r": "restart"} }
```

**Units and addressing (normative):**
- Manifest `t`/`dur` = **wall-clock presentation seconds**; `speed` multiplies data
  consumption → at 8× the segments consume 120 / 280 / 240 / 240 s of data. Segment
  wall timeline: 15 + 35 + 30 + 30 = 110 s + 10 s close (screen switch) = 120 s —
  one story across §32/§34.
- **`run:` sources reference generated runs**, form `run:<scenario>/<segment-id>`,
  resolving to a run manifest in `data/demo_cache/` that records generator, params,
  seed, duration (e.g. segment 2's run manifest records `stick_slip, L=3000,
  rpm=120, ratio=1.6, jb=200, seed=1042, dur=280`). Synthetic library episodes keep
  the §15 slug form for UI copy; `volve:` sources resolve via
  `data/volve/segments.yaml` (§13).
- Segment 4 is **optional**: absent Volve data → the scenario player skips it with
  the caption "Volve data not present — see README"; the demo runs as a 3-segment
  show (§35, gate 7b).

Backend: `replay/scenario_player.py` executes manifests (segment sequencing, speed,
caption + camera events pushed over `/ws/monitor` as `scenario_event` messages).
Frontend: renders captions as a subtle lower-third; camera events drive the twin's
orchestrated moves; hotkeys always active. Scenarios live in `scenarios/*.json` —
adding a new demo is editing JSON, not code.

## 33. Demo Mode guarantees (engineering against Murphy)

- **One-command boot:** `drillprint demo` → verifies approved library exists (builds
  flagship library from cache if missing), starts API + serves built frontend, opens
  browser to `/demo`, preloads scenario list. Cold start ≤ 15 s; assert in CI.
- **The cache is a prebuilt artifact:** `data/demo_cache/` ships the approved
  flagship fingerprint DB (~20 MB) + pre-generated run data. "Builds from cache" =
  **file copy + activate (< 1 s)**. Missing cache → full build with a console
  warning that the 15 s guarantee doesn't apply. CI asserts the cached path ≤ 15 s
  on its machine class, documented as such.
- **Zero-network demo:** everything local (synth data bundled, Volve segments cached
  only if the Equinor license permits redistribution — §13; otherwise user-placed
  and the show is 3 segments — no CDN fonts/assets). Conference Wi-Fi cannot hurt
  you.
- **Warm start:** scenario 1's first 5 s pre-buffered on boot — pressing PLAY
  produces motion within one frame. Dead air kills 2-minute demos.
- **Reset discipline:** `r` restarts the scenario to a byte-identical state. The
  mechanism: a **virtual clock** (run epoch t = 0.0; all cadences in data-time, §17;
  replay speed only paces delivery) + seeded RNG everywhere (scenario player owns
  the clock) + the **canonical output log** = ordered /ws/monitor messages with
  `diag` stripped, hashed across runs. Run it 50 times, identical 50 times.
- **Fallback:** a `--record` capture mode (screen + timing → MP4) is deferred to
  v1.4 unless its headless-capture dependency is explicitly accepted.
- **Presenter HUD (`?`):** translucent overlay with hotkeys + elapsed time.

## 34. The 2-minute flagship script (scenarios/flagship_2min.json — this is code)

Spoken-word timings at 8× replay speed (wall-clock; the segments consume
120 / 280 / 240 / 240 s of data); captions carry the argument even if the presenter
says nothing:

- **0:00–0:15 — Hook (screen already live, normal drilling).** "Shazam identifies a
  song from a noisy bar in seconds. This is Shazam for drilling failures." Twin
  rotating calmly, spectrogram scrolling, pump-noise comb visible and *unalerted* —
  false-positive immunity demonstrated before a word about it.
- **0:15–0:50 — Stick-slip.** Torque sawtooth appears; the **amber advisory** fires
  within seconds (SSSI, Tier 1) — "the instrument reacts immediately, and says so in
  amber: advisory, not yet proof." The twin shows string wind-up, bit stalls, whips
  free; then the **red confirmed** card fires (Tier 2, ~5–7.5 s wall into the segment
  at 8×): class, episode, score, p-value, period. Press `d`: **Alignment View** —
  "thirty-four hash matches, one time offset — the odds of that happening by chance
  are below one in a billion. That's not a probability from a black box — it's a
  p-value you can audit."
- **0:50–1:20 — Whirl under RPM ramp (the research beat).** RPM ramps 80→140 on
  screen; whirl orbit + wall strikes in the twin; the red detection *holds* through
  the ramp. "Speed is changing, the signature moves with it — we fingerprint per
  revolution, not per second. Time domain for string-clocked failures, order domain
  for rotation-clocked ones. That's the contribution."
- **1:20–1:50 — Real field data (when Volve data is present; otherwise the show is
  three segments and this beat moves to the benchmark screen).** Caption: *Volve
  field, North Sea — real WITSML.* "Same engine, zero retraining. ML detectors drop
  to ~60% on wells they've never seen — this needs no training at all, because the
  library comes from physics." The badges stay honest: at surface cadence only
  stick-slip-band content is even visible.
- **1:50–2:00 — Close.** Press `b`: benchmark screen (PR curves, latency, baseline
  comparison, calibration records). "Deterministic, explainable, physics-derived,
  real-time — and every number on this screen regenerates with one command." End on
  the About screen's three equations.

## 35. Build additions

- **M7 — Flows & demo.** scenario_player +
  scenario_event messages + `drillprint` CLI (library/bench/demo subcommands, typer)
  + demo boot guarantees as tests (cold-start time on the cached path, warm-buffer,
  reset determinism via hash comparison of the canonical output log — ordered
  /ws/monitor messages with `diag` stripped — across two runs).
- **Acceptance gate 7:** `drillprint demo` from clean clone (cache present) → cold
  start ≤ 15 s; segments 1–3 fire their expected detections at expected **wall-clock
  times ± 2 s** (expected times computed from §18 at 8× — stick-slip Tier-2 fires
  ~5–7.5 s wall into its 35 s segment; whirl ~1–2 s in, fill starting at the ramp's
  80 RPM; the beats land with margin); **segment 1: zero Tier-2 AND zero Tier-1**;
  sustained whirl detection through the ramp; determinism hash identical across two
  runs.
- **Acceptance gate 7b (only when Volve data is present):** segment 4 plays with
  honest badges (LOW-DECIM streaming for ~1 Hz channels, correct observability) —
  **never a guaranteed detection** (at 1–10 s cadence some segments are entirely
  blind to every class; the UI must say so).

---
# PART VIII — 3D DIGITAL TWIN (THE RIG VIEW)

*The Monitor screen gains a primary 3D visualization pane — a live, realistic digital
twin of the wellbore and drillstring, animated by the same data stream the engine
consumes. Target feel: SLB DrillOps / drilling-simulator class, not a toy diagram.*

## 24. Principle: the twin animates DATA, never fakes physics

The 3D scene is a *renderer of state*, not a second simulator. Every motion on screen
is driven by real stream values — surface RPM, downhole RPM (synthetic/replay),
torque, WOB, hookload, detection events, SSSI, dominant orders. This keeps the twin
honest (audit chain intact: what you see IS the data) and cheap (no physics on the
GPU). Where a needed state isn't in the stream (e.g., whirl orbit phase), derive it
deterministically from stream values — orbit angle = ∫Ω_orbit dt with
**Ω_orbit = −N_b·ω**, the inertial-frame orbit rate of §3 (the sensor-frame line at
order N_b+1 is what the fingerprint hashes, never what the orbit animates) — and
label the pane "reconstructed from measured spectra" — expert honesty, SLB-style.

**Backend additions:** extend `/ws/monitor` with the `twin_state`
message type (§17), one message per **40 ms of data-time** (25 Hz):

```json
{"type": "twin_state", "t": 421.16,
 "bit_depth_m": 3014.1, "hole_depth_m": 3014.1,
 "rpm_surface": 118.2, "rpm_downhole": 42.7,
 "torque_knm": 14.8, "wob_kn": 82.0, "hookload_kn": 940.0,
 "twist_rad": 47.16,
 "block_pos_m": 12.3,
 "active_detections": [{"class": "STICK_SLIP", "tier": 2, "confidence": 0.9999,
                        "p_corr": 1.0e-9, "score": 34, "sssi": 0.42}],
 "whirl": {"active": false, "order": null, "phase_rad": 0.0, "eccentricity": 0.0},
 "bounce": {"active": false, "amp_mm": 0.0, "phase_rad": 0.0}}
```

`t` is the stream clock (§17). The bit is on bottom (bit_depth = hole_depth), so
WOB 82 kN is legitimate. `twist_rad` = T/k from §2 (real elastic wind-up angle),
computed at the printed depth: k = G·J_p/L = 945,950 / 3014.1 = 313.85 N·m/rad;
14,800 / 313.85 = **47.16 rad** (7.51 turns). k derives from the well-context config
(§15) with L = current bit depth. Whirl/bounce phase is integrated server-side in
`engine/twin_kinematics.py` (§15) so all clients see identical motion; fields carry
the latest channel-native sample (**zero-order hold server-side; clients lerp for
display** — interpolation ownership is stated, not duplicated).

**Field ← channel map (explicit, §16 registry):** rpm_surface ← RPM_SURF ·
rpm_downhole ← RPM_DH · torque_knm ← TORQUE_SURF · wob_kn ← WOB · hookload_kn ←
HOOKLOAD · bit_depth_m ← BIT_DEPTH · hole_depth_m ← HOLE_DEPTH · block_pos_m ←
BLOCK_POS.

## 25. Stack & scene graph

**React Three Fiber (Three.js) + drei + postprocessing.** Fits the existing
React/Vite/Vercel plan; declarative scene as components; 60 fps on integrated GPUs
if the budget below is respected.

```
<Canvas shadows>
 ├─ Environment: HDRI (industrial dusk), fog for depth cueing
 ├─ RigFloor: derrick base, rotary table, top drive (animated: rotation = rpm_surface,
 │            vertical = block_pos_m), drawworks lines
 ├─ EarthSection: cutaway ground volume — layered formation strata (sand/shale/carbonate
 │            palette), borehole cased upper / open lower, mud column with subtle
 │            animated flow shader in the annulus
 ├─ Drillstring: instanced pipe joints (tool joints modeled — the visual rhythm experts
 │            expect), transitions to drill collars, stabilizers, MWD sub, bit
 ├─ Bit: PDC with N_b blades (parametric — matches library episode metadata)
 ├─ Sensors: glowing ring markers at surface + BHA measurement points (click → that
 │            channel's spectrogram — the twin is NAVIGATION, not just decoration)
 └─ FX layer: detection-triggered effects (§27)
```

**Scale problem (must solve, or it looks fake):** a 3 km string at true scale is a
1-pixel hair. Use the drilling-visualization convention: **telescoped depth** — true
proportions near surface and near the BHA, with a clearly-marked compressed mid-section
(break symbol + depth ticks), plus a **camera elevator** that travels the string.
Radial scale exaggerated ~50× for the wellbore cutaway; state both factors in a
persistent HUD chip ("radial ×50 · mid-string compressed") — experts respect declared
exaggeration and distrust undeclared realism.

## 26. Realism kit (what makes it read as engineering-grade)

- **PBR materials:** worn steel (roughness maps, subtle rust at tool joints), matte
  formation strata, wet sheen on mud; no cartoon colors — severity color arrives only
  as *emissive light* on affected components.
- **Lighting:** low-key industrial rig lighting + rim light on the string; shadow-
  casting top drive. SSAO + mild bloom (bloom reserved for detection emissives).
- **Depth cues:** fog gradient down-hole, particle motes in mud, depth ticks every
  250 m on the borehole wall.
- **Motion fidelity:** top drive and string rotation locked to rpm_surface (visual
  rotation capped/stroboscope-safe above ~90 RPM: render sub-multiple with motion
  blur, standard turbine-viz trick); block position from hookload/block channel;
  slow camera drift when idle (nothing is ever frozen).
- **Performance budget:** ≤ 150k triangles via instancing; single 2k HDRI; target
  60 fps desktop / 30 fps laptop; `<AdaptiveDpr>` fallback; reduced-motion mode swaps
  animation for annotated static states.

## 27. Dysfunction choreography (data → motion mapping)

This is the demo's soul — each detection has a physically-truthful motion signature.
**Choreography derives exclusively from `twin_state.active_detections`** (single
socket, TCP-ordered — which is what makes §29's 200 ms gate attainable). Entries
carry `tier` (§10): **tier 2 triggers motion choreography; tier 1 drives amber
HUD/emissive only — never a motion signature** (§19's "red exclusively for confirmed"
extended to motion).

- **STICK-SLIP:** BHA section visually decouples: bit RPM → rpm_downhole (grinds to
  a stop) while surface keeps turning; the pipe between shows *accumulating helical
  twist* — the choreography distributes the full multi-turn wind-up across joints,
  summing to twist_rad (totals routinely exceed 2π; 7.5 turns over 3 km is the
  physically real — and more dramatic — picture), with a subtle shear-stripe texture
  so wind-up is visible — then a whip-release as rpm_downhole spikes. Amber→red
  emissive on the torsion-loaded interval scaled by SSSI. Camera auto-frames the BHA
  on first confirmation (one orchestrated move, then hands control back).
- **BACKWARD WHIRL:** bit/BHA axis traces the whirl orbit — offset = eccentricity ×
  clearance, orbit direction *opposite* rotation at the inertial rate
  **Ω_orbit = −N_b·ω** from phase_rad (§3, §24); wall-contact flashes at the M-lobe
  pattern, M = j·N_b+1 (impact sparks + decal ring marks accumulating on the borehole
  wall — damage history as texture). The M-lobed hypotrochoid path is drawn as a
  fading trail: the math literally inscribed in 3D.
- **BIT BOUNCE:** bit axial oscillation from bounce amp/phase; hole-bottom shows the
  tri-lobed pattern (displacement-mapped disc, N_lobes from metadata); dust puff +
  WOB gauge slam on each contact; hookload trace ripples in sync.
- **NORMAL:** smooth rotation, gentle mud shimmer, green status lighting — the calm
  baseline that makes dysfunction states land.

Every choreography parameter comes from twin_state or detection metadata — zero
client-side randomness in motion (randomness allowed only in cosmetic particles).

## 28. Layout integration & interaction

Monitor screen becomes a three-zone cockpit: **left** channel rail (unchanged) ·
**center** 3D Rig View (dominant, ~55% width) · **right** spectrogram + detection feed
(§20 content). The Alignment View (signature element, §19) still owns the detection
drill-down — the twin gets people leaning in; the histogram spike is still the proof.
Interactions: orbit/zoom (damped), sensor-click → channel focus, detection-card
hover → highlights the affected string interval in 3D, timeline scrub (replay mode)
drives both twin and spectrogram from the same clock. HUD chips: bit depth, RPM in/out,
torque, WOB, scale disclosure.

## 29. Build additions

- **Milestone M6 (frontend; backend supplies twin_state):** static scene →
  data-driven rotation/twist → choreographies → FX/polish, in that order. Backend M4
  gains twin_state emission + the gate-6 backend tests below; the rendered-state
  audit and the 30 fps requirement stay in M6.
- **Asset note:** model derrick/top-drive/bit as parametric primitives + instancing in
  code (no heavy GLTF dependency), boolean-free cutaway via clipping planes —
  keeps the repo self-contained and the bundle small.
- **Acceptance gate 6 (backend half, tested in M4):** the twin_state log is
  self-consistent — twist_rad = torque/k exactly (§24 values); whirl phase continuous
  at Ω_orbit = −N_b·ω across messages; tier semantics per §27 (tier 2 → motion,
  tier 1 → amber emissive only); choreography fields null-safe when no detection;
  rig-context channels present for synthetic runs.
- **Acceptance gate 6 (frontend half, M6):** replay the composite run of §22 with the
  twin attached — choreography state must match the detection feed within 200 ms,
  30 fps minimum on a mid-range laptop, and every animated quantity traceable to a
  stream field (audit script: record twin_state log, diff against rendered state).

---

## 23. References (renumbered position, original §23 — verify formatting before citing in any manuscript)

- Wang, A. (2003). *An Industrial-Strength Audio Search Algorithm.* ISMIR 2003 —
  constellation maps, combinatorial hashing, diagonal-alignment scoring.
- Wang, A. (2006). *The Shazam music recognition service.* CACM 49(8).
- Kyllingstad, Å. & Halsey, G.W. (1987). *A Study of Slip-Stick Motion of the Bit.*
  SPE 16659 — canonical stick-slip mechanism description.
- Lines et al. (2013) and the HFTO review literature — LFTO ≈ 0.3 Hz fundamental,
  stick-slip vs HFTO taxonomy.
- Backward-whirl kinematics: sensor-frame Ω_sensor = −ω·d_h/(d_h−d_b) = −(N_b+1)·ω;
  inertial orbit Ω_orbit = −ω·d_b/(d_h−d_b) = −N_b·ω; cutter-induced bit whirl line
  Ω = −ω(N_b+1), lobe relation M = j·N_b+1 (patent + field-test literature; j is the
  lobe integer, §3).
- Downhole vibration mode band assignments — literature bands: stick-slip 0.1–5 Hz;
  bit bounce 1–10 Hz axial; whirl 10–50 Hz lateral (§5 is the normative table for
  this system) — state-machine vibration-monitoring patent literature.
- Brandt, A. — *Noise and Vibration Analysis* (order tracking / angular resampling,
  standard rotating-machinery reference).
- Equinor Volve open dataset — real-time drilling WITSML logs.

*Positioning note for the eventual paper/demo narrative: frame as "methodological
transfer of combinatorially-hashed constellation fingerprinting from audio retrieval
to drilling dysfunction surveillance, with a dual-domain (time/order) formulation for
rotation-clocked phenomena." That sentence is the abstract's spine.*
