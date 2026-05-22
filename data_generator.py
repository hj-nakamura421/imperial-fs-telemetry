"""Generate a synthetic Formula Student drivetrain test session.

Produces data/sample_run.csv with realistic-shaped telemetry for ~10 laps of
a small-formula electric car (Emrax-228-class motor, 600V nominal pack).
Synthetic so the dashboard has something to show before real test logs land.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

# --- Session parameters -----------------------------------------------------
NUM_LAPS = 10
LAP_TIME_S = 60          # one lap of a typical FS autocross
SAMPLE_HZ = 10           # 10 Hz is plenty for trend visualisation
NOMINAL_VOLTAGE_V = 600  # accumulator nominal
INTERNAL_RES_OHM = 0.05  # rough pack internal resistance

OUT_PATH = Path(__file__).parent / "data" / "sample_run.csv"


def generate() -> pd.DataFrame:
    rng = np.random.default_rng(seed=42)
    total_time = NUM_LAPS * LAP_TIME_S
    t = np.arange(0, total_time, 1 / SAMPLE_HZ)

    # RPM: layered sinusoids approximate corner / straight cycles within a lap
    rpm = (
        3500
        + 2500 * np.sin(2 * np.pi * t / 12)
        + 800 * np.sin(2 * np.pi * t / 4)
        + rng.normal(0, 100, len(t))
    )
    rpm = np.clip(rpm, 800, 7000)

    # Torque rolls off above ~5000 RPM (constant-power region)
    torque = np.where(rpm > 5000, 80 - (rpm - 5000) * 0.01, 80)
    torque = np.clip(torque + rng.normal(0, 3, len(t)), 0, 100)

    # Mechanical power = T * omega
    power_kw = (torque * rpm * 2 * np.pi / 60) / 1000

    # Electrical side: current from power, voltage sags under load
    current_a = (power_kw * 1000) / NOMINAL_VOLTAGE_V
    battery_v = NOMINAL_VOLTAGE_V - current_a * INTERNAL_RES_OHM

    # Temperatures ramp through the session with slow oscillation
    motor_temp = (
        30
        + (t / total_time) * 60
        + 5 * np.sin(2 * np.pi * t / 30)
        + rng.normal(0, 1, len(t))
    )
    inverter_temp = (
        25
        + (t / total_time) * 40
        + 3 * np.sin(2 * np.pi * t / 45)
        + rng.normal(0, 0.5, len(t))
    )

    # Inject realistic anomalies the dashboard should catch
    # Lap 4: motor overtemp event
    motor_temp[(t >= 220) & (t <= 260)] += 25
    # Lap 6: inverter overtemp
    inverter_temp[(t >= 340) & (t <= 360)] += 30
    # Lap 8: voltage sag under hard acceleration
    battery_v[(t >= 460) & (t <= 470)] -= 35

    lap_num = (t // LAP_TIME_S + 1).astype(int)

    return pd.DataFrame(
        {
            "time_s": np.round(t, 2),
            "lap": lap_num,
            "motor_rpm": np.round(rpm, 1),
            "motor_torque_nm": np.round(torque, 2),
            "power_kw": np.round(power_kw, 2),
            "motor_temp_c": np.round(motor_temp, 2),
            "inverter_temp_c": np.round(inverter_temp, 2),
            "battery_voltage_v": np.round(battery_v, 2),
            "battery_current_a": np.round(current_a, 2),
        }
    )


def main() -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df = generate()
    df.to_csv(OUT_PATH, index=False)
    print(f"Wrote {len(df):,} rows to {OUT_PATH}")
    print(df.describe().round(2))


if __name__ == "__main__":
    main()
