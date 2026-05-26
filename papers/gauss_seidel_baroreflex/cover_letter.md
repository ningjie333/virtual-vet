Dear Editor-in-Chief,

We are submitting our manuscript entitled "Spurious Steady State from a dt-Dimensional Mismatch in FactorCommand Events: A Canine Cardiovascular Case Study" for consideration as a Technical Note in SIMULATION: Transactions of the Society for Modeling and Simulation International.

**Contribution.** This paper documents a failure mode in modular ODE simulation that, to our knowledge, has not been previously reported: a threshold-gated discrete inter-module event was implemented with a per-step increment (bpm/step) instead of a time-normalized rate (bpm/s), producing a steady-state MAP bias of +44.7 mmHg that standard convergence diagnostics could not detect. We term this a "spurious steady state" — a stable fixed point of the discrete system that does not correspond to any fixed point of the continuous-limit system.

**Relevance to SIMULATION.** The paper contributes to the journal's scope of simulation methodology in three ways: (1) it documents a specific failure pattern in sequential Euler coupling with threshold-gated discrete events, (2) it proposes a three-condition isolation experiment design for disentangling multiple simultaneous code corrections, and (3) it provides four practical detection heuristics for developers of modular simulation engines. The findings are relevant to any domain where discrete events modify continuous state variables — including co-simulation, circuit simulation, and agent-based models.

**Scope and format.** The manuscript is structured as a Technical Note (~4,000 words, 4 figures, 4 tables). The case study is based on Virtual Vet, an 11-organ canine cardiovascular simulation platform. All results are reproducible from open-source code and data (https://github.com/ningjie333/virtual-vet).

**Prior publication.** This work has not been published previously and is not under consideration elsewhere. All authors have approved the manuscript and agree with its submission.

We believe this paper will be of interest to the SIMULATION readership as a cautionary tale with practical detection strategies for a class of numerical errors that standard verification methods miss.

Sincerely,

[Author Name]
[Institution]
[Email]
