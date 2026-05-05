"""
虚拟生物 CLI 守护进程
终端自治运行，持续仿真 + 定时输出状态

用法:
  python cli_daemon.py --scenario normal --duration 60 --interval 10
  python cli_daemon.py --scenario blood_loss_200 --duration 120 --interval 5
  python cli_daemon.py --scenario dehydration --duration 90 --interval 10 --verbose
  python cli_daemon.py --scenario blood_loss_resuscitation --duration 180 --interval 10
"""

import argparse
import sys
import os
import time
import signal

# 添加 src 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
sys.path.insert(0, os.path.dirname(__file__))

from simulation import VirtualCreature
from parameters import (
    total_blood_volume_ml, T_MAX_MINUTES,
    HEART_RATE_REST_BPM, MEAN_ARTERIAL_PRESSURE_MMHG,
    DT_SECONDS
)


# ============================================================
# 场景定义（与 gui_app.py 保持一致）
# ============================================================
SCENARIOS = {
    "normal": {
        "label": "正常稳态",
        "label_en": "Normal Steady State",
        "events": [],
        "color": "\033[36m",   # 青色
    },
    "blood_loss_100": {
        "label": "轻度失血 100mL",
        "label_en": "Mild Blood Loss",
        "events": [{"t": 60.0, "type": "blood_loss", "vol": 100}],
        "color": "\033[33m",   # 黄色
    },
    "blood_loss_200": {
        "label": "中度失血 200mL",
        "label_en": "Moderate Blood Loss",
        "events": [{"t": 60.0, "type": "blood_loss", "vol": 200}],
        "color": "\033[35m",   # 紫色
    },
    "blood_loss_resuscitation": {
        "label": "失血 + 输液复苏",
        "label_en": "Blood Loss + IV Resuscitation",
        "events": [
            {"t": 60.0, "type": "blood_loss", "vol": 200},
            {"t": 180.0, "type": "fluid_infusion", "vol": 300},
        ],
        "color": "\033[33m",   # 橙色
    },
    "dehydration": {
        "label": "脱水模拟",
        "label_en": "Dehydration",
        "events": [{"t": 10.0, "type": "blood_loss", "vol": total_blood_volume_ml(20.0) * 0.05}],
        "color": "\033[34m",   # 蓝色
    },
    "cocaine": {
        "label": "可卡因中毒 3mg/kg",
        "label_en": "Cocaine 3 mg/kg IV (Liu 1993)",
        "events": [{"t": 30.0, "type": "cocaine", "dose_mg_kg": 3.0}],
        "color": "\033[31m",   # 红色
    },
    "cocaine_high": {
        "label": "可卡因高剂量 6mg/kg",
        "label_en": "Cocaine 6 mg/kg IV",
        "events": [{"t": 30.0, "type": "cocaine", "dose_mg_kg": 6.0}],
        "color": "\033[31m",   # 红色
    },
}

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

# 正常范围（用于状态判断）
NORMAL_RANGES = {
    "HR_bpm":        (60, 180),
    "MAP_mmHg":      (90, 120),
    "CO_ml_min":     (1200, 2200),
    "blood_volume_ml": (5500, 6500),
    "saturation":    (0.95, 1.0),
    "RR":            (10, 30),
    "GFR":           (50, 70),
    "urine_ml_min":  (0.2, 1.0),
    "BUN":           (8, 25),
    "pH":            (7.35, 7.45),
}

HISTORY_METRICS = [
    "HR_bpm", "MAP_mmHg", "CO_ml_min", "blood_volume_ml",
    "saturation", "RR", "GFR", "urine_ml_min", "BUN", "pH"
]

# 可卡因场景专用指标
COCAINE_METRICS = [
    "HR_bpm", "MAP_mmHg", "CO_ml_min", "contractility_factor", "svr_factor",
    "saturation", "GFR", "pH"
]


# ============================================================
# 工具函数
# ============================================================

def status_color(value: float, key: str) -> str:
    """根据正常范围返回状态颜色"""
    if key not in NORMAL_RANGES:
        return RESET
    lo, hi = NORMAL_RANGES[key]
    if isinstance(lo, float) and key in ("saturation",):
        if value < lo:
            return "\033[31m"   # 红色：偏低
        elif value > hi:
            return "\033[34m"  # 蓝色：偏高（血氧一般不会）
        return "\033[32m"       # 绿色
    elif isinstance(lo, float) and key == "pH":
        if value < lo:
            return "\033[33m"   # 黄：偏酸
        elif value > hi:
            return "\033[36m"   # 青：偏碱
        return "\033[32m"
    elif key == "urine_ml_min":
        if value < lo:
            return "\033[33m"   # 黄：少尿
        elif value > hi:
            return "\033[34m"   # 蓝：多尿
        return "\033[32m"
    elif key == "BUN":
        if value > hi:
            return "\033[31m"   # 红：高氮质血症
        elif value > hi * 0.8:
            return "\033[33m"   # 黄：临界
        return "\033[32m"
    else:
        if value < lo:
            return "\033[31m"
        elif value > hi:
            return "\033[35m"
        return "\033[32m"


def format_value(key: str, value: float) -> str:
    """格式化指标值"""
    if key == "saturation":
        return f"{value * 100:.1f}%"
    elif key == "pH":
        return f"{value:.3f}"
    elif key == "blood_volume_ml":
        return f"{value:.0f} mL"
    elif key == "CO_ml_min":
        return f"{value:.0f} mL/min"
    elif key == "GFR":
        return f"{value:.1f} mL/min"
    elif key == "urine_ml_min":
        return f"{value:.3f} mL/min"
    elif key == "BUN":
        return f"{value:.1f} mg/dL"
    else:
        return f"{value:.1f}"


def format_row(key: str, value: float, unit: str) -> str:
    """生成带颜色的状态行"""
    c = status_color(value, key)
    names = {
        "HR_bpm": "心率 HR",
        "MAP_mmHg": "平均动脉压 MAP",
        "CO_ml_min": "心输出量 CO",
        "blood_volume_ml": "循环血量 BV",
        "saturation": "血氧饱和度 SaO₂",
        "RR": "呼吸频率 RR",
        "GFR": "肾小球滤过率 GFR",
        "urine_ml_min": "尿量 Urine",
        "BUN": "血尿素氮 BUN",
        "pH": "动脉血 pH",
    }
    name = names.get(key, key)
    lo, hi = NORMAL_RANGES.get(key, (None, None))
    range_str = ""
    if lo is not None and hi is not None:
        if isinstance(lo, float) and key in ("saturation",):
            range_str = f"  [{lo*100:.0f}–{hi*100:.0f}%]"
        elif isinstance(lo, float) and key == "pH":
            range_str = f"  [{lo:.2f}–{hi:.2f}]"
        elif key == "urine_ml_min":
            range_str = f"  [{lo:.1f}–{hi:.1f}]"
        elif key == "BUN":
            range_str = f"  [{lo:.0f}–{hi:.0f}]"
        else:
            range_str = f"  [{lo:.0f}–{hi:.0f}]"

    val_str = format_value(key, value)
    return f"  {BOLD}{name:22s}{RESET} {c}{val_str:>12s}{RESET}{range_str}"


def print_header(t_min: float, scenario_label: str, scenario_color: str):
    """打印表头"""
    t_sec = t_min * 60
    print(f"\n{scenario_color}{BOLD}{'─' * 62}{RESET}")
    print(f"{scenario_color}{BOLD}  {scenario_label}  |  t = {t_min:6.1f} min ({t_sec:7.1f} s){RESET}")
    print(f"{scenario_color}{'─' * 62}{RESET}")
    # 列头
    print(f"  {'指标':22s} {'当前值':>14s}  {'正常范围'}")
    print(f"  {'─' * 22}  {'─' * 14}  {'─' * 20}")


def print_snapshot(history: dict, t_min: float, scenario_color: str, scenario_label: str, cocaine_mode: bool = False):
    """打印当前时刻的快照"""
    t_s = history["time_s"]
    # 找最近的时间点
    if not t_s:
        return
    idx = -1

    metrics = COCAINE_METRICS if cocaine_mode else HISTORY_METRICS
    print_header(t_min, scenario_label, scenario_color)
    for key in metrics:
        if key in history and len(history[key]) > 0:
            v = history[key][idx]
            print(format_row(key, v, ""))
    print()


def plot_history(history: dict):
    """用 ASCII 图打印趋势（最近 60 秒）"""
    t_s = history["time_s"]
    if len(t_s) < 2:
        return

    print(f"{DIM}  最近趋势（最近 {min(60, t_s[-1]/60):.0f} min）{RESET}")
    print()

    for key in ["MAP_mmHg", "HR_bpm", "GFR", "pH"]:
        if key not in history or len(history[key]) < 2:
            continue
        vals = history[key]
        # 截取最后 60 个点
        window = min(60, len(vals))
        v_slice = vals[-window:]
        t_slice = t_s[-window:]

        lo, hi = NORMAL_RANGES.get(key, (None, None))
        all_vals = v_slice
        v_min = min(all_vals)
        v_max = max(all_vals)
        rng = v_max - v_min if v_max != v_min else 1

        names = {
            "MAP_mmHg": "MAP",
            "HR_bpm": "HR",
            "GFR": "GFR",
            "pH": "pH",
        }
        name = names.get(key, key)

        # ASCII bar chart
        n_bars = 40
        bars = ""
        for v in v_slice:
            norm = (v - v_min) / rng
            filled = int(norm * n_bars)
            bars += "\033[32m█\033[0m" + "\033[32m" + "▓" * filled + RESET

        # 正常范围标记
        range_markers = ""
        if lo is not None and hi is not None:
            if v_min < lo:
                range_markers += f" \033[31m↓ below {lo}\033[0m"
            if v_max > hi:
                range_markers += f" \033[35m↑ above {hi}\033[0m"

        # 趋势箭头
        if v_slice[-1] > v_slice[0]:
            arrow = "\033[31m↑\033[0m"
        elif v_slice[-1] < v_slice[0]:
            arrow = "\033[34m↓\033[0m"
        else:
            arrow = "\033[32m→\033[0m"

        print(f"  {BOLD}{name:>6s}{RESET}  [{v_slice[0]:.1f} {arrow} {v_slice[-1]:.1f}]{range_markers}")

    print()


def running_bar(progress: float, width: int = 40) -> str:
    """进度条"""
    filled = int(progress * width)
    return "\033[32m" + "█" * filled + "\033[0m" + "░" * (width - filled)


# ============================================================
# 主程序
# ============================================================

def run_daemon(
    scenario_key: str,
    duration_minutes: float,
    interval_seconds: int = 10,
    body_weight_kg: float = 20.0,
    verbose: bool = False,
    ascii_plot: bool = True,
):
    """
    守护进程主循环

    Args:
        scenario_key: 场景键名
        duration_minutes: 仿真总时长（分钟）
        interval_seconds: 状态输出间隔（秒）
        body_weight_kg: 体重（kg）
        verbose: 打印详细步进信息
        ascii_plot: 打印 ASCII 趋势图
    """
    if scenario_key not in SCENARIOS:
        print(f"错误：未知场景 '{scenario_key}'")
        print(f"可用场景：{', '.join(SCENARIOS.keys())}")
        sys.exit(1)

    cfg = SCENARIOS[scenario_key]
    scenario_color = cfg["color"]

    # 创建虚拟生物
    vc = VirtualCreature(body_weight_kg=body_weight_kg)

    # 注册事件
    for ev in cfg["events"]:
        if ev["type"] == "cocaine":
            vc.schedule_event(ev["t"], ev["type"], {"dose_mg_kg": ev["dose_mg_kg"]})
        else:
            vc.schedule_event(ev["t"], ev["type"], {"volume_ml": ev.get("vol", 0)})

    # 事件日志（用于提示）
    event_times = {ev["t"] for ev in cfg["events"]}
    announced_events = set()

    # 仿真参数
    total_steps = int(duration_minutes * 60.0 / DT_SECONDS)
    report_interval = int(interval_seconds / DT_SECONDS)
    last_report_time_s = -999.0

    print(f"\n{scenario_color}{BOLD}{'═' * 62}{RESET}")
    print(f"{scenario_color}{BOLD}  虚拟生物 CLI 守护进程{RESET}")
    print(f"{scenario_color}{BOLD}  场景：{cfg['label']} ({cfg['label_en']}){RESET}")
    print(f"{scenario_color}{BOLD}  时长：{duration_minutes:.0f} min  间隔：{interval_seconds}s{RESET}")
    print(f"{scenario_color}{BOLD}  体重：{body_weight_kg:.1f} kg{RESET}")
    print(f"{scenario_color}{'═' * 62}{RESET}")

    if cfg["events"]:
        print(f"\n{scenario_color}  事件计划：{RESET}")
        for ev in cfg["events"]:
            if ev["type"] == "blood_loss":
                print(f"{scenario_color}    t = {ev['t']/60:.1f} min  →  失血 {ev.get('vol', 0):.0f} mL{RESET}")
            elif ev["type"] == "fluid_infusion":
                print(f"{scenario_color}    t = {ev['t']/60:.1f} min  →  输液 {ev.get('vol', 0):.0f} mL{RESET}")
            elif ev["type"] == "cocaine":
                print(f"{scenario_color}    t = {ev['t']/60:.1f} min  →  可卡因 {ev.get('dose_mg_kg', 3.0):.1f} mg/kg IV{RESET}")
    print()

    # 键盘中断标志
    interrupted = False

    def handle_interrupt(signum, frame):
        nonlocal interrupted
        interrupted = True
        print(f"\n{DIM}  [接收到中断信号，正在优雅停止...] {RESET}")

    old_handler = signal.signal(signal.SIGINT, handle_interrupt)
    old_handler_windows = signal.signal(signal.SIGBREAK, handle_interrupt)

    try:
        for step in range(total_steps):
            # 执行一步
            vc.step()

            # 检查是否到达事件时间（未在 step 内处理的）
            t = vc.current_time_s
            for ev_t in event_times:
                if abs(t - ev_t) < DT_SECONDS / 2 and ev_t not in announced_events:
                    announced_events.add(ev_t)
                    ev_data = next(e for e in cfg["events"] if e["t"] == ev_t)
                    if ev_data["type"] == "blood_loss":
                        print(f"\n{scenario_color}{BOLD}  ⚡ 事件 @ t={t/60:.1f} min  →  失血 {ev_data.get('vol', 0):.0f} mL{RESET}\n")
                    elif ev_data["type"] == "fluid_infusion":
                        print(f"\n{scenario_color}{BOLD}  ⚡ 事件 @ t={t/60:.1f} min  →  输液 {ev_data.get('vol', 0):.0f} mL{RESET}\n")
                    elif ev_data["type"] == "cocaine":
                        print(f"\n{scenario_color}{BOLD}  ⚡ 事件 @ t={t/60:.1f} min  →  可卡因 {ev_data.get('dose_mg_kg', 3.0):.1f} mg/kg IV{RESET}\n")

            # 定时报告
            if step % report_interval == 0 or step == total_steps - 1:
                t_min = t / 60.0
                progress = step / total_steps

                # 进度条
                bar = running_bar(progress, 50)
                print(f"\r{DIM}  进度: {bar} {progress*100:.1f}%  t={t_min:.1f} min{RESET}", end="", flush=True)

                # 详细快照（每整分钟打印一次，或结束时）
                if (step > 0 and step % int(60 / DT_SECONDS) == 0) or step == total_steps - 1 or interrupted:
                    print()  # 换行
                    print_snapshot(vc.history, t_min, scenario_color, cfg["label"],
                                  cocaine_mode=(scenario_key.startswith("cocaine")))

                    # 事件日志
                    if vc.event_log:
                        print(f"  {DIM}事件：{RESET}")
                        for e in vc.event_log[-3:]:
                            print(f"    {DIM}{e}{RESET}")

                    # ASCII 趋势图
                    if ascii_plot:
                        plot_history(vc.history)

                # 打印步进详情
                if verbose and step % 100 == 0:
                    gfr = vc.history["GFR"][-1] if vc.history["GFR"] else 0
                    hr = vc.history["HR_bpm"][-1] if vc.history["HR_bpm"] else 0
                    map_ = vc.history["MAP_mmHg"][-1] if vc.history["MAP_mmHg"] else 0
                    print(f"    {DIM}t={t:.0f}s | HR={hr:.0f} MAP={map_:.1f} GFR={gfr:.1f}{RESET}")

            if interrupted:
                break

    finally:
        signal.signal(signal.SIGINT, old_handler)
        signal.signal(signal.SIGBREAK, old_handler_windows)

    # 最终报告
    t = vc.current_time_s
    t_min = t / 60.0
    print(f"\n{scenario_color}{BOLD}{'═' * 62}{RESET}")
    print(f"{scenario_color}{BOLD}  仿真结束  |  t = {t_min:.1f} min{RESET}")
    print(f"{scenario_color}{'═' * 62}{RESET}\n")
    print_snapshot(vc.history, t_min, scenario_color, cfg["label"])

    # 最终状态摘要
    print(f"  {BOLD}最终事件日志：{RESET}")
    for e in vc.event_log:
        print(f"    {DIM}{e}{RESET}")

    print(f"\n  {BOLD}状态轨迹：{RESET}")
    for key in HISTORY_METRICS:
        if key in vc.history and len(vc.history[key]) > 1:
            vals = vc.history[key]
            start = vals[0]
            end = vals[-1]
            delta = end - start
            c = status_color(end, key)
            sign = "+" if delta >= 0 else ""
            name_map = {
                "HR_bpm": "HR", "MAP_mmHg": "MAP", "CO_ml_min": "CO",
                "blood_volume_ml": "BV", "saturation": "SaO₂", "RR": "RR",
                "GFR": "GFR", "urine_ml_min": "Urine", "BUN": "BUN", "pH": "pH"
            }
            name = name_map.get(key, key)
            print(f"    {name:>8s}: {format_value(key, start):>12s}  →  {c}{format_value(key, end):>12s}{RESET}  ({sign}{format_value(key, delta) if abs(delta) > 0.001 else '0':>8s})")

    print()
    return vc


# ============================================================
# 入口
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="虚拟生物 CLI 守护进程 — 终端自治运行仿真",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python cli_daemon.py --scenario normal --duration 60 --interval 10
  python cli_daemon.py --scenario blood_loss_200 --duration 120 --interval 5
  python cli_daemon.py --scenario dehydration --duration 90 --interval 10 --verbose
  python cli_daemon.py --scenario blood_loss_resuscitation --duration 180 --interval 10 --no-plot

场景列表：normal, blood_loss_100, blood_loss_200, blood_loss_resuscitation, dehydration
        """
    )

    parser.add_argument(
        "--scenario", "-s",
        default="normal",
        help="场景名称 (default: normal)"
    )
    parser.add_argument(
        "--duration", "-d",
        type=float,
        default=10.0,
        help="仿真时长，分钟 (default: 10)"
    )
    parser.add_argument(
        "--interval", "-i",
        type=int,
        default=10,
        help="状态输出间隔，秒 (default: 10)"
    )
    parser.add_argument(
        "--weight", "-w",
        type=float,
        default=20.0,
        help="虚拟生物体重，kg (default: 20)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="打印每步详细信息"
    )
    parser.add_argument(
        "--no-plot",
        action="store_true",
        help="禁用 ASCII 趋势图"
    )

    args = parser.parse_args()

    run_daemon(
        scenario_key=args.scenario,
        duration_minutes=args.duration,
        interval_seconds=args.interval,
        body_weight_kg=args.weight,
        verbose=args.verbose,
        ascii_plot=not args.no_plot,
    )
