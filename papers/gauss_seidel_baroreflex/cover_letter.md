Dear Editor-in-Chief,

We are submitting our manuscript entitled "Spurious Steady State from a dt-Dimensional Mismatch in FactorCommand Events: A Canine Cardiovascular Case Study" for consideration as a Technical Note in SIMULATION: Transactions of the Society for Modeling and Simulation International.

**Contribution.** This paper documents a previously unreported failure mode in modular simulation architectures: a threshold-gated discrete inter-module event was implemented with a per-step increment (bpm/step) instead of a time-normalized rate (bpm/s), producing a steady-state MAP bias of +44.7 mmHg that standard convergence diagnostics could not detect. We term this a "spurious steady state" — a stable fixed point of the discrete system that does not correspond to any fixed point of the continuous-limit system. The correction required 7 lines of code; the detection required a non-obvious dimensional analysis.

**Relevance to SIMULATION.** The paper's primary contribution is to simulation methodology, not to cardiovascular physiology per se. The FactorCommand dispatch pattern (`target`, `op`, `value`) studied here is a domain-neutral interface for inter-module communication that appears in physiological engines, robotic co-simulation, and DEVS-based frameworks. The paper contributes to the journal's scope in four ways:

1. It identifies a failure mode — spurious steady state — that is inherent to the design pattern of threshold-gated discrete events coupling continuous integration modules, and is therefore relevant across simulation domains.
2. It provides a formal definition and mechanistic analysis of the failure mode, including the conditions under which it arises (dimensional inconsistency + threshold gating + physiological saturation).
3. It proposes a three-condition isolation experiment design using subprocess isolation to disentangle multiple simultaneous code corrections — a methodology applicable to any multi-fix debugging scenario.
4. It releases a static lint tool (`check_fc_dimensions.py`) that automatically detects dimensional inconsistencies in FactorCommand emissions, providing a reusable artifact for the simulation community.

**Scope and format.** The manuscript (~4,500 words, 4 figures, 4 tables) is structured as a Technical Note documenting the complete journey from discovery through diagnosis to correction. All results are reproducible from open-source code and data at <https://github.com/ningjie333/virtual-vet>.

**Prior publication.** This work has not been published previously and is not under consideration elsewhere. The sole author has approved the manuscript and agrees with its submission.

We believe this paper will be of interest to the SIMULATION readership — particularly readers working in the Medical Modeling & Simulation section — as a cautionary tale with practical detection strategies for a class of numerical errors that standard verification methods miss.

Sincerely,

Ning Jie
College of Animal Sciences, Zhejiang University
<ningjie@zju.edu.cn>
