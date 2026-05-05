"""
Virtual Creature - 虚拟生物仿真平台
主入口：运行仿真 + 生成可视化图表
"""

import sys
import os

# 入口文件保留 sys.path 注入，确保 src/ 下的模块可导入
# TODO: 迁移到 pyproject.toml editable install 后移除
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from simulation import VirtualCreature
from parameters import TOTAL_BLOOD_VOLUME_ML, T_MAX_MINUTES

# ============================================================
# 如果安装了 matplotlib，会生成图表
# ============================================================
try:
    import matplotlib
    matplotlib.use('Agg')  # 无头模式，不弹出窗口
    import matplotlib.pyplot as plt
    import numpy as np
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False


def run_all_scenarios():
    """运行所有预设场景并生成对比图表"""
    scenarios = {
        "正常稳态": {"blood_loss_ml": 0, "fluid_ml": 0},
        "失血200mL": {"blood_loss_ml": 200, "fluid_ml": 0},
        "失血+输液": {"blood_loss_ml": 200, "fluid_ml": 300},
    }

    results = {}

    for name, cfg in scenarios.items():
        print(f"\n>>> 场景：{name}")
        vc = VirtualCreature(body_weight_kg=20.0)

        if cfg["blood_loss_ml"] > 0:
            vc.schedule_event(60.0, "blood_loss", {"volume_ml": cfg["blood_loss_ml"]})
        if cfg["fluid_ml"] > 0:
            vc.schedule_event(180.0, "fluid_infusion", {"volume_ml": cfg["fluid_ml"]})

        vc.simulate(duration_minutes=T_MAX_MINUTES, verbose=False)

        results[name] = {
            "time_s": vc.history["time_s"],
            "HR": vc.history["HR_bpm"],
            "MAP": vc.history["MAP_mmHg"],
            "CO": vc.history["CO_ml_min"],
            "RR": vc.history["RR"],
            "GFR": vc.history["GFR"],
            "urine": vc.history["urine_ml_min"],
            "BV": vc.history["blood_volume_ml"],
            "sat": vc.history["saturation"],
            "BUN": vc.history["BUN"],
            "pH": vc.history["pH"],
        }

        print(f"  最终 HR={vc.history['HR_bpm'][-1]:.0f} bpm, "
              f"MAP={vc.history['MAP_mmHg'][-1]:.1f} mmHg, "
              f"BV={vc.history['blood_volume_ml'][-1]:.0f} mL")

    return results


def plot_results(results: dict):
    """绘制仿真结果图表"""
    if not HAS_MATPLOTLIB:
        print("\n[提示] 未安装 matplotlib，无法生成图表。")
        print("  运行: pip install matplotlib numpy")
        return

    output_dir = os.path.join(os.path.dirname(__file__), "results")
    os.makedirs(output_dir, exist_ok=True)

    # 图1: 心血管系统
    fig, axes = plt.subplots(2, 2, figsize=(14, 8))
    fig.suptitle("Virtual Creature - Cardiovascular System", fontsize=14, fontweight='bold')

    colors = ['#2196F3', '#F44336', '#4CAF50']
    labels = list(results.keys())

    # 心率
    ax = axes[0, 0]
    for i, (name, data) in enumerate(results.items()):
        ax.plot(data["time_s"], data["HR"], color=colors[i], label=name, linewidth=1.5)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Heart Rate (bpm)")
    ax.set_title("Heart Rate")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # 平均动脉压
    ax = axes[0, 1]
    for i, (name, data) in enumerate(results.items()):
        ax.plot(data["time_s"], data["MAP"], color=colors[i], label=name, linewidth=1.5)
    ax.axhline(y=100, color='gray', linestyle='--', alpha=0.5, label='Normal MAP')
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("MAP (mmHg)")
    ax.set_title("Mean Arterial Pressure")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # 心输出量
    ax = axes[1, 0]
    for i, (name, data) in enumerate(results.items()):
        ax.plot(data["time_s"], data["CO"], color=colors[i], label=name, linewidth=1.5)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Cardiac Output (mL/min)")
    ax.set_title("Cardiac Output")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # 血容量
    ax = axes[1, 1]
    for i, (name, data) in enumerate(results.items()):
        ax.plot(data["time_s"], data["BV"], color=colors[i], label=name, linewidth=1.5)
    ax.axhline(y=TOTAL_BLOOD_VOLUME_ML, color='gray', linestyle='--', alpha=0.5, label='Normal BV')
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Blood Volume (mL)")
    ax.set_title("Blood Volume")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    fig.savefig(os.path.join(output_dir, "cardiovascular.png"), dpi=150)
    print(f"\n图表已保存: {output_dir}\\cardiovascular.png")

    # 图2: 呼吸 + 肾脏系统
    fig, axes = plt.subplots(2, 2, figsize=(14, 8))
    fig.suptitle("Virtual Creature - Respiratory & Renal System", fontsize=14, fontweight='bold')

    # 呼吸频率
    ax = axes[0, 0]
    for i, (name, data) in enumerate(results.items()):
        ax.plot(data["time_s"], data["RR"], color=colors[i], label=name, linewidth=1.5)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Respiratory Rate (/min)")
    ax.set_title("Respiratory Rate")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # GFR
    ax = axes[0, 1]
    for i, (name, data) in enumerate(results.items()):
        ax.plot(data["time_s"], data["GFR"], color=colors[i], label=name, linewidth=1.5)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("GFR (mL/min)")
    ax.set_title("Glomerular Filtration Rate")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # 血氧饱和度
    ax = axes[1, 0]
    for i, (name, data) in enumerate(results.items()):
        ax.plot(data["time_s"], [s * 100 for s in data["sat"]], color=colors[i], label=name, linewidth=1.5)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Arterial O2 Saturation (%)")
    ax.set_title("Arterial Oxygen Saturation")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # 尿量
    ax = axes[1, 1]
    for i, (name, data) in enumerate(results.items()):
        ax.plot(data["time_s"], data["urine"], color=colors[i], label=name, linewidth=1.5)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Urine Output (mL/min)")
    ax.set_title("Urine Output")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    fig.savefig(os.path.join(output_dir, "respiratory_renal.png"), dpi=150)
    print(f"图表已保存: {output_dir}\\respiratory_renal.png")

    # 图3: 系统耦合概览（单一场景）
    fig, axes = plt.subplots(3, 2, figsize=(14, 10))
    fig.suptitle("Normal State - Multi-System Coupling Overview", fontsize=14, fontweight='bold')

    data = results["正常稳态"]

    metrics = [
        ("Heart Rate (bpm)", data["HR"]),
        ("MAP (mmHg)", data["MAP"]),
        ("Respiratory Rate (/min)", data["RR"]),
        ("GFR (mL/min)", data["GFR"]),
        ("Blood Volume (mL)", data["BV"]),
        ("pH", data["pH"]),
    ]

    for idx, (title, values) in enumerate(metrics):
        row, col = divmod(idx, 2)
        ax = axes[row, col]
        ax.plot(data["time_s"], values, color='#2196F3', linewidth=1.5)
        ax.set_xlabel("Time (s)")
        ax.set_ylabel(title)
        ax.set_title(title)
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    fig.savefig(os.path.join(output_dir, "normal_overview.png"), dpi=150)
    print(f"图表已保存: {output_dir}\\normal_overview.png")

    print(f"\n所有图表已保存至: {output_dir}/")


def interactive_demo():
    """交互式演示"""
    print("\n" + "=" * 60)
    print("  Virtual Creature - 虚拟生物仿真平台")
    print("=" * 60)

    vc = VirtualCreature(body_weight_kg=20.0)
    print(f"\n初始状态（正常稳态）：")
    vc.print_summary()

    # 场景选择
    print("\n请选择一个场景：")
    print("  1. 正常稳态（观察 10 分钟）")
    print("  2. 急性失血（1min 后失血 200mL）")
    print("  3. 失血 + 输液复苏（1min 失血，3min 输液 300mL）")
    print("  4. 脱水模拟（血容量下降 5%）")
    print("  5. 运行所有场景对比")
    choice = input("\n请输入选项 [1-5]: ").strip()

    if choice == "1":
        vc.simulate(T_MAX_MINUTES, verbose=False)
        vc.print_summary()
        plot_results({"正常稳态": {
            "time_s": vc.history["time_s"], "HR": vc.history["HR_bpm"],
            "MAP": vc.history["MAP_mmHg"], "CO": vc.history["CO_ml_min"],
            "RR": vc.history["RR"], "GFR": vc.history["GFR"],
            "urine": vc.history["urine_ml_min"], "BV": vc.history["blood_volume_ml"],
            "sat": vc.history["saturation"], "BUN": vc.history["BUN"],
            "pH": vc.history["pH"],
        }}) if HAS_MATPLOTLIB else None

    elif choice == "2":
        vc.schedule_event(60.0, "blood_loss", {"volume_ml": 200.0})
        vc.simulate(T_MAX_MINUTES, verbose=False)
        vc.print_summary()
        vc.run_scenario("blood_loss") if HAS_MATPLOTLIB else vc.print_summary()

    elif choice == "3":
        vc.schedule_event(60.0, "blood_loss", {"volume_ml": 200.0})
        vc.schedule_event(180.0, "fluid_infusion", {"volume_ml": 300.0, "type": "saline"})
        vc.simulate(T_MAX_MINUTES, verbose=False)
        vc.print_summary()

    elif choice == "4":
        vc.schedule_event(10.0, "blood_loss", {"volume_ml": TOTAL_BLOOD_VOLUME_ML * 0.05})
        vc.simulate(T_MAX_MINUTES, verbose=False)
        vc.print_summary()

    elif choice == "5":
        results = run_all_scenarios()
        if HAS_MATPLOTLIB:
            plot_results(results)
        print("\n✅ 仿真完成")

    else:
        print("无效选项")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--auto":
        # 自动模式（无图表，直接输出）
        results = run_all_scenarios()
    else:
        interactive_demo()
