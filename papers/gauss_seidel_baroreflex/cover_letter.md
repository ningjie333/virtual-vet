Dear Editor-in-Chief,

We are submitting our manuscript entitled "Spurious Steady State from dt-Dimensional Ambiguity in Modular ODE Coupling: A Failure Mode, Detection Protocol, and Cardiovascular Demonstration" for consideration as a Technical Note in SIMULATION: Transactions of the Society for Modeling and Simulation International.

**Contribution.** This paper documents a previously unreported verification failure mode: a threshold-gated discrete inter-module event was implemented with a per-step increment (bpm/step) instead of a time-normalized rate (bpm/s), producing a steady-state MAP bias of +44.7 mmHg that passed all standard verification diagnostics — dt refinement, steady-state detection, parameter sweeps, and ordering swap tests. We term this a "spurious steady state" — a stable fixed point of the discrete system that does not correspond to any fixed point of the continuous-limit system. The correction required 7 lines of code; the detection required a non-obvious dimensional analysis that no automated tool flagged.

**Relevance to SIMULATION.** The paper's primary contribution is to verification and validation methodology. Standard V&V practice assumes that dt refinement will reveal convergence problems, and that steady-state detection will confirm correct operating points. Our results show a specific, reproducible scenario where both assumptions fail: the system converges to a stable but wrong steady state that is invariant across dt refinement and parameter sweeps. The paper contributes to the journal's scope in four ways:

1. It identifies a failure mode — spurious steady state — that is inherent to the design pattern of threshold-gated discrete events coupling continuous integration modules, and that systematically evades standard verification methods.
2. It provides a formal definition and mechanistic analysis of the failure mode, including the conditions under which it arises (dimensional inconsistency + threshold gating + saturation truncation).
3. It proposes a three-condition isolation experiment design using subprocess isolation to disentangle multiple simultaneous code corrections — a verification methodology applicable to any multi-fix debugging scenario.
4. It releases a static lint tool (`check_fc_dimensions.py`) that automatically detects dimensional inconsistencies in discrete event emissions, providing a reusable V&V artifact for the simulation community.

**Scope and format.** The manuscript (~5,000 words of body text, 2 figures, 4 tables) is structured as a Technical Note documenting the complete journey from discovery through diagnosis to correction. All results are reproducible from open-source code and data at <https://github.com/ningjie333/virtual-vet-paper>.

**Suggested classification.** We suggest the paper be classified under *Theory and Methodology — Verification, Validation and Accreditation* (primary) and *Applications in Science and Engineering — Biomedical and Medicine* (secondary).

**Prior publication.** This work has not been published previously and is not under consideration elsewhere. The sole author has approved the manuscript and agrees with its submission.

We believe this paper will be of interest to the SIMULATION readership as a case study in verification failure: a class of numerical errors that standard V&V methods miss, with concrete detection strategies and an automated lint tool.

Sincerely,

Yibo Wang
College of Animal Sciences, Zhejiang University
<3230100266@zju.edu.cn>
