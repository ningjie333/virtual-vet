"""
诊断：rhs 非确定性 + VdP 游走

T1: rhs 非确定性（diff > 1e-12）
T2: VdP 状态不在 y 向量中的影响
"""
import sys
import os
import time as time_

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(PROJECT_ROOT, "src")
sys.path.insert(0, _SRC_DIR)

import numpy as np

# 加载模块（两遍扫描策略）
import types

def _read_patched(path: str) -> str:
    src = open(path, encoding="utf-8").read()
    return src.replace("from src.", "from ")

sys.modules["parameters"] = types.ModuleType("parameters")
exec(compile(_read_patched(os.path.join(_SRC_DIR, "parameters.py")),
             os.path.join(_SRC_DIR, "parameters.py"), "exec"),
     sys.modules["parameters"].__dict__)

for _name in [
    "blood", "fluid", "cardiac_electrophysiology", "noble_purkinje",
    "respiratory_rhythm", "heart", "lung", "kidney", "gut", "liver",
    "endocrine", "neuro", "immune", "coagulation", "lymphatic",
    "lifecycle", "toxicology", "organ_health", "pharmacology", "simulation",
]:
    _path = os.path.join(_SRC_DIR, f"{_name}.py")
    _src = _read_patched(_path)
    _mod = types.ModuleType(_name)
    sys.modules[_name] = _mod
    exec(compile(_src, _path, "exec"), _mod.__dict__)

VirtualCreature = sys.modules["simulation"].VirtualCreature


print("=" * 60)
print("T1: rhs 非确定性检测（5次调用，检查收敛性）")
print("=" * 60)

vc = VirtualCreature(body_weight_kg=20.0)
y0 = vc._pack_unified_state()

vc._cached_inputs.clear()
d1 = vc._unified_rhs(0.0, y0)
d2 = vc._unified_rhs(0.0, y0)
d3 = vc._unified_rhs(0.0, y0)
d4 = vc._unified_rhs(0.0, y0)
d5 = vc._unified_rhs(0.0, y0)

diff_12 = np.max(np.abs(d1 - d2))
diff_23 = np.max(np.abs(d2 - d3))
diff_34 = np.max(np.abs(d3 - d4))
diff_45 = np.max(np.abs(d4 - d5))

print(f"d1 vs d2: {diff_12:.2e}")
print(f"d2 vs d3: {diff_23:.2e}")
print(f"d3 vs d4: {diff_34:.2e}")
print(f"d4 vs d5: {diff_45:.2e}")

# 最大差异
all_diffs = [diff_12, diff_23, diff_34, diff_45]
max_diff = max(all_diffs)
print(f"最大差异: {max_diff:.2e}")
print(f"T1 结果: {'FAIL (非确定性)' if max_diff > 1e-12 else 'PASS (确定性)'}")

if max_diff > 1e-12:
    # 找出哪个分量差异最大
    max_err = 0
    max_i = 0
    for i in range(len(d1)):
        err = abs(d1[i] - d2[i])
        if err > max_err:
            max_err = err
            max_i = i
    state_map = vc._build_unified_state_map()
    rev_map = {v: k for k, v in state_map.items()}
    mname, vname = rev_map.get(max_i, ("unknown", "unknown"))
    print(f"  最大差异: [{max_i}] {mname}.{vname} = {d1[max_i]:.6e} vs {d2[max_i]:.6e}")


print()
print("=" * 60)
print("T2: VdP 状态不在 y 向量中（检查 state_map）")
print("=" * 60)

vc3 = VirtualCreature(body_weight_kg=20.0)
y0 = vc3._pack_unified_state()
state_map = vc3._build_unified_state_map()

# 列出所有 state_map 条目
print(f"state_map 大小: {len(state_map)}")
print(f"y 向量长度: {len(y0)}")

# 找出 lung 模块的条目
lung_items = [(v, i) for (m, v), i in state_map.items() if m == "lung"]
print(f"Lung 模块条目: {lung_items}")

# 检查 VdP 状态
lung_mod = getattr(vc3, "lung")
vdp = getattr(lung_mod, 'vdp', None) or getattr(lung_mod, '_vdp', None)
if vdp:
    print(f"VdP 对象找到: x={vdp.x:.4f}, v={vdp.v:.4f}")
    print(f"VdP class: {type(vdp).__name__}")
    print(f"VdP rr_rest: {vdp.rr_rest_hz:.4f} Hz")
    # 检查 y 向量里有没有 respiratory 相关的
    resp_items = [(v, i) for (m, v), i in state_map.items() if m == "respiratory"]
    print(f"Respiratory 模块条目: {resp_items}")
else:
    print("VdP 对象未找到")
    # 检查 lung 模块的属性
    print(f"Lung 模块属性: {[a for a in dir(lung_mod) if not a.startswith('_')]}")