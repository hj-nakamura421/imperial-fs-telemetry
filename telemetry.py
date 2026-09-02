"""Pure Formula Student telemetry analysis used by the Streamlit interface.

The module deliberately keeps the engineering calculations separate from the
dashboard. That makes the post-run checks testable and lets a team review the
logic before relying on it for test-session triage.
"""

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
    """Engineering review limits, configured at runtime in the dashboard."""

    motor_temp_c: float = 100.0
    inverter_temp_c: float = 80.0
    pack_voltage_v: float = 540.0


@dataclass(frozen=True)
class HeadlineMetrics:
    peak_power_kw: float
    average_power_kw: float
    maximum_motor_temp_c: float
    minimum_pack_voltage_v: float
    maximum_voltage_sag_v: float
    mechanical_energy_kj: float
    electrical_energy_kj: float
    estimated_drivetrain_efficiency_pct: float | None
    laps_logged: int


@dataclass(frozen=True)
class Anomaly:
    """An aggregate threshold breach across the test session."""

    signal: str
    message: str
    sample_count: int
    laps: tuple[int, ...]


@dataclass(frozen=True)
class TelemetryEvent:
    """One continuous threshold breach to investigate during a post-run debrief."""

    signal: str
    title: str
    severity: str
    start_time_s: float
    end_time_s: float
    duration_s: float
    sample_count: int
    laps: tuple[int, ...]
    threshold: float
    extreme_value: float
    unit: str
    review_prompt: str


_SIGNAL_RULES = (
    {
        "signal": "motor_temperature",
        "title": "Motor temperature limit exceeded",
        "column": "motor_temp_c",
        "threshold_name": "motor_temp_c",
        "operator": "above",
        "unit": "°C",
        "review_prompt": (
            "Review coolant flow, fan/pump operation, thermal derate settings and the "
            "high-load section of the run before scheduling the next test."
        ),
    },
    {
        "signal": "inverter_temperature",
        "title": "Inverter temperature limit exceeded",
        "column": "inverter_temp_c",
        "threshold_name": "inverter_temp_c",
        "operator": "above",
        "unit": "°C",
        "review_prompt": (
            "Review inverter cooling, current demand and any controller derate around "
            "the affected time window."
        ),
    },
    {
        "signal": "pack_voltage",
        "title": "Pack voltage sag limit exceeded",
        "column": "battery_voltage_v",
        "threshold_name": "pack_voltage_v",
        "operator": "below",
        "unit": "V",
        "review_prompt": (
            "Review pack state of charge, current draw, BMS limits and high-resistance "
            "paths in the accumulator and HV connections."
        ),
    },
)


def validate_telemetry_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalise an uploaded telemetry frame.

    A copy is returned so callers can safely retain the uploaded object. The
    dashboard intentionally rejects malformed data instead of quietly plotting
    it, because a plausible-looking chart can still lead a test debrief astray.
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


def electrical_power_kw(frame: pd.DataFrame) -> pd.Series:
    """Return pack-side electrical power in kW from recorded voltage/current."""

    return frame["battery_voltage_v"] * frame["battery_current_a"] / 1000


def _integrate_signal_kj(group: pd.DataFrame, signal_kw: pd.Series) -> float:
    """Integrate a kW signal over timestamped samples to obtain kJ."""

    ordered = group.sort_values("time_s")
    time_s = ordered["time_s"].to_numpy(dtype=float)
    values_kw = signal_kw.loc[ordered.index].to_numpy(dtype=float)
    if len(ordered) < 2:
        return 0.0
    return float(np.trapezoid(values_kw, time_s))


def _efficiency_pct(mechanical_energy_kj: float, electrical_energy_kj: float) -> float | None:
    if electrical_energy_kj <= 0:
        return None
    return 100 * mechanical_energy_kj / electrical_energy_kj


def headline_metrics(
    frame: pd.DataFrame, nominal_pack_voltage_v: float = 600.0
) -> HeadlineMetrics:
    """Compute the top-level metrics needed for a rapid post-run review."""

    mechanical_energy_kj = _integrate_signal_kj(frame, frame["power_kw"])
    electrical_energy_kj = _integrate_signal_kj(frame, electrical_power_kw(frame))
    minimum_pack_voltage_v = float(frame["battery_voltage_v"].min())
    return HeadlineMetrics(
        peak_power_kw=float(frame["power_kw"].max()),
        average_power_kw=float(frame["power_kw"].mean()),
        maximum_motor_temp_c=float(frame["motor_temp_c"].max()),
        minimum_pack_voltage_v=minimum_pack_voltage_v,
        maximum_voltage_sag_v=float(nominal_pack_voltage_v - minimum_pack_voltage_v),
        mechanical_energy_kj=mechanical_energy_kj,
        electrical_energy_kj=electrical_energy_kj,
        estimated_drivetrain_efficiency_pct=_efficiency_pct(
            mechanical_energy_kj, electrical_energy_kj
        ),
        laps_logged=int(frame["lap"].nunique()),
    )


def _breach_mask(frame: pd.DataFrame, rule: dict[str, str], threshold: float) -> pd.Series:
    if rule["operator"] == "above":
        return frame[rule["column"]] > threshold
    return frame[rule["column"]] < threshold


def detect_anomalies(
    frame: pd.DataFrame, thresholds: Thresholds = Thresholds()
) -> list[Anomaly]:
    """Return session-level threshold breaches with affected laps and sample counts."""

    anomalies: list[Anomaly] = []
    for rule in _SIGNAL_RULES:
        threshold = getattr(thresholds, rule["threshold_name"])
        mask = _breach_mask(frame, rule, threshold)
        if not mask.any():
            continue
        comparator = "over" if rule["operator"] == "above" else "under"
        laps = tuple(sorted(int(lap) for lap in frame.loc[mask, "lap"].unique()))
        anomalies.append(
            Anomaly(
                signal=rule["signal"],
                message=f"{rule['title']} ({comparator} {threshold:g} {rule['unit']})",
                sample_count=int(mask.sum()),
                laps=laps,
            )
        )
    return anomalies


def _median_sample_interval_s(frame: pd.DataFrame) -> float:
    positive_intervals = frame["time_s"].diff().dropna()
    positive_intervals = positive_intervals[positive_intervals > 0]
    return float(positive_intervals.median()) if not positive_intervals.empty else 0.0


def _severity(rule: dict[str, str], threshold: float, extreme_value: float) -> str:
    breach = extreme_value - threshold if rule["operator"] == "above" else threshold - extreme_value
    return "Priority review" if breach / threshold >= 0.05 else "Review"


def detect_events(
    frame: pd.DataFrame, thresholds: Thresholds = Thresholds()
) -> list[TelemetryEvent]:
    """Convert threshold samples into continuous, engineering-reviewable events.

    Consecutive samples are grouped using the observed median sample interval, so
    the debrief remains meaningful even when the logger does not sample at 10 Hz.
    """

    sample_interval_s = _median_sample_interval_s(frame)
    max_contiguous_gap_s = 1.5 * sample_interval_s if sample_interval_s else 0.0
    events: list[TelemetryEvent] = []

    for rule in _SIGNAL_RULES:
        threshold = float(getattr(thresholds, rule["threshold_name"]))
        breached = frame.loc[_breach_mask(frame, rule, threshold)].copy()
        if breached.empty:
            continue

        group_ids = (breached["time_s"].diff().fillna(0) > max_contiguous_gap_s).cumsum()
        for _, group in breached.groupby(group_ids, sort=False):
            values = group[rule["column"]]
            extreme_value = float(values.max() if rule["operator"] == "above" else values.min())
            start_time_s = float(group["time_s"].iloc[0])
            end_time_s = float(group["time_s"].iloc[-1])
            duration_s = end_time_s - start_time_s + sample_interval_s
            events.append(
                TelemetryEvent(
                    signal=rule["signal"],
                    title=rule["title"],
                    severity=_severity(rule, threshold, extreme_value),
                    start_time_s=start_time_s,
                    end_time_s=end_time_s,
                    duration_s=max(0.0, duration_s),
                    sample_count=len(group),
                    laps=tuple(sorted(int(lap) for lap in group["lap"].unique())),
                    threshold=threshold,
                    extreme_value=extreme_value,
                    unit=rule["unit"],
                    review_prompt=rule["review_prompt"],
                )
            )

    return sorted(events, key=lambda event: (event.start_time_s, event.signal))


def event_table(events: list[TelemetryEvent]) -> pd.DataFrame:
    """Build an exportable review log for the post-run debrief."""

    return pd.DataFrame(
        [
            {
                "severity": event.severity,
                "event": event.title,
                "lap(s)": ", ".join(str(lap) for lap in event.laps),
                "start_s": round(event.start_time_s, 2),
                "end_s": round(event.end_time_s, 2),
                "duration_s": round(event.duration_s, 2),
                "extreme": f"{event.extreme_value:.1f} {event.unit}",
                "limit": f"{event.threshold:.1f} {event.unit}",
                "samples": event.sample_count,
                "review_prompt": event.review_prompt,
            }
            for event in events
        ]
    )


def lap_summary(frame: pd.DataFrame) -> pd.DataFrame:
    """Build per-lap energy, performance and thermal summaries.

    Energy is integrated from recorded timestamps rather than a fixed logger
    frequency. Estimated drivetrain efficiency is a diagnostic indicator, not a
    calibrated component-efficiency measurement.
    """

    rows = []
    pack_power_kw = electrical_power_kw(frame)
    for lap, group in frame.groupby("lap", sort=True):
        mechanical_energy_kj = _integrate_signal_kj(group, group["power_kw"])
        electrical_energy_kj = _integrate_signal_kj(group, pack_power_kw)
        rows.append(
            {
                "lap": int(lap),
                "duration_s": float(group["time_s"].max() - group["time_s"].min()),
                "avg_power_kw": float(group["power_kw"].mean()),
                "peak_power_kw": float(group["power_kw"].max()),
                "max_motor_temp_c": float(group["motor_temp_c"].max()),
                "max_inverter_temp_c": float(group["inverter_temp_c"].max()),
                "min_pack_voltage_v": float(group["battery_voltage_v"].min()),
                "mechanical_energy_kj": mechanical_energy_kj,
                "electrical_energy_kj": electrical_energy_kj,
                "estimated_drivetrain_efficiency_pct": _efficiency_pct(
                    mechanical_energy_kj, electrical_energy_kj
                ),
            }
        )
    return pd.DataFrame(rows).round(2)
