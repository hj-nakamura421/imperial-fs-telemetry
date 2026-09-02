"""Generate a synthetic Formula Student drivetrain test session.

The sample intentionally contains three review scenarios: motor over-temperature,
inverter over-temperature, and pack-voltage sag. It is a demonstration dataset,
not an official team log.
"""

from pathlib import Path

import numpy as np
import pandas as pd


NUM_LAPS = 10
LAP_TIME_S = 60
SAMPLE_HZ = 10
NOMINAL_PACK_VOLTAGE_V = 600.0
PACK_RESISTANCE_OHM = 0.05
DRIVETRAIN_EFFICIENCY = 0.91
OUTPUT_PATH = Path(__file__).parent / "data" / "sample_run.csv"


def _current_for_electrical_power(electrical_power_w: np.ndarray) -> np.ndarray:
    """Solve P = (V_nominal - I R) I for physically consistent pack current."""
    discriminant = NOMINAL_PACK_VOLTAGE_V**2 - 4 * PACK_RESISTANCE_OHM * electrical_power_w
    if np.any(discriminant < 0):
        raise ValueError("Requested electrical power exceeds the simple pack-model limit.")
    return (NOMINAL_PACK_VOLTAGE_V - np.sqrt(discriminant)) / (2 * PACK_RESISTANCE_OHM)


def generate() -> pd.DataFrame:
    """Return one deterministic, synthetic EV endurance-style test session."""
    rng = np.random.default_rng(42)
    samples = NUM_LAPS * LAP_TIME_S * SAMPLE_HZ
    time_s = np.arange(samples) / SAMPLE_HZ
    lap_num = np.floor(time_s / LAP_TIME_S).astype(int) + 1
    lap_phase = (time_s % LAP_TIME_S) / LAP_TIME_S

    rpm = (
        5_100
        + 2_400 * np.sin(2 * np.pi * lap_phase - 0.5)
        + 550 * np.sin(8 * np.pi * lap_phase)
        + rng.normal(0, 95, samples)
    ).clip(900, None)
    torque_nm = (
        118
        + 80 * np.maximum(0, np.sin(2 * np.pi * lap_phase + 0.2))
        + 22 * np.sin(6 * np.pi * lap_phase)
        + rng.normal(0, 7, samples)
    ).clip(18, None)

    mechanical_power_kw = torque_nm * rpm * (2 * np.pi / 60) / 1_000
    electrical_power_w = mechanical_power_kw * 1_000 / DRIVETRAIN_EFFICIENCY
    pack_current_a = _current_for_electrical_power(electrical_power_w)
    pack_voltage_v = NOMINAL_PACK_VOLTAGE_V - pack_current_a * PACK_RESISTANCE_OHM

    motor_temp_c = 60 + 3 * lap_num + 5 * np.sin(2 * np.pi * lap_phase) + rng.normal(0, 1.2, samples)
    inverter_temp_c = 45 + 2.5 * lap_num + 3 * np.sin(2 * np.pi * lap_phase + 0.8) + rng.normal(0, 1, samples)

    # Deliberate review windows; these remain labelled as synthetic in the UI/README.
    motor_temp_c[(time_s >= 220) & (time_s < 260)] += 45
    inverter_temp_c[(time_s >= 340) & (time_s < 360)] += 35
    sag_window = (time_s >= 460) & (time_s < 470)
    pack_voltage_v[sag_window] -= 65
    pack_current_a[sag_window] = electrical_power_w[sag_window] / pack_voltage_v[sag_window]

    return pd.DataFrame(
        {
            "time_s": time_s,
            "lap": lap_num,
            "motor_rpm": rpm,
            "motor_torque_nm": torque_nm,
            "power_kw": mechanical_power_kw,
            "motor_temp_c": motor_temp_c,
            "inverter_temp_c": inverter_temp_c,
            "battery_voltage_v": pack_voltage_v,
            "battery_current_a": pack_current_a,
        }
    )


if __name__ == "__main__":
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    generate().to_csv(OUTPUT_PATH, index=False)
    print(f"Wrote {OUTPUT_PATH}")
