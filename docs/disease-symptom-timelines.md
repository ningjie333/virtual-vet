# 各疾病症状出现时间线

数据来源：`paper_rewriting_output/disease_progression_data.json`（19 个疾病 × 5 个采样点）

符号说明：
- **NEW** = 该时间点新增的症状（相对前一采样点）
- 同一疾病下，症状在首次出现时刻后保持持续触发状态直到采样结束
- 采样间隔：5/10/15/30 min（即 300/600/900/1800 s 间隔），warmup_min 见各 case


## case_001 — pneumonia

**标题**: 呕吐与嗜睡  
**Warmup**: 2 min  
**采样点**: 5

| 时间 (s) | 新增症状 | 累计症状数 | 当下全部活动症状 |
|---:|---|---:|---|
| 120 | — | 0 | — |
| 420 | **cough** | 1 | cough |
| 1020 | **cyanosis**, **dyspnea** | 3 | cough, cyanosis, dyspnea |
| 1920 | — | 3 | cough, cyanosis, dyspnea |
| 3720 | **coagulopathy_signs** | 4 | coagulopathy_signs, cough, cyanosis, dyspnea |

**所有触发的症状（合并去重）**:
`coagulopathy_signs`, `cough`, `cyanosis`, `dyspnea`

## case_002 — acute_renal_failure

**标题**: 无尿与呕吐  
**Warmup**: 2 min  
**采样点**: 5

| 时间 (s) | 新增症状 | 累计症状数 | 当下全部活动症状 |
|---:|---|---:|---|
| 120 | **bleeding_gums**, **bradycardia**, **halitosis**, **oliguria**, **oral_ulcers** | 5 | bleeding_gums, bradycardia, halitosis, oliguria, oral_ulcers |
| 420 | — | 5 | bleeding_gums, bradycardia, halitosis, oliguria, oral_ulcers |
| 1020 | **exercise_intolerance**, **vomiting**, **weakness** | 8 | bleeding_gums, bradycardia, exercise_intolerance, halitosis, oliguria, oral_ulcers, vomiting, weakness |
| 1920 | — | 8 | bleeding_gums, bradycardia, exercise_intolerance, halitosis, oliguria, oral_ulcers, vomiting, weakness |
| 3720 | **coagulopathy_signs** | 9 | bleeding_gums, bradycardia, coagulopathy_signs, exercise_intolerance, halitosis, oliguria, oral_ulcers, vomiting, weakness |

**所有触发的症状（合并去重）**:
`bleeding_gums`, `bradycardia`, `coagulopathy_signs`, `exercise_intolerance`, `halitosis`, `oliguria`, `oral_ulcers`, `vomiting`, `weakness`

## case_003 — dilated_cardiomyopathy

**标题**: 运动不耐受与咳嗽  
**Warmup**: 5 min  
**采样点**: 5

| 时间 (s) | 新增症状 | 累计症状数 | 当下全部活动症状 |
|---:|---|---:|---|
| 300 | **exercise_intolerance**, **gallop_rhythm** | 2 | exercise_intolerance, gallop_rhythm |
| 600 | — | 2 | exercise_intolerance, gallop_rhythm |
| 1200 | — | 2 | exercise_intolerance, gallop_rhythm |
| 2100 | — | 2 | exercise_intolerance, gallop_rhythm |
| 3900 | **coagulopathy_signs** | 3 | coagulopathy_signs, exercise_intolerance, gallop_rhythm |

**所有触发的症状（合并去重）**:
`coagulopathy_signs`, `exercise_intolerance`, `gallop_rhythm`

## case_004 — phosphorus_poisoning

**标题**: 误食灭鼠药后呕吐抽搐  
**Warmup**: 1 min  
**采样点**: 5

| 时间 (s) | 新增症状 | 累计症状数 | 当下全部活动症状 |
|---:|---|---:|---|
| 60 | **mild_pain** | 1 | mild_pain |
| 360 | **abdominal_pain**, **muscle_tremor** | 3 | abdominal_pain, mild_pain, muscle_tremor |
| 960 | **dysthermia** | 4 | abdominal_pain, dysthermia, mild_pain, muscle_tremor |
| 1860 | **limb_pain**, **pain**, **tremor** | 7 | abdominal_pain, dysthermia, limb_pain, mild_pain, muscle_tremor, pain, tremor |
| 3660 | **hematemesis** | 8 | abdominal_pain, dysthermia, hematemesis, limb_pain, mild_pain, muscle_tremor, pain, tremor |

**所有触发的症状（合并去重）**:
`abdominal_pain`, `dysthermia`, `hematemesis`, `limb_pain`, `mild_pain`, `muscle_tremor`, `pain`, `tremor`

## case_005 — gastric_dilatation_volvulus

**标题**: 突发腹部膨隆与干呕  
**Warmup**: 0.5 min  
**采样点**: 5

| 时间 (s) | 新增症状 | 累计症状数 | 当下全部活动症状 |
|---:|---|---:|---|
| 30 | — | 0 | — |
| 330 | **abdominal_distension** | 1 | abdominal_distension |
| 930 | **exercise_intolerance** | 2 | abdominal_distension, exercise_intolerance |
| 1830 | — | 2 | abdominal_distension, exercise_intolerance |
| 3630 | — | 2 | abdominal_distension, exercise_intolerance |

**所有触发的症状（合并去重）**:
`abdominal_distension`, `exercise_intolerance`

## case_006 — immune_mediated_hemolytic_anemia

**标题**: 虚弱与黄疸  
**Warmup**: 2 min  
**采样点**: 5

| 时间 (s) | 新增症状 | 累计症状数 | 当下全部活动症状 |
|---:|---|---:|---|
| 120 | — | 0 | — |
| 420 | **icterus**, **pale_mm**, **splenomegaly**, **tachycardia** | 4 | icterus, pale_mm, splenomegaly, tachycardia |
| 1020 | — | 4 | icterus, pale_mm, splenomegaly, tachycardia |
| 1920 | — | 4 | icterus, pale_mm, splenomegaly, tachycardia |
| 3720 | **coagulopathy_signs** | 5 | coagulopathy_signs, icterus, pale_mm, splenomegaly, tachycardia |

**所有触发的症状（合并去重）**:
`coagulopathy_signs`, `icterus`, `pale_mm`, `splenomegaly`, `tachycardia`

## case_007 — urinary_obstruction

**标题**: 公猫无尿与呕吐  
**Warmup**: 1 min  
**采样点**: 5

| 时间 (s) | 新增症状 | 累计症状数 | 当下全部活动症状 |
|---:|---|---:|---|
| 60 | — | 0 | — |
| 360 | **bradycardia** | 1 | bradycardia |
| 960 | — | 1 | bradycardia |
| 1860 | — | 1 | bradycardia |
| 3660 | **exercise_intolerance**, **urinary_bladder_distended** | 3 | bradycardia, exercise_intolerance, urinary_bladder_distended |

**所有触发的症状（合并去重）**:
`bradycardia`, `exercise_intolerance`, `urinary_bladder_distended`

## case_008 — diabetic_ketoacidosis

**标题**: 多饮多饮后精神沉郁  
**Warmup**: 2 min  
**采样点**: 5

| 时间 (s) | 新增症状 | 累计症状数 | 当下全部活动症状 |
|---:|---|---:|---|
| 120 | **ketosis_signs** | 1 | ketosis_signs |
| 420 | — | 1 | ketosis_signs |
| 1020 | **glycosuria** | 2 | glycosuria, ketosis_signs |
| 1920 | — | 2 | glycosuria, ketosis_signs |
| 3720 | **coagulopathy_signs**, **weakness** | 4 | coagulopathy_signs, glycosuria, ketosis_signs, weakness |

**所有触发的症状（合并去重）**:
`coagulopathy_signs`, `glycosuria`, `ketosis_signs`, `weakness`

## case_009 — pericardial_effusion

**标题**: 颈静脉怒张与晕厥  
**Warmup**: 2 min  
**采样点**: 5

| 时间 (s) | 新增症状 | 累计症状数 | 当下全部活动症状 |
|---:|---|---:|---|
| 120 | **exercise_intolerance**, **weak_pulses** | 2 | exercise_intolerance, weak_pulses |
| 420 | **pulsus_paradoxus** | 3 | exercise_intolerance, pulsus_paradoxus, weak_pulses |
| 1020 | — | 3 | exercise_intolerance, pulsus_paradoxus, weak_pulses |
| 1920 | — | 3 | exercise_intolerance, pulsus_paradoxus, weak_pulses |
| 3720 | **coagulopathy_signs** | 4 | coagulopathy_signs, exercise_intolerance, pulsus_paradoxus, weak_pulses |

**所有触发的症状（合并去重）**:
`coagulopathy_signs`, `exercise_intolerance`, `pulsus_paradoxus`, `weak_pulses`

## case_010 — disseminated_intravascular_coagulation

**标题**: 发热后全身瘀斑  
**Warmup**: 2 min  
**采样点**: 5

| 时间 (s) | 新增症状 | 累计症状数 | 当下全部活动症状 |
|---:|---|---:|---|
| 120 | — | 0 | — |
| 420 | **crt**, **ecchymosis**, **prolonged_bleeding**, **thrombus_signs** | 4 | crt, ecchymosis, prolonged_bleeding, thrombus_signs |
| 1020 | — | 4 | crt, ecchymosis, prolonged_bleeding, thrombus_signs |
| 1920 | — | 4 | crt, ecchymosis, prolonged_bleeding, thrombus_signs |
| 3720 | **coagulopathy_signs** | 5 | coagulopathy_signs, crt, ecchymosis, prolonged_bleeding, thrombus_signs |

**所有触发的症状（合并去重）**:
`coagulopathy_signs`, `crt`, `ecchymosis`, `prolonged_bleeding`, `thrombus_signs`

## case_011 — hepatic_failure_coagulopathy

**标题**: 黄疸与皮下出血  
**Warmup**: 3 min  
**采样点**: 5

| 时间 (s) | 新增症状 | 累计症状数 | 当下全部活动症状 |
|---:|---|---:|---|
| 180 | **hypoalbuminemia** | 1 | hypoalbuminemia |
| 480 | **coagulopathy_signs**, **drowsiness**, **prolonged_bleeding** | 4 | coagulopathy_signs, drowsiness, hypoalbuminemia, prolonged_bleeding |
| 1080 | — | 4 | coagulopathy_signs, drowsiness, hypoalbuminemia, prolonged_bleeding |
| 1980 | — | 4 | coagulopathy_signs, drowsiness, hypoalbuminemia, prolonged_bleeding |
| 3780 | — | 4 | coagulopathy_signs, drowsiness, hypoalbuminemia, prolonged_bleeding |

**所有触发的症状（合并去重）**:
`coagulopathy_signs`, `drowsiness`, `hypoalbuminemia`, `prolonged_bleeding`

## case_012 — splenic_rupture

**标题**: 突发腹围增大与虚弱  
**Warmup**: 3 min  
**采样点**: 5

| 时间 (s) | 新增症状 | 累计症状数 | 当下全部活动症状 |
|---:|---|---:|---|
| 180 | **abdominal_pain**, **collapse**, **hypotension**, **mild_pain**, **muscle_tremor**, **shock**, **syncope**, **tachycardia**, **weakness** | 9 | abdominal_pain, collapse, hypotension, mild_pain, muscle_tremor, shock, syncope, tachycardia, weakness |
| 480 | **abdominal_tenderness**, **exercise_intolerance**, **limb_pain**, **pain** | 13 | abdominal_pain, abdominal_tenderness, collapse, exercise_intolerance, hypotension, limb_pain, mild_pain, muscle_tremor, pain, shock, syncope, tachycardia, weakness |
| 1080 | — | 13 | abdominal_pain, abdominal_tenderness, collapse, exercise_intolerance, hypotension, limb_pain, mild_pain, muscle_tremor, pain, shock, syncope, tachycardia, weakness |
| 1980 | — | 13 | abdominal_pain, abdominal_tenderness, collapse, exercise_intolerance, hypotension, limb_pain, mild_pain, muscle_tremor, pain, shock, syncope, tachycardia, weakness |
| 3780 | **coagulopathy_signs** | 14 | abdominal_pain, abdominal_tenderness, coagulopathy_signs, collapse, exercise_intolerance, hypotension, limb_pain, mild_pain, muscle_tremor, pain, shock, syncope, tachycardia, weakness |

**所有触发的症状（合并去重）**:
`abdominal_pain`, `abdominal_tenderness`, `coagulopathy_signs`, `collapse`, `exercise_intolerance`, `hypotension`, `limb_pain`, `mild_pain`, `muscle_tremor`, `pain`, `shock`, `syncope`, `tachycardia`, `weakness`

## case_013 — hyperthyroidism

**标题**: 消瘦多食伴心悸  
**Warmup**: 3 min  
**采样点**: 5

| 时间 (s) | 新增症状 | 累计症状数 | 当下全部活动症状 |
|---:|---|---:|---|
| 180 | **dysthermia**, **fever**, **polyphagia**, **weight_loss** | 4 | dysthermia, fever, polyphagia, weight_loss |
| 480 | **drowsiness**, **pu_pd**, **tachycardia** | 7 | drowsiness, dysthermia, fever, polyphagia, pu_pd, tachycardia, weight_loss |
| 1080 | — | 7 | drowsiness, dysthermia, fever, polyphagia, pu_pd, tachycardia, weight_loss |
| 1980 | — | 7 | drowsiness, dysthermia, fever, polyphagia, pu_pd, tachycardia, weight_loss |
| 3780 | **coagulopathy_signs** | 8 | coagulopathy_signs, drowsiness, dysthermia, fever, polyphagia, pu_pd, tachycardia, weight_loss |

**所有触发的症状（合并去重）**:
`coagulopathy_signs`, `drowsiness`, `dysthermia`, `fever`, `polyphagia`, `pu_pd`, `tachycardia`, `weight_loss`

## case_014 — hypoadrenocorticism

**标题**: 反复呕吐伴急性虚脱  
**Warmup**: 3 min  
**采样点**: 5

| 时间 (s) | 新增症状 | 累计症状数 | 当下全部活动症状 |
|---:|---|---:|---|
| 180 | **bradycardia**, **vomiting**, **weakness** | 3 | bradycardia, vomiting, weakness |
| 480 | — | 3 | bradycardia, vomiting, weakness |
| 1080 | **exercise_intolerance** | 4 | bradycardia, exercise_intolerance, vomiting, weakness |
| 1980 | — | 4 | bradycardia, exercise_intolerance, vomiting, weakness |
| 3780 | **coagulopathy_signs** | 5 | bradycardia, coagulopathy_signs, exercise_intolerance, vomiting, weakness |

**所有触发的症状（合并去重）**:
`bradycardia`, `coagulopathy_signs`, `exercise_intolerance`, `vomiting`, `weakness`

## case_015 — sepsis

**标题**: 术后高热伴精神沉郁  
**Warmup**: 2 min  
**采样点**: 5

| 时间 (s) | 新增症状 | 累计症状数 | 当下全部活动症状 |
|---:|---|---:|---|
| 120 | — | 0 | — |
| 420 | **weakness** | 1 | weakness |
| 1020 | **dysthermia** | 2 | dysthermia, weakness |
| 1920 | — | 2 | dysthermia, weakness |
| 3720 | **coagulopathy_signs** | 2 | coagulopathy_signs, weakness |

**所有触发的症状（合并去重）**:
`coagulopathy_signs`, `dysthermia`, `weakness`

## case_016 — ivdd

**标题**: 突发后肢瘫痪  
**Warmup**: 1 min  
**采样点**: 5

| 时间 (s) | 新增症状 | 累计症状数 | 当下全部活动症状 |
|---:|---|---:|---|
| 60 | **mild_pain** | 1 | mild_pain |
| 360 | **abdominal_pain**, **muscle_tremor** | 3 | abdominal_pain, mild_pain, muscle_tremor |
| 960 | **limb_pain**, **pain**, **paresis**, **spinal_pain** | 7 | abdominal_pain, limb_pain, mild_pain, muscle_tremor, pain, paresis, spinal_pain |
| 1860 | — | 7 | abdominal_pain, limb_pain, mild_pain, muscle_tremor, pain, paresis, spinal_pain |
| 3660 | **paralysis** | 8 | abdominal_pain, limb_pain, mild_pain, muscle_tremor, pain, paralysis, paresis, spinal_pain |

**所有触发的症状（合并去重）**:
`abdominal_pain`, `limb_pain`, `mild_pain`, `muscle_tremor`, `pain`, `paralysis`, `paresis`, `spinal_pain`

## case_017 — meningitis

**标题**: 发热伴颈部疼痛  
**Warmup**: 2 min  
**采样点**: 5

| 时间 (s) | 新增症状 | 累计症状数 | 当下全部活动症状 |
|---:|---|---:|---|
| 120 | **mild_pain** | 1 | mild_pain |
| 420 | **abdominal_pain**, **muscle_tremor**, **neck_stiffness** | 4 | abdominal_pain, mild_pain, muscle_tremor, neck_stiffness |
| 1020 | — | 4 | abdominal_pain, mild_pain, muscle_tremor, neck_stiffness |
| 1920 | **limb_pain**, **pain** | 6 | abdominal_pain, limb_pain, mild_pain, muscle_tremor, neck_stiffness, pain |
| 3720 | **coagulopathy_signs** | 7 | abdominal_pain, coagulopathy_signs, limb_pain, mild_pain, muscle_tremor, neck_stiffness, pain |

**所有触发的症状（合并去重）**:
`abdominal_pain`, `coagulopathy_signs`, `limb_pain`, `mild_pain`, `muscle_tremor`, `neck_stiffness`, `pain`

## case_018 — ckd_anemia

**标题**: 消瘦多饮伴精神萎靡  
**Warmup**: 5 min  
**采样点**: 5

| 时间 (s) | 新增症状 | 累计症状数 | 当下全部活动症状 |
|---:|---|---:|---|
| 300 | **bradycardia** | 1 | bradycardia |
| 600 | — | 1 | bradycardia |
| 1200 | — | 1 | bradycardia |
| 2100 | **anemia_signs**, **pale_mm** | 3 | anemia_signs, bradycardia, pale_mm |
| 3900 | **coagulopathy_signs** | 4 | anemia_signs, bradycardia, coagulopathy_signs, pale_mm |

**所有触发的症状（合并去重）**:
`anemia_signs`, `bradycardia`, `coagulopathy_signs`, `pale_mm`

## case_019 — hepatic_anemia

**标题**: 厌食呕吐伴皮肤黄染  
**Warmup**: 1 min  
**采样点**: 5

| 时间 (s) | 新增症状 | 累计症状数 | 当下全部活动症状 |
|---:|---|---:|---|
| 60 | — | 0 | — |
| 360 | **anemia_signs**, **mild_pain**, **pale_mm** | 3 | anemia_signs, mild_pain, pale_mm |
| 960 | **hypoalbuminemia**, **icterus** | 5 | anemia_signs, hypoalbuminemia, icterus, mild_pain, pale_mm |
| 1860 | **ascites**, **drowsiness** | 7 | anemia_signs, ascites, drowsiness, hypoalbuminemia, icterus, mild_pain, pale_mm |
| 3660 | **abdominal_pain**, **muscle_tremor** | 9 | abdominal_pain, anemia_signs, ascites, drowsiness, hypoalbuminemia, icterus, mild_pain, muscle_tremor, pale_mm |

**所有触发的症状（合并去重）**:
`abdominal_pain`, `anemia_signs`, `ascites`, `drowsiness`, `hypoalbuminemia`, `icterus`, `mild_pain`, `muscle_tremor`, `pale_mm`