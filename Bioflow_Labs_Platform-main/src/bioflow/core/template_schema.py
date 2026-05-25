# JSON Schema (Draft 2020-12) for BioFlow Template v2.0 (Phase 4.1 shape)
TEMPLATE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["template_version", "resolved_parameters"],
    "properties": {
        "template_version": {"type": "string", "const": "2.0"},
        "metadata": {"type": "object", "additionalProperties": True},
        "profile": {"type": "object", "additionalProperties": True},
        "clinical_reference": {"type": "object", "additionalProperties": True},

        "resolved_parameters": {
            "type": "object",
            "additionalProperties": False,
            "required": ["total_blood_volume_ml", "beds", "pump", "compartments"],
            "properties": {
                "total_blood_volume_ml": {"type": "number", "exclusiveMinimum": 0},
                "posture": {"type": "string", "enum": ["supine", "standing"]},
                "vascular_tone_factor": {
                    "type": "number",
                    "default": 1.0,
                    "minimum": 0.2,
                    "maximum": 5.0,
                    "description": "Global resistance multiplier. R_eff = R * vascular_tone_factor. 1.0 = neutral."
                },
                "blood_volume_factor": {
                    "type": "number",
                    "minimum": 0.5,
                    "maximum": 1.5,
                },
                "posture": {
                    "type": "string",
                    "enum": ["supine", "standing"]
                },
                "pooling_bias_enabled": {"type": "boolean"},


                "baseline": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["P_art_mmHg", "P_ven_mmHg"],
                    "properties": {
                        "P_art_mmHg": {"type": "number"},
                        "P_ven_mmHg": {"type": "number"},
                    },
                },

                # NEW Phase 4.1
                "pump": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["Q_ml_per_s"],
                    "properties": {
                        "Q_ml_per_s": {"type": "number", "minimum": 0},
                    },
                },

                # NEW Phase 4.1
                "compartments": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["arterial", "venous"],
                    "properties": {
                        "arterial": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["C_ml_per_mmHg", "V0_ml"],
                            "properties": {
                                "C_ml_per_mmHg": {"type": "number", "exclusiveMinimum": 0},
                                "V0_ml": {"type": "number", "minimum": 0},
                            },
                        },
                        "venous": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["C_ml_per_mmHg", "V0_ml"],
                            "properties": {
                                "C_ml_per_mmHg": {"type": "number", "exclusiveMinimum": 0},
                                "V0_ml": {"type": "number", "minimum": 0},
                            },
                        },
                    },
                },

                "beds": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["bed_id", "R_mmHg_s_per_ml"],
                        "properties": {
                            "bed_id": {"type": "string", "minLength": 1},
                            "R_mmHg_s_per_ml": {"type": "number", "exclusiveMinimum": 0},
                            "C_ml_per_mmHg": {"type": "number", "exclusiveMinimum": 0},
                            "unstressed_volume_ml": {"type": "number", "minimum": 0},
                            "pooling_bias": {"type": "number", "minimum": 0.0, "maximum": 10.0},
                        },
                    },
                },
            },
        },

        # UPDATED Phase 4.1
        "initial_state": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "P_art_mmHg": {"type": "number"},
                "P_ven_mmHg": {"type": "number"},
                "V_art_ml": {"type": "number", "minimum": 0},
                "V_ven_ml": {"type": "number", "minimum": 0},
            },
        },
    },
}


# Examples ----------------------------------------------------------------
"""
Valid BioFlow Template Examples — Phase 4
========================================

These examples match the Phase 4 contract exactly.

Key rules:
- Beds live under resolved_parameters.beds
- bed_id + R_mmHg_s_per_ml are required
- Pressures use *_mmHg
- Compliance/volume fields are optional and ignored in Phase 4.0
- metadata / profile / clinical_reference are annotation-only

------------------------------------------------------------

Example 1 — Minimal Valid Template
---------------------------------
Smallest runnable template for Phase 4 algebraic flow.
Good for smoke tests.

{
  "template_version": "2.0",
  "resolved_parameters": {
    "total_blood_volume_ml": 5000,
    "beds": [
      {
        "bed_id": "brain",
        "R_mmHg_s_per_ml": 1.0
      }
    ]
  }
}

------------------------------------------------------------

Example 2 — Baseline Physiological Template
-------------------------------------------
Typical multi-bed adult baseline with pressures defined
for perfusion normalization.

{
  "template_version": "2.0",
  "resolved_parameters": {
    "total_blood_volume_ml": 5000,
    "posture": "supine",
    "baseline": {
      "P_art_mmHg": 95.0,
      "P_ven_mmHg": 5.0
    },
    "beds": [
      {
        "bed_id": "brain",
        "R_mmHg_s_per_ml": 1.2,
        "C_ml_per_mmHg": 2.0,
        "unstressed_volume_ml": 200
      },
      {
        "bed_id": "kidney",
        "R_mmHg_s_per_ml": 1.5,
        "C_ml_per_mmHg": 2.5,
        "unstressed_volume_ml": 250
      },
      {
        "bed_id": "muscle",
        "R_mmHg_s_per_ml": 2.0,
        "C_ml_per_mmHg": 4.0,
        "unstressed_volume_ml": 600,
        "pooling_bias": 0.3
      }
    ]
  },
  "initial_state": {
    "P_art_mmHg": 95.0,
    "P_ven_mmHg": 5.0
  }
}

------------------------------------------------------------

Example 3 — Standing Posture Variant
------------------------------------
Same structure, different posture and resistance profile.
Useful for Phase 5 extensions.

{
  "template_version": "2.0",
  "resolved_parameters": {
    "total_blood_volume_ml": 5000,
    "posture": "standing",
    "baseline": {
      "P_art_mmHg": 90.0,
      "P_ven_mmHg": 4.0
    },
    "beds": [
      {
        "bed_id": "brain",
        "R_mmHg_s_per_ml": 1.4,
        "C_ml_per_mmHg": 1.8,
        "unstressed_volume_ml": 180
      },
      {
        "bed_id": "splanchnic",
        "R_mmHg_s_per_ml": 1.8,
        "C_ml_per_mmHg": 5.0,
        "unstressed_volume_ml": 900,
        "pooling_bias": 0.6
      }
    ]
  }
}

------------------------------------------------------------

Example 4 — Fully Annotated Template
------------------------------------
Includes metadata, profile, and clinical_reference.
These fields are ignored by the engine and exist only
for documentation, provenance, or tooling.

{
  "template_version": "2.0",
  "metadata": {
    "name": "Young Athlete Baseline",
    "author": "Lilly",
    "created_utc": "2025-12-20T00:00:00Z"
  },
  "profile": {
    "age_years": 25,
    "sex": "M",
    "notes": "Annotation only; engine ignores this block."
  },
  "resolved_parameters": {
    "total_blood_volume_ml": 5400,
    "posture": "supine",
    "baseline": {
      "P_art_mmHg": 100.0,
      "P_ven_mmHg": 6.0
    },
    "beds": [
      {
        "bed_id": "brain",
        "R_mmHg_s_per_ml": 1.1,
        "C_ml_per_mmHg": 2.2,
        "unstressed_volume_ml": 200
      },
      {
        "bed_id": "kidney",
        "R_mmHg_s_per_ml": 1.4,
        "C_ml_per_mmHg": 2.6,
        "unstressed_volume_ml": 260
      },
      {
        "bed_id": "muscle",
        "R_mmHg_s_per_ml": 1.7,
        "C_ml_per_mmHg": 4.5,
        "unstressed_volume_ml": 700,
        "pooling_bias": 0.2
      }
    ]
  },
  "initial_state": {
    "P_art_mmHg": 100.0,
    "P_ven_mmHg": 6.0
  },
  "clinical_reference": {
    "notes": "Free-form annotations permitted by schema."
  }
}

------------------------------------------------------------

Phase notes:
- Phase 4.0 uses only pressures + resistance
- Compliance and volumes activate in Phase 4.1+
- Determinism and conservation remain mandatory
"""
