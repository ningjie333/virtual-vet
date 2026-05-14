#!/usr/bin/env python3
"""
检查 3+4：JSON 配置文件交叉一致性 + 数据完整性

验证 6 个 data/*.json 文件之间的交叉引用是否合法。
支持 --fix 模式自动修复可自动修复的问题。

退出码: 0=无问题, 1=有 CRITICAL/HIGH, 2=仅有 MEDIUM/LOW
"""

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"

SEVERITY_CRITICAL = "CRITICAL"
SEVERITY_HIGH = "HIGH"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_LOW = "LOW"

# _PARAM_PATHS 中所有合法的 target 前缀（从 simulation.py 提取）
VALID_PARAM_PREFIXES = (
    "heart.",
    "lung.",
    "kidney.",
    "blood.",
    "fluid.",
    "gut.",
    "liver.",
    "endocrine.",
    "neuro.",
    "immune.",
)

# 可自动修复的问题类型
AUTO_FIXABLE_SEVERITIES = {SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM}


def load_json(filename: str):
    path = DATA_DIR / filename
    if not path.exists():
        print(f"[ERROR] 找不到 {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(filename: str, data) -> None:
    path = DATA_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"  [FIX] 已写入 {path}")


# ─── 检查函数 ───────────────────────────────────────────────

def check_cases_to_diseases(cases: dict, diseases: dict, ode_diseases: dict) -> list:
    errors = []
    disease_names = set(diseases.get("disease_names", {}).keys())
    ode_disease_keys = {k for k in ode_diseases.keys() if not k.startswith("_")}
    for case in cases.get("cases", []):
        case_id = case.get("id", "?")
        disease = case.get("disease", "")
        if not disease:
            errors.append({"sev": SEVERITY_HIGH, "msg": f"cases.json:{case_id} → disease 字段为空", "fixable": False})
            continue
        if disease not in disease_names:
            errors.append({"sev": SEVERITY_CRITICAL, "msg": f"cases.json:{case_id} → disease=\"{disease}\" 在 diseases.json.disease_names 中不存在", "fixable": False})
        if disease not in ode_disease_keys:
            errors.append({"sev": SEVERITY_CRITICAL, "msg": f"cases.json:{case_id} → disease=\"{disease}\" 在 ode_diseases.json 中不存在", "fixable": False})
    return errors


def check_disease_clues(diseases: dict, examinations: dict) -> list:
    errors = []
    all_clue_ids = set(diseases.get("clue_descriptions", {}).keys())
    exam_keys = set(examinations.keys())

    for disease_key, clue_ids in diseases.get("clues", {}).items():
        for clue_id in clue_ids:
            if clue_id not in all_clue_ids:
                errors.append({
                    "sev": SEVERITY_CRITICAL,
                    "msg": f"diseases.json.clues.{disease_key} → clue_id=\"{clue_id}\" 在 clue_descriptions 中无定义",
                    "fixable": True,
                    "fix": "add_clue_description",
                    "clue_id": clue_id,
                })

    for clue_id, exam_type in diseases.get("clue_to_test", {}).items():
        if exam_type not in exam_keys:
            errors.append({"sev": SEVERITY_CRITICAL, "msg": f"diseases.json.clue_to_test → \"{clue_id}\" 映射到不存在的检查类型 \"{exam_type}\"", "fixable": False})
        if clue_id not in all_clue_ids:
            errors.append({
                "sev": SEVERITY_HIGH,
                "msg": f"diseases.json.clue_to_test → clue_id=\"{clue_id}\" 在 clue_descriptions 中无定义",
                "fixable": True,
                "fix": "add_clue_description",
                "clue_id": clue_id,
            })

    treatment_keys = set(diseases.get("treatment_protocols", {}).keys())
    for disease_key in diseases.get("clues", {}).keys():
        if disease_key not in treatment_keys:
            errors.append({"sev": SEVERITY_HIGH, "msg": f"diseases.json → \"{disease_key}\" 有 clues 但无 treatment_protocols", "fixable": False})

    case_diseases = {c.get("disease", "") for c in load_json("cases.json").get("cases", [])}
    for disease_key in diseases.get("disease_names", {}).keys():
        if disease_key not in case_diseases:
            errors.append({"sev": SEVERITY_LOW, "msg": f"diseases.json → \"{disease_key}\" 未被任何病例引用", "fixable": False})

    win_msgs = set(diseases.get("messages", {}).get("win", {}).keys())
    loss_msgs = set(diseases.get("messages", {}).get("loss", {}).keys())
    all_disease_keys = set(diseases.get("disease_names", {}).keys())
    for dk in all_disease_keys:
        if dk not in win_msgs:
            errors.append({"sev": SEVERITY_MEDIUM, "msg": f"diseases.json.messages.win → 缺少 \"{dk}\" 的获胜消息", "fixable": False})
        if dk not in loss_msgs:
            errors.append({"sev": SEVERITY_MEDIUM, "msg": f"diseases.json.messages.loss → 缺少 \"{dk}\" 的失败消息", "fixable": False})

    return errors


def check_exam_templates(templates: dict, examinations: dict, vitals_ranges: dict, diseases: dict) -> list:
    errors = []
    exam_keys = set(examinations.keys())
    vitals_keys = set(vitals_ranges.keys())
    all_clue_ids = set(diseases.get("clue_descriptions", {}).keys())
    template_keys = {k for k in templates.keys() if not k.startswith("_")}

    if template_keys != exam_keys:
        only_in_exams = exam_keys - template_keys
        only_in_templates = template_keys - exam_keys
        for k in only_in_exams:
            errors.append({"sev": SEVERITY_LOW, "msg": f"examinations.json → \"{k}\" 在 exam_templates.json 中无对应模板", "fixable": False})
        for k in only_in_templates:
            errors.append({"sev": SEVERITY_LOW, "msg": f"exam_templates.json → \"{k}\" 在 examinations.json 中无对应定义", "fixable": False})

    for tkey, tmpl in templates.items():
        if tkey.startswith("_"):
            continue
        test_type = tmpl.get("test_type", tkey)
        if test_type not in exam_keys:
            errors.append({"sev": SEVERITY_HIGH, "msg": f"exam_templates.json:{tkey} → test_type=\"{test_type}\" 在 examinations.json 中不存在", "fixable": False})
        for vital in tmpl.get("vitals", []):
            if vital not in vitals_keys:
                errors.append({"sev": SEVERITY_CRITICAL, "msg": f"exam_templates.json:{tkey} → vitals=[\"{vital}\"] 在 vitals_ranges.json 中不存在", "fixable": False})
        for rule in tmpl.get("tag_rules", []):
            clue_id = rule.get("clue_id", "")
            if clue_id and clue_id not in all_clue_ids:
                errors.append({
                    "sev": SEVERITY_HIGH,
                    "msg": f"exam_templates.json:{tkey} → tag_rules clue_id=\"{clue_id}\" 在 diseases.json.clue_descriptions 中无定义",
                    "fixable": True,
                    "fix": "add_clue_description",
                    "clue_id": clue_id,
                })
    return errors


def check_game_config(config: dict, examinations: dict) -> list:
    errors = []
    exam_keys = set(examinations.keys())
    for i, combo in enumerate(config.get("combo_bonuses", [])):
        for test in combo.get("tests", []):
            if test not in exam_keys:
                errors.append({"sev": SEVERITY_HIGH, "msg": f"game_config.json.combo_bonuses[{i}] → tests=[\"{test}\"] 在 examinations.json 中不存在", "fixable": False})
    return errors


def check_ode_targets(ode_diseases: dict) -> list:
    errors = []
    for disease_key, disease in ode_diseases.items():
        if disease_key.startswith("_"):
            continue
        for i, output in enumerate(disease.get("outputs", [])):
            target = output.get("target", "")
            if not target:
                errors.append({"sev": SEVERITY_HIGH, "msg": f"ode_diseases.json:{disease_key}.outputs[{i}] → target 为空", "fixable": False})
                continue
            if not any(target.startswith(p) for p in VALID_PARAM_PREFIXES):
                errors.append({"sev": SEVERITY_HIGH, "msg": f"ode_diseases.json:{disease_key}.outputs[{i}] → target=\"{target}\" 不以任何已知 _PARAM_PATHS 前缀开头", "fixable": False})
    return errors


# ─── 修复函数 ────────────────────────────────────────────────

def generate_clue_description(clue_id: str) -> str:
    """从 clue_id 自动生成中文描述。"""
    # 常见模式映射
    patterns = {
        "_low": ("低", "降低"),
        "_high": ("高", "升高"),
    }
    # 已知参数名映射
    param_names = {
        "potassium": "钾", "sodium": "钠", "calcium": "钙", "magnesium": "镁",
        "chloride": "氯", "phosphorus": "磷", "glucose": "血糖", "bun": "BUN",
        "creatinine": "肌酐", "cr": "肌酐", "alt": "ALT", "ast": "AST",
        "bilirubin": "胆红素", "hct": "红细胞比容", "wbc": "白细胞",
        "plt": "血小板", "hr": "心率", "rr": "呼吸频率", "map": "平均动脉压",
        "cvp": "中心静脉压", "spo2": "血氧饱和度", "pao2": "氧分压",
        "paco2": "二氧化碳分压", "ph": "pH", "hco3": "碳酸氢根",
        "lactate": "乳酸", "gfr": "GFR", "usg": "尿比重",
        "upcr": "尿蛋白/肌酐比", "ketone": "酮体",
    }

    clue_lower = clue_id.lower()

    # 尝试匹配已知参数
    for param, name in sorted(param_names.items(), key=lambda x: -len(x[0])):
        if param in clue_lower:
            for suffix, (adj, verb) in patterns.items():
                if clue_lower.endswith(suffix):
                    if suffix == "_low":
                        return f"{name}{verb}"
                    else:
                        return f"{name}{verb}"
            return name

    # 特殊 ECG 相关
    if "t_wave" in clue_lower:
        return "T波" + ("高尖" if "tall" in clue_lower else "异常")
    if "qrs" in clue_lower:
        return "QRS" + ("增宽" if "wide" in clue_lower else "异常")
    if "p_wave" in clue_lower:
        return "P波" + ("消失" if "absent" in clue_lower else "异常")
    if "pr" in clue_lower:
        return "PR间期" + ("延长" if "prolong" in clue_lower else "异常")
    if "av" in clue_lower:
        return "AV传导" + ("阻滞" if "block" in clue_lower else "异常")

    # 兜底：把下划线替换为首字母大写
    return clue_id.replace("_", " ").title()


def fix_add_clue_description(diseases: dict, clue_id: str) -> bool:
    """自动添加缺失的 clue_description。"""
    if clue_id in diseases.get("clue_descriptions", {}):
        return False
    desc = generate_clue_description(clue_id)
    diseases.setdefault("clue_descriptions", {})[clue_id] = desc
    print(f"  [FIX] 添加 clue_descriptions[\"{clue_id}\"] = \"{desc}\"")
    return True


def apply_fixes(errors: list, diseases: dict) -> int:
    """应用自动修复，返回修复数量。"""
    fixed = 0
    seen_clues = set()  # 避免重复添加同一 clue_id

    for err in errors:
        if not err.get("fixable"):
            continue
        fix_type = err.get("fix")
        clue_id = err.get("clue_id")

        if fix_type == "add_clue_description" and clue_id:
            if clue_id in seen_clues:
                continue
            seen_clues.add(clue_id)
            if fix_add_clue_description(diseases, clue_id):
                fixed += 1

    if fixed > 0:
        save_json("diseases.json", diseases)

    return fixed


# ─── 主入口 ─────────────────────────────────────────────────

def run_check() -> tuple[int, list, dict]:
    """运行检查，返回 (exit_code, errors, diseases_dict)。"""
    errors = []
    cases = load_json("cases.json")
    diseases = load_json("diseases.json")
    examinations = load_json("examinations.json")
    templates = load_json("exam_templates.json")
    vitals_ranges = load_json("vitals_ranges.json")
    game_config = load_json("game_config.json")
    ode_diseases = load_json("ode_diseases.json")

    errors.extend(check_cases_to_diseases(cases, diseases, ode_diseases))
    errors.extend(check_disease_clues(diseases, examinations))
    errors.extend(check_exam_templates(templates, examinations, vitals_ranges, diseases))
    errors.extend(check_game_config(game_config, examinations))
    errors.extend(check_ode_targets(ode_diseases))

    if not errors:
        return 0, [], diseases

    critical = [e for e in errors if e["sev"] == SEVERITY_CRITICAL]
    high = [e for e in errors if e["sev"] == SEVERITY_HIGH]
    medium = [e for e in errors if e["sev"] == SEVERITY_MEDIUM]
    low = [e for e in errors if e["sev"] == SEVERITY_LOW]

    for err in errors:
        print(f"[{err['sev']}] {err['msg']}")

    print(f"\n共 {len(errors)} 个问题：CRITICAL={len(critical)}, HIGH={len(high)}, MEDIUM={len(medium)}, LOW={len(low)}")

    fixable = [e for e in errors if e.get("fixable")]
    if fixable:
        print(f"  其中 {len(fixable)} 个可自动修复（使用 --fix）")

    if critical or high:
        return 1, errors, diseases
    return 2, errors, diseases


def run_fix() -> int:
    """运行检查并自动修复。"""
    print("=" * 50)
    print("数据一致性检查 — 修复模式")
    print("=" * 50)

    exit_code, errors, diseases = run_check()

    if not errors:
        print("[OK] 无需修复")
        return 0

    fixable = [e for e in errors if e.get("fixable")]
    if not fixable:
        print("\n没有可自动修复的问题，请手动修复")
        return exit_code

    print(f"\n正在自动修复 {len(fixable)} 个问题...")
    fixed = apply_fixes(fixable, diseases)
    print(f"\n[FIXED] 已修复 {fixed} 个问题")

    # 修复后重新检查
    print("\n重新检查...")
    exit_code2, errors2, _ = run_check()
    return exit_code2


def main():
    parser = argparse.ArgumentParser(description="JSON 配置文件交叉一致性检查")
    parser.add_argument("--fix", action="store_true", help="自动修复可修复的问题")
    args = parser.parse_args()

    if args.fix:
        return run_fix()
    else:
        exit_code, _, _ = run_check()
        return exit_code


if __name__ == "__main__":
    sys.exit(main())
