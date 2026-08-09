from __future__ import annotations

import pandas as pd
import pytest

from telemetry import (
    TelemetryValidationError,
    Thresholds,
    detect_anomalies,
    headline_metrics,
    lap_summary,
    validate_telemetry_frame,
)


def telemetry_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "time_s": [0.0, 1.0, 2.0, 3.0],
            "lap": [1, 1, 1, 2],
            "motor_rpm": [1000, 2000, 3000, 1200],
            "motor_torque_nm": [20, 20, 20, 10],
            "power_kw": [10.0, 10.0, 10.0, 5.0],
            "motor_temp_c": [70.0, 101.0, 75.0, 80.0],
            "inverter_temp_c": [60.0, 70.0, 81.0, 65.0],
            "battery_voltage_v": [590.0, 580.0, 530.0, 570.0],
            "battery_current_a": [20.0, 25.0, 30.0, 10.0],
        }
    )


def test_validation_reports_missing_columns() -> None:
    frame = telemetry_frame().drop(columns=["motor_rpm"])

    with pytest.raises(TelemetryValidationError, match="motor_rpm"):
        validate_telemetry_frame(frame)


def test_validation_rejects_non_numeric_values() -> None:
    frame = telemetry_frame()
    frame["power_kw"] = [10.0, 10.0, "not-a-number", 5.0]

    with pytest.raises(TelemetryValidationError, match="power_kw"):
        validate_telemetry_frame(frame)


def test_metrics_and_lap_energy_are_sample_rate_independent() -> None:
    frame = validate_telemetry_frame(telemetry_frame())

    metrics = headline_metrics(frame)
    summary = lap_summary(frame)

    assert metrics.peak_power_kw == 10.0
    assert metrics.laps_logged == 2
    assert summary.loc[summary["lap"] == 1, "energy_kj"].item() == 20.0


def test_anomalies_include_affected_laps() -> None:
    frame = validate_telemetry_frame(telemetry_frame())

    anomalies = detect_anomalies(frame, Thresholds())

    assert [anomaly.signal for anomaly in anomalies] == [
        "motor_temperature",
        "inverter_temperature",
        "pack_voltage",
    ]
    assert all(anomaly.laps == (1,) for anomaly in anomalies)
