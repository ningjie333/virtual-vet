"""
Root cause: explicit Euler on stiff baroreflex ODE
Confirmed by:
1. step() (Sequential Euler) RMSE increases as dt decreases: 4.03 → 7.50 → 9.51 → 10.83
2. Pure Euler (RK23 on _unified_rhs) RMSE ~0.11 (stable across dt)
3. Explicit Euler on _unified_rhs: RMSE increases as dt decreases: 0.101 → 0.105 → 0.108 → 0.110 → 0.111
   (confirms _unified_rhs is stiff — explicit Euler fails)
4. BDF: stable, HR=[85-130.7], no saturation

HR saturation at 180: at t=25s, dHR/dt ≈ 1.1/s for error ≈ 0.074
With explicit Euler: HR_{n+1} = HR_n + dt * 1.1
  dt=0.1: 11 beats/step → hits 180 in (180-85)/11 ≈ 8.6 steps = 0.86s after t=25
  dt=0.01: 0.11 beats/step → in 25/0.01 = 2500 steps, accumulates to ~275 before saturation
  Larger dt jumps faster but also jumps past the peak
  Smaller dt accumulates consistently toward saturation

With BDF (implicit): the stiff solve handles the 1.1/s rate correctly
  HR converges gradually from 85 to 130 over 60s
  No saturation at 180

CONCLUSION: The step() path uses explicit Euler on a STIFF ODE system.
Fix: use BDF or Radau solver (already in _unified_rhs / run_unified_ivp) for stiff baroreflex.
step() should be replaced by run_unified_ivp for hemorrhage simulation.
"""
print(__doc__)