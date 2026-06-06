"""
Virtual Vet 多器官耦合引擎功能测试
验证：正常/疾病状态下血气、心血管、肾脏、生化数据正确性 + 时序一致性
"""
import urllib.request
import urllib.error
import json

BASE = "http://127.0.0.1:5000/api"


def api_post(path: str, data: dict, timeout: float = 8.0) -> dict:
    try:
        req = urllib.request.Request(
            BASE + path,
            data=json.dumps(data).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return {"_error": e.code, "_body": body[:500]}
    except TimeoutError:
        return {"_error": 408, "_body": "timeout"}


def api_get(path: str) -> dict:
    try:
        with urllib.request.urlopen(BASE + path, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"_error": e.code}


def gf(report: dict, param: str):
    """从 report.results 数组提取字段值"""
    for item in report.get("results", []):
        if item.get("param") == param:
            return item.get("value")
    return None


def gf_flag(report: dict, param: str):
    for item in report.get("results", []):
        if item.get("param") == param:
            return item.get("flag")
    return None


# ═══════════════════════════════════════════════
print("=" * 60)
print("Virtual Vet 功能测试")
print("=" * 60)

# ── Test 0: 连通性 ──
cases = api_get("/cases")
if "_error" in cases:
    print(f"❌ 服务器无响应: {cases}")
    exit(1)
print(f"✅ 服务器正常，{len(cases)} cases")
print(f"   {[c['id'] for c in cases]}")
print()

# ── Test 1: 正常血气基线 ──
print("=" * 60)
print("Test 1: 正常血气基线（case_001 轻症肺炎初始状态）")
print("=" * 60)
# 所有 case 都有疾病；用 difficulty=1 的 case_001 作为"相对正常"基线参考
baseline_c = next((c for c in cases if c.get("id") == "case_001"), None)
if baseline_c:
    print(f"  选择: {baseline_c['id']} | difficulty={baseline_c.get('difficulty')} | disease={baseline_c.get('disease')}")
    st = api_post("/new-game", {"case_id": baseline_c["id"]})
    sid = st["session_id"]

    r = api_post("/examine", {"session_id": sid, "test_type": "blood_gas"})
    rep = r.get("report", {})
    results = rep.get("results", [])
    print(f"  血气字段数: {len(results)}")
    for item in results:
        print(f"    {item['param']}={item['value']} {item['unit']} "
              f"[{item.get('normal_range','?')}] flag={item.get('flag','?')}")

    pao2 = gf(rep, "PaO2")
    paco2 = gf(rep, "PaCO2")
    ph = gf(rep, "pH")
    print(f"\n  核心指标:")
    if pao2:
        ok = 80 <= pao2 <= 110
        print(f"    {'✅' if ok else '⚠️'} PaO2={pao2} mmHg (正常 80-110)")
    if paco2:
        ok = 35 <= paco2 <= 45
        print(f"    {'✅' if ok else '⚠️'} PaCO2={paco2} mmHg (正常 35-45)")
    if ph:
        ok = 7.35 <= ph <= 7.45
        print(f"    {'✅' if ok else '⚠️'} pH={ph} (正常 7.35-7.45)")
else:
    print("  错误: case_001 不存在")

print()

# ── Test 2: 肺炎 PaO2 下降验证（Fix B 核心） ──
print("=" * 60)
print("Test 2: 肺炎 PaO2 下降验证（Fix B 核心）")
print("=" * 60)
pneumo_cases = [c for c in cases if c.get("disease") == "pneumonia"]
for pc in pneumo_cases:
    print(f"\n  {pc['id']} ({pc['animal']['species']} {pc['animal']['weight_kg']}kg)")
    # 初始血气
    s0 = api_post("/new-game", {"case_id": pc["id"]})
    sid = s0["session_id"]
    r0 = api_post("/examine", {"session_id": sid, "test_type": "blood_gas"})
    rep0 = r0.get("report", {})
    p0 = gf(rep0, "PaO2")
    pc0 = gf(rep0, "PaCO2")
    ph0 = gf(rep0, "pH")
    flag0 = gf_flag(rep0, "PaO2")
    print(f"  初始: PaO2={p0} ({flag0}), PaCO2={pc0}, pH={ph0}")

    # 等 3 turns 让病情发展
    for i in range(3):
        wr = api_post("/wait", {"session_id": sid})
        if "_error" in wr:
            print(f"    wait turn {i+1} error: {wr}")
            break

    # 3 turns 后血气
    r3 = api_post("/examine", {"session_id": sid, "test_type": "blood_gas"})
    rep3 = r3.get("report", {})
    p3 = gf(rep3, "PaO2")
    pc3 = gf(rep3, "PaCO2")
    ph3 = gf(rep3, "pH")
    flag3 = gf_flag(rep3, "PaO2")
    print(f"  3 turns: PaO2={p3} ({flag3}), PaCO2={pc3}, pH={ph3}")

    if p0 and p3:
        diff = p3 - p0
        print(f"  PaO2 变化: {diff:+.1f} mmHg")
        if diff < -5:
            print(f"  ✅ PaO2 下降 {diff:.1f} mmHg，符合肺炎肺泡渗出→低氧预期")
        elif diff < 0:
            print(f"  ⚠️  PaO2 下降但幅度小（{diff:.1f} mmHg），可能病情轻或已预热稳定")
        else:
            print(f"  ❌ PaO2 未下降或反升（{diff:+.1f} mmHg），Fix B 可能未生效")

print()

# ── Test 3: 时序一致性 ──
print("=" * 60)
print("Test 3: 时序一致性（两次 start 同 case）")
print("=" * 60)
if baseline_c:
    results = []
    for run in range(2):
        s = api_post("/new-game", {"case_id": baseline_c["id"]})
        r = api_post("/examine", {"session_id": s["session_id"], "test_type": "blood_gas"})
        po2 = gf(r.get("report", {}), "PaO2")
        results.append(po2)
        print(f"  Run {run+1}: PaO2={po2}")
    if results[0] == results[1]:
        print(f"  ✅ 两次结果完全一致，时序稳定")
    else:
        print(f"  ⚠️  结果不一致: {results}")
else:
    print("  跳过")

print()

# ── Test 4: 所有检查类型响应完整性 ──
print("=" * 60)
print("Test 4: 检查类型响应完整性")
print("=" * 60)
test_types = [
    "blood_routine", "blood_gas", "urinalysis",
    "chest_xray", "ultrasound", "ecg", "blood_pressure",
]
if baseline_c:
    st = api_post("/new-game", {"case_id": baseline_c["id"]})
    sid = st["session_id"]
    for tt in test_types:
        r = api_post("/examine", {"session_id": sid, "test_type": tt})
        if "_error" in r:
            print(f"  ❌ {tt}: HTTP {r['_error']} body={r.get('_body','?')[:200]}")
            continue
        rep = r.get("report", {})
        n = len(rep.get("results", []))
        ok = "✅" if n > 0 else "⚠️"
        print(f"  {ok} {tt}: {n} fields")
        if n == 0:
            print(f"       raw: {json.dumps(r.get('report', {}), ensure_ascii=False)[:100]}")
else:
    print("  跳过")

print()

# ── Test 5: ARF 肾功能验证 ──
print("=" * 60)
print("Test 5: 急性肾衰 ARF 肾功能")
print("=" * 60)
arf_c = next((c for c in cases if c.get("disease") == "acute_renal_failure"), None)
if arf_c:
    print(f"  选择: {arf_c['id']}")
    st = api_post("/new-game", {"case_id": arf_c["id"]})
    sid = st["session_id"]
    r = api_post("/examine", {"session_id": sid, "test_type": "blood_biochem"})
    if "_error" in r:
        print(f"  ⚠️  blood_biochem 暂跳过（HTTP {r['_error']}）")
    else:
        rep = r.get("report", {})
        bun = gf(rep, "BUN")
        cr = gf(rep, "creatinine")
        k = gf(rep, "potassium")
        print(f"  BUN={bun} mg/dL, Creatinine={cr} mg/dL, K+={k} mEq/L")
        if bun and bun > 25:
            print(f"  ✅ BUN={bun} 升高，符合 ARF 蛋白分解代谢亢进")
        if cr and cr > 1.5:
            print(f"  ✅ Creatinine={cr} 升高，符合 ARF 肾小球滤过率下降")
        if k and k > 5.5:
            print(f"  ✅ K+={k} 高钾，符合 ARF 排泄障碍")
else:
    print("  跳过（无 ARF case）")

print()
print("=" * 60)
print("全部测试完成")
print("=" * 60)