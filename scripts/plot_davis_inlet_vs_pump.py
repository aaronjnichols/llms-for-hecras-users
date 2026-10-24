"""Plot aggregate pipe-network inlet flow against Davis pump discharge."""

from __future__ import annotations

from pathlib import Path

import h5py
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
HDF = (
    REPO
    / "work"
    / "example_plans_20260812T020308Z"
    / "Example_Projects_7_0"
    / "Pipes"
    / "Davis"
    / "DavisStormSystem.p02.hdf"
)
OUTPUT = REPO / "outputs" / "davis_pump_analysis"
TIME_SERIES = "Results/Unsteady/Output/Output Blocks/DSS Hydrograph Output/Unsteady Time Series"
INLET_FLOW = f"{TIME_SERIES}/Pipe Networks/Davis/Nodes/Top + Side Inlet Flow"
PUMP_RESULTS = f"{TIME_SERIES}/Pumping Stations/Pump Station #1/Structure Variables"
CUBIC_FEET_PER_ACRE_FOOT = 43_560.0


def decode(value: object) -> str:
    if isinstance(value, bytes | np.bytes_):
        return bytes(value).decode("utf-8", errors="replace").strip()
    return str(value).strip()


def cumulative_volume_acre_ft(timestamps: pd.DatetimeIndex, flow_cfs: np.ndarray) -> np.ndarray:
    """Integrate a saved flow series with the trapezoidal rule."""
    interval_seconds = np.array(
        [
            (timestamps[index] - timestamps[index - 1]).total_seconds()
            for index in range(1, len(timestamps))
        ]
    )
    interval_volume_cubic_ft = 0.5 * (flow_cfs[:-1] + flow_cfs[1:]) * interval_seconds
    return np.concatenate(([0.0], np.cumsum(interval_volume_cubic_ft) / CUBIC_FEET_PER_ACRE_FOOT))


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)

    with h5py.File(HDF, "r") as hdf:
        timestamps = pd.to_datetime(
            [decode(value) for value in hdf[f"{TIME_SERIES}/Time Date Stamp"][:]],
            format="%d%b%Y %H:%M:%S",
        )
        node_flow_cfs = hdf[INLET_FLOW][:]
        pump_variables = hdf[PUMP_RESULTS][:]

        if node_flow_cfs.shape != (len(timestamps), 133):
            raise ValueError(f"Unexpected inlet-flow shape: {node_flow_cfs.shape}")
        if decode(hdf[INLET_FLOW].attrs["Units"]) != "cfs":
            raise ValueError("The inlet-flow dataset is not recorded in cfs.")

    net_inlet_cfs = node_flow_cfs.sum(axis=1)
    pump_flow_cfs = pump_variables[:, 0]
    cumulative_net_inlet_acre_ft = cumulative_volume_acre_ft(timestamps, net_inlet_cfs)
    cumulative_pumped_acre_ft = cumulative_volume_acre_ft(timestamps, pump_flow_cfs)
    net_inlet_volume_acre_ft = cumulative_net_inlet_acre_ft[-1]
    pumped_volume_acre_ft = cumulative_pumped_acre_ft[-1]
    inlet_peak = int(np.argmax(net_inlet_cfs))
    pump_peak = int(np.argmax(pump_flow_cfs))

    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "aggregate_net_inlet_flow_cfs": net_inlet_cfs,
            "pump_discharge_cfs": pump_flow_cfs,
            "cumulative_net_inlet_volume_acre_ft": cumulative_net_inlet_acre_ft,
            "cumulative_pumped_volume_acre_ft": cumulative_pumped_acre_ft,
        }
    )
    frame.to_csv(OUTPUT / "davis_inlet_vs_pump.csv", index=False)

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
    fig, ax = plt.subplots(figsize=(12, 6.8))
    ax.plot(
        timestamps,
        net_inlet_cfs,
        color="#1f6f8b",
        linewidth=2.4,
        label="Net flow through 133 surface inlets into pipe network",
    )
    ax.plot(
        timestamps,
        pump_flow_cfs,
        color="#d97706",
        linewidth=2.4,
        label="Pump Station #1 discharge",
    )
    ax.fill_between(
        timestamps,
        pump_flow_cfs,
        net_inlet_cfs,
        where=net_inlet_cfs >= pump_flow_cfs,
        color="#8ec5d6",
        alpha=0.25,
        interpolate=True,
        label="Inlet flow exceeds pump flow",
    )

    for index, values, color, label_offset in [
        (inlet_peak, net_inlet_cfs, "#1f6f8b", (14, -38)),
        (pump_peak, pump_flow_cfs, "#d97706", (12, -34)),
    ]:
        ax.scatter(timestamps[index], values[index], s=55, color=color, zorder=5)
        ax.annotate(
            f"{values[index]:.2f} cfs\n{timestamps[index]:%b %d, %H:%M}",
            xy=(timestamps[index], values[index]),
            xytext=label_offset,
            textcoords="offset points",
            color=color,
            fontsize=9.5,
            fontweight="bold",
            arrowprops={"arrowstyle": "-", "color": color, "lw": 1},
        )

    fig.suptitle(
        "Davis storm system: aggregate inlet flow and pump discharge",
        x=0.08,
        y=0.975,
        ha="left",
        fontsize=16,
        fontweight="bold",
    )
    fig.text(
        0.08,
        0.925,
        "Positive node flows enter the pipe network; negative node flows represent surcharge.",
        color="#475569",
        fontsize=10,
    )
    fig.text(
        0.08,
        0.89,
        f"Volume under each curve: {net_inlet_volume_acre_ft:.2f} acre-ft net through inlets  |  "
        f"{pumped_volume_acre_ft:.2f} acre-ft pumped to DS Channel",
        color="#334155",
        fontsize=10,
        fontweight="bold",
    )
    ax.set_ylabel("Flow, cfs")
    ax.set_xlabel("Simulation time")
    ax.set_ylim(bottom=0)
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=4))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d\n%H:%M"))
    ax.grid(axis="y", alpha=0.25)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="upper right", frameon=False)
    fig.text(
        0.08,
        0.025,
        "HEC-RAS 7.0.1 | Original hypothetical rainfall | 10-minute saved output\n"
        "Aggregate inlet flow is the signed sum of Top + Side Inlet Flow across all 133 nodes.",
        fontsize=9,
        color="#475569",
    )
    fig.subplots_adjust(left=0.08, right=0.97, top=0.84, bottom=0.17)
    fig.savefig(OUTPUT / "davis_inlet_vs_pump.png", dpi=180, facecolor="white")
    fig.savefig(OUTPUT / "davis_inlet_vs_pump.pdf", facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    main()
