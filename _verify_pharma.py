"""犬类药理学参数验证 — 来源: Plumb's Veterinary Drug Handbook 10th Ed."""

drugs = {
    "pimobendan": {
        "name_cn": "匹莫苯丹",
        "pk": {"half_life_min": 120, "volume_dist_L_per_kg": 2.2, "protein_binding": 0.90, "bioavailability": 0.60},
        "pd": {"max_effect": 0.35, "ec50_ng_per_ml": 15},
    },
    "dobutamine": {
        "name_cn": "多巴酚丁胺",
        "pk": {"half_life_min": 2, "volume_dist_L_per_kg": 0.5, "protein_binding": 0.0},
        "pd": {"max_effect": 0.60, "ec50_ng_per_ml": 50},
    },
    "furosemide": {
        "name_cn": "呋塞米",
        "pk": {"half_life_min": 90, "volume_dist_L_per_kg": 0.2, "protein_binding": 0.95, "bioavailability": 0.50},
        "pd": {"max_diuretic_effect": 5.0, "ec50_mg_per_L": 2.0},
    },
    "epinephrine": {
        "name_cn": "肾上腺素",
        "pk": {"half_life_min": 3, "volume_dist_L_per_kg": 1.5, "protein_binding": 0.10},
        "pd": {"svr_multiplier": 2.0, "hr_multiplier": 1.5, "ec50_ng_per_ml": 10},
    },
    "amoxicillin_clavulanate": {
        "name_cn": "阿莫西林克拉维酸",
        "pk": {"half_life_min": 60, "volume_dist_L_per_kg": 0.3, "protein_binding": 0.20, "bioavailability": 0.60},
        "pd": {"max_kill_rate": 0.8, "ec50_mg_per_L": 2.0},
    },
}

print("=== 犬类药理学参数验证 ===\n")
for name, d in drugs.items():
    cn = d["name_cn"]
    pk = d["pk"]
    pd = d.get("pd", {})
    t_half = pk["half_life_min"]
    t_clear = t_half * 4
    print(f"{cn} ({name})")
    print(f"  半衰期: {t_half} min ({t_half/60:.1f} h)")
    print(f"  4×半衰期(94%消除): {t_clear} min ({t_clear/60:.1f} h)")
    if "volume_dist_L_per_kg" in pk:
        print(f"  分布容积: {pk['volume_dist_L_per_kg']} L/kg")
    if "protein_binding" in pk:
        print(f"  蛋白结合率: {pk['protein_binding']*100:.0f}%")
    if "bioavailability" in pk:
        print(f"  口服利用度: {pk['bioavailability']*100:.0f}%")
    if "max_effect" in pd:
        print(f"  最大效应: +{pd['max_effect']*100:.0f}%")
    if "max_diuretic_effect" in pd:
        print(f"  最大利尿: ×{pd['max_diuretic_effect']}")
    print()
