"""
Minimal CV Model: Independent heart+neuro 2-module system to reproduce O(1) bias.
Verifies that bias is NOT a VirtualCreature-specific artifact, but a general property
of sequential Gauss-Seidel coupling with the baroreflex loop.

Architecture:
  heart: _baroreceptor_feedback(MAP, dt) -> HR, SVR update
  neuro: FactorCommands -> multiplicative SVR/HR modification

Two orderings:
  heart→neuro: heart.compute() FIRST -> raw_MAP ≈ 88.3 -> error≈+0.117 -> HR climbs
  neuro→heart: neuro.compute() FIRST -> reads filtered_MAP=100.0 -> error≈0 -> HR stays
"""
import os, sys, types, numpy as np

EXPERIMENTS_DIR = 'experiments'
PROJECT_ROOT = os.path.dirname(os.path.abspath(EXPERIMENTS_DIR))
SRC_DIR = os.path.join(PROJECT_ROOT, 'src')
sys.path.insert(0, SRC_DIR)

def _read_patched(path):
    src = open(path, encoding='utf-8').read()
    # Replace 'from src.' and 'import src.' prefixes so standalone loading works
    src = src.replace('from src.', 'from ')
    src = src.replace('import src.', 'import ')
    return src

# Load modules standalone (same pattern as check_order_swap.py)
for _name in ['parameters', 'blood', 'fluid', 'cardiac_electrophysiology', 'noble_purkinje',
    'respiratory_rhythm', 'heart', 'lung', 'kidney', 'gut', 'liver',
    'endocrine', 'neuro', 'immune', 'coagulation', 'lymphatic',
    'lifecycle', 'toxicology', 'organ_health', 'pharmacology', 'simulation']:
    _path = os.path.join(SRC_DIR, f'{_name}.py')
    _src = _read_patched(_path)
    _mod = types.ModuleType(_name)
    sys.modules[_name] = _mod
    exec(compile(_src, _path, 'exec'), _mod.__dict__)

HeartModule = sys.modules['heart'].HeartModule
NeuroModule = sys.modules['neuro'].NeuroModule


# ============================================================
# Minimal blood compartment (only pH and K+ needed)
# ============================================================
class MinimalBlood:
    def __init__(self, weight_kg: float):
        self.total_volume_ml = 86.0 * weight_kg
        self.plasma_fraction = 0.55
        self.arterial_PO2_mmHg = 95.0
        self.arterial_PCO2_mmHg = 40.0
        self.arterial_pH = 7.40
        self.potassium_mEq_L = 4.5


# ============================================================
# Minimal Neuro Module (just enough to issue FactorCommands)
# ============================================================
class MinimalNeuro:
    """Standalone neuro module that issues FactorCommands to heart"""
    def __init__(self):
        self.sympathetic_tone = 0.3
        self.parasympathetic_tone = 0.7

    def compute(self, dt: float, heart_state: dict, lung_state: dict = None) -> dict:
        """neuro.compute() issues HR and SVR FactorCommands based on MAP"""
        map_mmHg = heart_state.get('MAP_mmHg', 100.0)
        hr = heart_state.get('HR', 85.0)
        svr = heart_state.get('SVR', 1.4)

        # Simple sympathetic response to MAP error
        error = (100.0 - map_mmHg) / 100.0  # normalized
        sym_adjust = 0.5 * max(0.0, error)  # only activate when MAP low

        self.sympathetic_tone = min(1.0, self.sympathetic_tone + sym_adjust * dt)
        self.parasympathetic_tone = max(0.0, self.parasympathetic_tone - 0.3 * error * dt)

        # FactorCommands: multiplicative adjustments
        hr_factor = 1.0 + 0.3 * self.sympathetic_tone * max(0.0, error)
        svr_factor = 1.0 + 0.2 * self.sympathetic_tone * max(0.0, error)

        return {
            'factor_commands': [
                {'target': 'heart_rate', 'op': 'multiply', 'value': hr_factor},
                {'target': 'SVR', 'op': 'multiply', 'value': svr_factor},
            ]
        }


# ============================================================
# VC_Minimal: Two orderings, heart→neuro and neuro→heart
# ============================================================
class VC_Minimal_HeartFirst:
    """heart.compute() FIRST → reads raw_MAP≈88.3 at step 1 → error≈+0.117"""
    def __init__(self, weight_kg=20.0):
        self.dt = 0.01
        self.current_time_s = 0.0
        self._step_count = 0
        self._cached_inputs = {}

        self.blood = MinimalBlood(weight_kg)
        self.heart = HeartModule(weight_kg=weight_kg, blood=self.blood)
        self.neuro = MinimalNeuro()

    def step(self):
        dt = self.dt
        self._step_count += 1

        # Toxicology (no-op for minimal)
        svr_factor = 1.0

        # 1. Heart FIRST (drained split analog)
        heart_state = self.heart.compute(dt, svr_factor=svr_factor)

        # 2. Neuro SECOND (reads updated heart state)
        neuro_state = self.neuro.compute(dt, {
            'MAP_mmHg': heart_state['MAP_mmHg'],
            'HR': heart_state['heart_rate_bpm'],
            'SVR': heart_state['SVR'],
        })

        # Apply FactorCommands
        for cmd in neuro_state.get('factor_commands', []):
            if cmd['target'] == 'heart_rate' and cmd['op'] == 'multiply':
                self.heart.heart_rate *= cmd['value']
            elif cmd['target'] == 'SVR' and cmd['op'] == 'multiply':
                self.heart.SVR *= cmd['value']
                self.heart.SVR = min(self.heart.SVR, self.heart.SVR_max)

        self.current_time_s += dt

    def run(self, t_end=60.0):
        n_steps = int(t_end / self.dt)
        recs = []
        for i in range(n_steps + 1):
            if i % 500 == 0:
                recs.append({
                    't': i * self.dt,
                    'MAP': float(self.heart.mean_arterial_pressure),
                    'HR': float(self.heart.heart_rate),
                    'SVR': float(self.heart.SVR),
                    'sym': float(self.heart.sympathetic),
                    'error': float((100.0 - self.heart.mean_arterial_pressure) / 100.0),
                })
            self.step()
        return recs


class VC_Minimal_NeuroFirst:
    """neuro.compute() FIRST → reads filtered_MAP=100.0 at step 1 → error≈0"""
    def __init__(self, weight_kg=20.0):
        self.dt = 0.01
        self.current_time_s = 0.0
        self._step_count = 0
        self._cached_inputs = {}

        self.blood = MinimalBlood(weight_kg)
        self.heart = HeartModule(weight_kg=weight_kg, blood=self.blood)
        self.neuro = MinimalNeuro()

    def step(self):
        dt = self.dt
        self._step_count += 1

        svr_factor = 1.0

        # 1. Neuro FIRST (fixed-strain split analog) - reads OLD MAP
        neuro_state = self.neuro.compute(dt, {
            'MAP_mmHg': self.heart.mean_arterial_pressure,  # STALE MAP
            'HR': self.heart.heart_rate,
            'SVR': self.heart.SVR,
        })

        # Apply FactorCommands to heart BEFORE heart.compute()
        for cmd in neuro_state.get('factor_commands', []):
            if cmd['target'] == 'heart_rate' and cmd['op'] == 'multiply':
                self.heart.heart_rate *= cmd['value']
            elif cmd['target'] == 'SVR' and cmd['op'] == 'multiply':
                self.heart.SVR *= cmd['value']
                self.heart.SVR = min(self.heart.SVR, self.heart.SVR_max)

        # 2. Heart SECOND (reads updated neuro state)
        heart_state = self.heart.compute(dt, svr_factor=svr_factor)

        self.current_time_s += dt

    def run(self, t_end=60.0):
        n_steps = int(t_end / self.dt)
        recs = []
        for i in range(n_steps + 1):
            if i % 500 == 0:
                recs.append({
                    't': i * self.dt,
                    'MAP': float(self.heart.mean_arterial_pressure),
                    'HR': float(self.heart.heart_rate),
                    'SVR': float(self.heart.SVR),
                    'sym': float(self.heart.sympathetic),
                    'error': float((100.0 - self.heart.mean_arterial_pressure) / 100.0),
                })
            self.step()
        return recs


# ============================================================
# Run experiments
# ============================================================
print('=' * 70)
print('MINIMAL CV MODEL: Independent 2-module verification of O(1) bias')
print('=' * 70)

for OrderingClass, name in [(VC_Minimal_HeartFirst, 'heart→neuro'), (VC_Minimal_NeuroFirst, 'neuro→heart')]:
    vc = OrderingClass(weight_kg=20.0)
    recs = vc.run(t_end=60.0)

    print(f'\n=== {name} ===')
    print(f'{"t":>5}  {"MAP":>8}  {"HR":>7}  {"SVR":>8}  {"sym":>6}  {"error":>8}')
    for r in recs:
        print(f'{r["t"]:5.1f}  {r["MAP"]:8.2f}  {r["HR"]:7.2f}  {r["SVR"]:8.4f}  '
              f'{r["sym"]:6.4f}  {r["error"]:8.4f}')

print('\n' + '=' * 70)
print('VERIFICATION CHECK:')
print('  Expected: heart→neuro MAP≈144.7 mmHg, neuro→heart MAP≈100.0 mmHg')
print('  If matches → bias reproduced in minimal model → NOT VirtualCreature-specific')
print('  If differs → bias requires full VirtualCreature context')
print('=' * 70)