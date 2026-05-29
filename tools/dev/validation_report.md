# VirtualVet Validation Report — Literature Comparison

| Scenario | Variable | Simulated | Literature Range | Status | Source |
|---|---|---|---|---|---|
| healthy | HR (bpm) | 86.0 | 60-140 | PASS | Nelson & Couto 5e Ch22 |
| healthy | MAP (mmHg) | 100.5 | 80-120 | PASS | Nelson & Couto 5e Ch22 |
| healthy | CO (mL/min) | 1720.0 | 1400-2000 | PASS | Guyton 14e Ch20 (20kg dog) |
| healthy | GFR (mL/min) | 63.9 | 50-80 | PASS | Nelson & Couto 5e Ch53 |
| healthy | SVR | 1.4 | 1.0-1.8 | PASS | Guyton 14e Ch26 |
| healthy | pH | 7.4 | 7.35-7.45 | PASS | Nelson & Couto 5e Ch6 |
| healthy | BUN (mg/dL) | 14.3 | 10-28 | PASS | Cornell Vet Lab |
| healthy | Creatinine (mg/dL) | 0.9 | 0.5-1.6 | PASS | Cornell Vet Lab |
| healthy | Na (mEq/L) | 145.0 | 141-151 | PASS | Iowa State Vet Path |
| healthy | K (mEq/L) | 4.2 | 3.9-5.3 | PASS | Iowa State Vet Path |
| healthy | Lactate (mmol/L) | 0.9 | 0.5-2.5 | PASS | IDEXX Catalyst |
| healthy | ALT (U/L) | 25.0 | 17-95 | PASS | Cornell Vet Lab |
| healthy | Albumin (g/dL) | 3.0 | 3.2-4.1 | WARN | Cornell Vet Lab |
| healthy | PaO2 (mmHg) | 91.5 | 85-95 | PASS | Iowa State Vet Path |
| healthy | PaCO2 (mmHg) | 38.0 | 29-42 | PASS | Iowa State Vet Path |
| healthy | RR (/min) | 18.0 | 10-30 | PASS | Nelson & Couto 5e Ch6 |
| arf | GFR decline (%) | 70% | 30-60 | PASS | Nelson & Couto 5e Ch53 (moderate ARF: GFR 30-60% of normal) |
| arf | BUN elevation (mg/dL) | 20.3 | 25-60 | WARN | Nelson & Couto 5e Ch53 |
| arf | Cr elevation (mg/dL) | 1.4 | 1.5-4.0 | WARN | Nelson & Couto 5e Ch53 |
| arf | K+ elevation (mEq/L) | 4.2 | 4.5-6.0 | WARN | Nelson & Couto 5e Ch53 (hyperkalemia in ARF) |
| hemorrhage | HR compensation | 133.7 | 120-180 | PASS | Guyton 14e Ch26 (Class II-III hemorrhage) |
| hemorrhage | MAP drop (mmHg) | 95.1 | 70-100 | PASS | Guyton 14e Ch26 (400mL loss on 20kg dog) |
| hemorrhage | BV remaining (%) | 77% | 1200-1500 | PASS | Guyton 14e Ch26 (20-25% loss) |
| pneumonia | HR elevation | 180.8 | 100-160 | WARN | Nelson & Couto 5e Ch11 |
| pneumonia | PaO2 depression | 91.5 | 50-80 | WARN | Nelson & Couto 5e Ch11 (V/Q mismatch) |

**Summary**: 19 PASS, 6 WARN, 0 FAIL

## Issues Requiring Calibration

