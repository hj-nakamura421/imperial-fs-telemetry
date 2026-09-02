import pandas as pd
import pytest

from data_generator import generate
from telemetry import (
    TelemetryValidationError,
    Thresholds,
    detect_anomalies,
    detect_events,
    event_table,
    headline_metrics,
    lap_summary,
    validate_telemetry_frame,
)


@pytest.fixture
def telemetry_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "time_s": [0.0, 1.0, 2.0, 3.0],
            "lap": [1, 1, 1, 2],
            "motor_rpm": [3_000, 3_000, 3_000, 2_000],
            "motor_torque_nm": [30, 30, 30, 20],
            "power_kw": [10.0, 10.0, 10.0, 5.0],
            "motor_temp_c": [70.0, 101.0, 75.0, 80.0],
            "inverter_temp_c": [60.0, 70.0, 81.0, 65.0],
            "battery_voltage_v": [590.0, 580.0, 530.0, 570.0],
            "battery_current_a": [20.0, 25.0, 30.0, 10.0],
        }
    )


def test_validate_telemetry_rejects_missing_columns(telemetry_frame: pd.DataFrame) -> None:
    with pytest.raises(TelemetryValidationError, match="Missing required columns"):
        validate_telemetry_frame(telemetry_frame.drop(columns="battery_current_a"))


def test_validate_telemetry_rejects_non_numeric_data(telemetry_frame: pd.DataFrame) -> None:
    telemetry_frame["power_kw"] = telemetry_frame["power_kw"].astype(object)
    telemetry_frame.loc[1, "power_kw"] = "fast"
    with pytest.raises(TelemetryValidationError, match="non-numeric"):
        validate_telemetry_frame(telemetry_frame)


def test_headline_metrics_integrate_timestamped_power(telemetry_frame: pd.DataFrame) -> None:
    metrics = headline_metrics(telemetry_frame, nominal_pack_voltage_v=600)

    assert metrics.mechanical_energy_kj == pytest.approx(27.5)
    assert metrics.electrical_energy_kj == pytest.approx(39.15)
    assert metrics.estimated_drivetrain_efficiency_pct == pytest.approx(70.24, abs=0.01)
    assert metrics.maximum_voltage_sag_v == pytest.approx(70.0)


def test_detect_events_groups_threshold_breaches_into_review_windows(telemetry_frame: pd.DataFrame) -> None:
    events = detect_events(telemetry_frame, Thresholds())

    assert [event.signal for event in events] == ["motor_temperature", "inverter_temperature", "pack_voltage"]
    assert events[0].start_time_s == pytest.approx(1.0)
    assert events[0].duration_s == pytest.approx(1.0)
    assert events[0].severity == "Review"
    assert events[2].extreme_value == pytest.approx(530.0)


def test_event_table_is_reviewer_ready(telemetry_frame: pd.DataFrame) -> None:
    review_log = event_table(detect_events(telemetry_frame, Thresholds()))

    assert list(review_log.columns) == [
        "severity",
        "event",
        "lap(s)",
        "start_s",
        "end_s",
        "duration_s",
        "extreme",
        "limit",
        "samples",
        "review_prompt",
    ]
    assert review_log.loc[2, "extreme"] == "530.0 V"


def test_lap_summary_reports_mechanical_and_electrical_energy(telemetry_frame: pd.DataFrame) -> None:
    summary = lap_summary(telemetry_frame)

    assert summary.loc[0, "mechanical_energy_kj"] == pytest.approx(20.0)
    assert summary.loc[0, "electrical_energy_kj"] == pytest.approx(28.35)
    assert summary.loc[0, "estimated_drivetrain_efficiency_pct"] == pytest.approx(70.55, abs=0.01)


def test_anomaly_view_remains_available_for_sample_level_inspection(telemetry_frame: pd.DataFrame) -> None:
    anomalies = detect_anomalies(telemetry_frame, Thresholds())

    assert {item.signal for item in anomalies} == {"motor_temperature", "inverter_temperature", "pack_voltage"}


def test_bundled_synthetic_scenario_exercises_the_debrief_path() -> None:
    frame = generate()
    metrics = headline_metrics(frame)
    events = detect_events(frame, Thresholds())
    signals = {event.signal for event in events}

    assert signals == {"motor_temperature", "inverter_temperature", "pack_voltage"}
    assert len(events) == 3
    assert metrics.electrical_energy_kj > metrics.mechanical_energy_kj
