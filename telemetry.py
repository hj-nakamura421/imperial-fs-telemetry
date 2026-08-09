"""Pure telemetry analysis used by the Streamlit interface and tests."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = (
    "time_s",
    "lap",
    "motor_rpm",
    "motor_torque_nm",
    "power_kw",
    "motor_temp_c",
    "inverter_temp_c",
    "battery_voltage_v",
    "battery_current_a",
)


class TelemetryValidationError(ValueError):
    """Raised when an uploaded telemetry frame violates the data contract."""


@dataclass(frozen=True)
class Thresholds:
    """Runtime limits used to flag samples for engineering review."""

    motor_temp_c: float = 100.0
    inverter_temp_c: float = 80.0
    pack_voltage_v: float = 540.0


@dataclass(frozen=True)
class HeadlineMetrics:
    peak_power_kw: float
    average_power_kw: float
    maximum_motor_temp_c: float
    minimum_pack_voltage_v: float
    laps_logged: int


@dataclass(frozen=True)
class Anomaly:
    signal: str
    message: str
    sample_count: int
    laps: tuple[int, ...]


def validate_telemetry_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalise an uploaded telemetry frame.

    A copy is returned so callers can safely retain the uploaded object.
    """

    if frame.empty:
        raise TelemetryValidationError("The telemetry file contains no rows.")

    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise TelemetryValidationError(
            "Missing required columns: " + ", ".join(f"`{column}`" for column in missing)
        )

    validated = frame.copy()
    for column in REQUIRED_COLUMNS:
        converted = pd.to_numeric(validated[column], errors="coerce")
        invalid = converted.isna() & validated[column].notna()
        if invalid.any():
            rows = ", ".join(str(index) for index in validated.index[invalid][:5])
            raise TelemetryValidationError(
                f"`{column}` contains non-numeric values at row(s): {rows}."
            )
        validated[column] = converted

    if validated[list(REQUIRED_COLUMNS)].isna().any().any():
        columns = validated[list(REQUIRED_COLUMNS)].columns[
            validated[list(REQUIRED_COLUMNS)].isna().any()
        ]
        raise TelemetryValidationError(
            "Required values are missing in: " + ", ".join(f"`{column}`" for column in columns)
        )

    values = validated[list(REQUIRED_COLUMNS)].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise TelemetryValidationError("Telemetry values must all be finite numbers.")

    if (validated["time_s"].diff().dropna() < 0).any():
        raise TelemetryValidationError("`time_s` must be ordered from earliest to latest.")

    lap_values = validated["lap"].to_numpy(dtype=float)
    if (lap_values < 1).any() or not np.allclose(lap_values, np.round(lap_values)):
        raise TelemetryValidationError("`lap` must contain positive whole numbers.")
    validated["lap"] = validated["lap"].astype(int)

    return validated


def headline_metrics(frame: pd.DataFrame) -> HeadlineMetrics:
    """Compute the metrics shown above the dashboard."""

    return HeadlineMetrics(
        peak_power_kw=float(frame["power_kw"].max()),
        average_power_kw=float(frame["power_kw"].mean()),
        maximum_motor_temp_c=float(frame["motor_temp_c"].max()),
        minimum_pack_voltage_v=float(frame["battery_voltage_v"].min()),
        laps_logged=int(frame["lap"].nunique()),
    )


def detect_anomalies(
    frame: pd.DataFrame, thresholds: Thresholds = Thresholds()
) -> list[Anomaly]:
    """Return threshold violations with affected laps and sample counts."""

    checks = (
        (
            "motor_temperature",
            frame["motor_temp_c"] > thresholds.motor_temp_c,
            f"Motor over {thresholds.motor_temp_c:g} °C",
        ),
        (
            "inverter_temperature",
            frame["inverter_temp_c"] > thresholds.inverter_temp_c,
            f"Inverter over {thresholds.inverter_temp_c:g} °C",
        ),
        (
            "pack_voltage",
            frame["battery_voltage_v"] < thresholds.pack_voltage_v,
            f"Pack voltage under {thresholds.pack_voltage_v:g} V",
        ),
    )

    anomalies: list[Anomaly] = []
    for signal, mask, message in checks:
        if mask.any():
            laps = tuple(sorted(int(lap) for lap in frame.loc[mask, "lap"].unique()))
            anomalies.append(
                Anomaly(
                    signal=signal,
                    message=message,
                    sample_count=int(mask.sum()),
                    laps=laps,
                )
            )
    return anomalies


def _integrate_power_kj(group: pd.DataFrame) -> float:
    """Integrate kW over seconds with the trapezoidal rule to obtain kJ."""

    ordered = group.sort_values("time_s")
    time_s = ordered["time_s"].to_numpy(dtype=float)
    power_kw = ordered["power_kw"].to_numpy(dtype=float)
    if len(ordered) < 2:
        return 0.0
    intervals = np.diff(time_s)
    interval_power = (power_kw[:-1] + power_kw[1:]) / 2
    return float(np.sum(intervals * interval_power))


def lap_summary(frame: pd.DataFrame) -> pd.DataFrame:
    """Build a per-lap engineering summary without assuming a sample rate."""

    rows = []
    for lap, group in frame.groupby("lap", sort=True):
        rows.append(
            {
                "lap": int(lap),
                "duration_s": float(group["time_s"].max() - group["time_s"].min()),
                "avg_power_kw": float(group["power_kw"].mean()),
                "peak_power_kw": float(group["power_kw"].max()),
                "max_motor_temp_c": float(group["motor_temp_c"].max()),
                "min_pack_voltage_v": float(group["battery_voltage_v"].min()),
                "energy_kj": _integrate_power_kj(group),
            }
        )
    return pd.DataFrame(rows).round(2)
