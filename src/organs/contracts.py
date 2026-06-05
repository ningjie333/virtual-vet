"""
Module contracts — Phase 5 architectural refactor.

Each organ module declares its I/O surface as class attributes. The engine
consults these declarations to build a Topology graph (see
`src.engine.topology`).

Why this matters
----------------
Phase 1-4 of the refactor extracted engine-level data structures but did
not constrain how modules communicate. Phase 5 introduces **declared
contracts**: every module says "I read from heart.MAP, I write to
blood.ammonia_umol_L" — written in code, not in a central table.

Phase 6+ can use these declarations to:
  - Auto-derive CONNECTIONS table (eliminate hand-maintained coupling)
  - Validate that the topology is acyclic
  - Generate per-module documentation
  - Stub modules for testing

The contract is **purely declarative**. Adding INPUTS / OUTPUTS class
attributes does NOT change behavior — modules continue to read/write
self.blood.X exactly as before. The bus (Phase 4) and the contract
(Phase 5) work together: the contract is metadata, the bus is the
runtime channel.

Usage
-----
A module declares its I/O via class attributes:

    class LiverModule(ModuleContract):
        INPUTS = ("co_input", "gut_state")
        OUTPUTS = ("glucose_output", "ammonia_umol_L",
                   "albumin_g_dL", "bilirubin_mg_dL")
        READS_BLOOD = ("glucose_mmol_L", "ammonia_umol_L",
                       "amino_acids_g_L", "drug_concentration_mg_kg",
                       "lactate_mmol_L")

    # Engine code:
    bus.register_module("liver", LiverModule.INPUTS,
                        LiverModule.OUTPUTS, LiverModule.READS_BLOOD)

The contract is intentionally a Protocol with class-level attributes —
not an abstract base class. Modules continue to inherit from object
(their current base) without modification.

Reference: HumMod ESL pattern (`<var name="X" mount="Y">` declarations
in module source).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ModuleContract(Protocol):
    """Declares a module's I/O surface.

    Class attributes (set on the implementing class):
      - INPUTS: tuple[str, ...] — names of inputs the module consumes
                (typically resolved via CONNECTIONS or self._cached_inputs)
      - OUTPUTS: tuple[str, ...] — names of outputs the module produces
      - READS_BLOOD: tuple[str, ...] — blood fields the module reads
      - WRITES_BLOOD: tuple[str, ...] — blood fields the module writes
                     (typically empty if the module publishes via bus)

    All four are optional. A module with no declared contract is still
    valid; the topology discovery treats it as a leaf node.
    """

    INPUTS: tuple[str, ...] = ()
    OUTPUTS: tuple[str, ...] = ()
    READS_BLOOD: tuple[str, ...] = ()
    WRITES_BLOOD: tuple[str, ...] = ()


def has_contract(cls: type) -> bool:
    """True if `cls` declares any contract attributes.

    Use this to distinguish modules that opted into declared contracts
    from those that haven't been migrated yet (Phase 5 backwards-compat).
    """
    return any(
        getattr(cls, attr, None)
        for attr in ("INPUTS", "OUTPUTS", "READS_BLOOD", "WRITES_BLOOD")
    )


def collect_contract(cls: type) -> dict:
    """Return the I/O surface of a module class as a dict.

    Returns:
        {
            "inputs": tuple[str, ...],
            "outputs": tuple[str, ...],
            "reads_blood": tuple[str, ...],
            "writes_blood": tuple[str, ...],
        }
    """
    return {
        "inputs": getattr(cls, "INPUTS", ()),
        "outputs": getattr(cls, "OUTPUTS", ()),
        "reads_blood": getattr(cls, "READS_BLOOD", ()),
        "writes_blood": getattr(cls, "WRITES_BLOOD", ()),
    }


# Re-export for convenience
__all__ = [
    "ModuleContract",
    "has_contract",
    "collect_contract",
]
