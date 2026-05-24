"""
Phase 1: 60分钟器官振荡调查脚本
记录所有关键指标的时间序列，用于定位震荡根因

用法: python tools/investigate_oscillation.py
"""

import os
import sys
import math
import csv
import json
from datetime import datetime

# Use absolute path so it works from any working directory
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")

# src/heart.py uses mixed imports: "from heart import ..." and "from src.cardiac_electrophysiology import ..."
# We need sys.path to find both. Add PROJECT_ROOT (not src/) so "from src.x" works.
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, SRC_DIR)
# Also chdir to src/ so that "from heart import ..." works in heart.py's imports
os.chdir(SRC_DIR)

from simulation import VirtualCreature


def run_investigation():
    creature = VirtualCreature(body_weight_kg=20.0)
    dt = 0.1
    steps_60min = int(60 * 60 / dt)  # 36000 steps

    # 每秒记录一次
    sample_interval = int(1.0 / dt)  # 10 steps
    total_samples = steps_60min // sample_interval  # 3600 samples

    print(f"开始60分钟振荡调查...")
    print(f"总时间步: {steps_60min}, 采样间隔: {sample_interval}步, 总采样数: {total_samples}")
    print(f"每采样点间隔: 1秒, 总时长: {total_samples}秒 = {total_samples/60:.1f}分钟")

    records = []

    for i in range(steps_60min):
        creature.step()

        if i % sample_interval == 0:
            t_sec = i * dt
            sample = sample_creature(creature, t_sec)
            records.append(sample)

            # 每100个采样点（100秒）打印一次进度
            if len(records) % 100 == 0:
                print(f"  t={t_sec:.0f}s ({t_sec/60:.1f}min): "
                      f"HR={sample['HR']:.1f} MAP={sample['MAP']:.1f} "
                      f"RR={sample['respiratory_rate']:.1f} "
                      f"pH={sample['arterial_pH']:.3f} "
                      f"K={sample['potassium']:.2f} "
                      f"blood_vol={sample['blood_volume_ml']:.0f}")

    print(f"\n采样完成，共 {len(records)} 个采样点")

    # 分析数据
    analysis = analyze_records(records)

    # 保存数据
    save_data(records, analysis)

    return records, analysis


def sample_creature(creature, t_sec):
    """采集当前时刻所有指标"""
    h = creature.heart
    lu = creature.lung
    ki = creature.kidney
    bl = creature.blood
    fl = creature.fluid
    en = creature.endocrine
    co = creature.coagulation
    rh = creature.lung._vdp  # Van der Pol oscillator is inside LungModule

    return {
        # 时间
        "t_sec": t_sec,

        # 心血管
        "HR": h.heart_rate,
        "MAP": h.mean_arterial_pressure,
        "CO": h.cardiac_output,
        "SV": h.stroke_volume,
        "SVR": h.SVR,
        "sympathetic": h.sympathetic,
        "parasympathetic": h.parasympathetic,
        "contractility_factor": h.contractility_factor,
        "MAP_error": (h.MAP_target - h.mean_arterial_pressure) / h.MAP_target,

        # 呼吸
        "respiratory_rate": lu.respiratory_rate,
        "PaCO2": bl.arterial_PCO2_mmHg,
        "PaO2": bl.arterial_PO2_mmHg,
        "arterial_pH": bl.arterial_pH,
        "O2_saturation": bl.arterial_saturation,

        # 血液化学
        "glucose": bl.glucose_mmol_L,
        "lactate": bl.lactate_mmol_L,
        "HCO3": fl.vascular_hco3_meq_l if hasattr(fl, 'vascular_hco3_meq_l') else 24.0,
        "potassium": bl.potassium_mEq_L,
        "sodium": bl.sodium_mEq_L,

        # 凝血
        "factor_VII": co.factor_VII,
        "factor_II": co.factor_II,
        "PT_sec": bl.PT_sec,
        "aPTT_sec": bl.aPTT_sec,
        "fibrinogen": co.fibrinogen,
        "coagulation_state": co.coagulation_state,

        # 内分泌
        "cortisol": en.cortisol_ug_dL,
        "T3": en.T3_ng_dL,
        "insulin": en.insulin_uU_mL,
        "glucagon": en.glucagon_pg_mL,
        "HPA_axis": en.HPA_axis if hasattr(en, 'HPA_axis') else 0.0,

        # VdP 振荡器
        "vdp_x": rh.x if hasattr(rh, 'x') else 0.0,
        "vdp_v": rh.v if hasattr(rh, 'v') else 0.0,
        "vdp_omega": rh.omega if hasattr(rh, 'omega') else 0.0,
        "vdp_mu": rh.mu if hasattr(rh, 'mu') else 0.0,
        "chemical_drive": rh.chemical_drive if hasattr(rh, 'chemical_drive') else 0.0,

        # 血容量
        "blood_volume_ml": h.circulating_volume_ml,
        "blood_volume_ratio": h.circulating_volume_ml / h.total_BV,

        # 肾脏
        "GFR": ki.GFR,
        "urine_output": ki.urine_output,
        "BUN": bl.bun_mg_dL,

        # 流体
        "extra_volume_ml": fl.vascular_volume_ml if hasattr(fl, 'vascular_volume_ml') else 0.0,
        "inter_volume_ml": fl.isf_volume_ml if hasattr(fl, 'isf_volume_ml') else 0.0,
        "intra_volume_ml": fl.icf_volume_ml if hasattr(fl, 'icf_volume_ml') else 0.0,
    }


def analyze_records(records):
    """分析记录，检测振荡"""
    print("\n" + "="*60)
    print("振荡分析报告")
    print("="*60)

    # 对每个指标计算统计量
    indicators = [
        ("HR", "心率 bpm"),
        ("MAP", "平均动脉压 mmHg"),
        ("respiratory_rate", "呼吸频率 /min"),
        ("arterial_pH", "动脉pH"),
        ("PaCO2", "动脉CO2分压 mmHg"),
        ("potassium", "血钾 mEq/L"),
        ("blood_volume_ml", "血容量 mL"),
        ("sympathetic", "交感神经活动"),
        ("parasympathetic", "副交感神经活动"),
        ("contractility_factor", "收缩力因子"),
        ("vdp_x", "VdP状态x"),
        ("vdp_omega", "VdP频率 omega"),
        ("chemical_drive", "化学感受器驱动"),
        ("cortisol", "皮质醇 ug/dL"),
        ("T3", "T3 ng/dL"),
        ("glucose", "血糖 mmol/L"),
        ("lactate", "血乳酸 mmol/L"),
    ]

    results = {}
    for key, label in indicators:
        values = [r[key] for r in records]
        mean_val = sum(values) / len(values)
        max_val = max(values)
        min_val = min(values)
        range_val = max_val - min_val
        std_val = math.sqrt(sum((v - mean_val)**2 for v in values) / len(values))

        # 计算振荡周期（峰值检测）
        peaks = 0
        for j in range(1, len(values) - 1):
            if values[j] > values[j-1] and values[j] > values[j+1]:
                peaks += 1

        # 简单振荡检测：range > 2倍标准差 视为显著振荡
        is_oscillating = range_val > 2 * std_val

        results[key] = {
            "mean": mean_val,
            "max": max_val,
            "min": min_val,
            "range": range_val,
            "std": std_val,
            "peaks": peaks,
            "is_oscillating": is_oscillating,
        }

        flag = "⚠️ 振荡" if is_oscillating else "✅ 稳定"
        print(f"{flag} {label:20s}: "
              f"范围[{min_val:.2f}, {max_val:.2f}] "
              f"均值={mean_val:.2f} "
              f"标准差={std_val:.2f} "
              f"峰数={peaks}")

    # 打印振荡最严重的指标
    print("\n--- 振荡幅度排名 (range/std) ---")
    osc_ratios = [(key, results[key]['range'] / max(results[key]['std'], 0.001))
                  for key in results]
    osc_ratios.sort(key=lambda x: x[1], reverse=True)
    for key, ratio in osc_ratios[:8]:
        label = next(l for l, _ in indicators if key == l)
        print(f"  {label}: {ratio:.1f}倍")

    return results


def save_data(records, analysis):
    """保存数据到CSV和JSON"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 保存CSV (absolute path)
    csv_path = os.path.join(PROJECT_ROOT, "tools", f"oscillation_data_{timestamp}.csv")
    if len(records) > 0:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=records[0].keys())
            writer.writeheader()
            writer.writerows(records)
        print(f"\nCSV数据已保存: {csv_path} ({len(records)}行)")

    # 保存分析结果
    json_path = os.path.join(PROJECT_ROOT, "tools", f"oscillation_analysis_{timestamp}.json")
    # 转换 analysis 中的 numpy/numeric types 到 Python types
    analysis_serializable = {}
    for key, val in analysis.items():
        analysis_serializable[key] = {k: float(v) if isinstance(v, (int, float)) else v
                                      for k, v in val.items()}
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(analysis_serializable, f, indent=2, ensure_ascii=False)
    print(f"分析结果已保存: {json_path}")


if __name__ == "__main__":
    records, analysis = run_investigation()