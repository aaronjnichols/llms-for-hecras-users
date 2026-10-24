"""Print Beaver Creek May '74 cross sections from HEC-RAS itself.

This Windows-only script drives the HEC-RAS 7.0.1 controller and the native
HEC-RAS plot dialogs. It does not redraw or reinterpret the cross sections.
HEC-RAS supplies each plot as a native enhanced metafile; Pillow only arranges
those native plots four-up on US Letter PDF pages.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import subprocess
import tempfile
import time
from ctypes import wintypes
from dataclasses import asdict, dataclass
from pathlib import Path

import win32com.client
from PIL import Image

HEC_RAS_PROG_ID = "RAS701.HECRASController"
HEC_RAS_VERSION = "7.0.1"
PROFILE_TEXT = "3 (May '74 flood)"
RIVER = "Beaver Creek"
REACH = "Kentwood"
FIRST_STATION = "5.99"

DEFAULT_PROJECT = Path(
    r"work\example_plans_20260812T020308Z\Example_Projects_7_0"
    r"\Applications Guide\Example 2 - Beaver Creek\BEAVCREK.prj"
)
DEFAULT_OUTPUT_DIR = Path("outputs/beaver_creek_may74_native_xs")

PLAN_OUTPUTS = (
    ("Press/Weir Method", "BEAVCREK_p01_press_weir_may74_native_xs.pdf", "BEAVCREK.p01.hdf"),
    ("Energy Method", "BEAVCREK_p02_energy_may74_native_xs.pdf", "BEAVCREK.p02.hdf"),
)

USER32 = ctypes.WinDLL("user32", use_last_error=True)
GDI32 = ctypes.WinDLL("gdi32", use_last_error=True)

WM_COMMAND = 0x0111
BM_CLICK = 0x00F5
BM_GETCHECK = 0x00F0
BST_CHECKED = 1
LB_GETCOUNT = 0x018B
LB_GETTEXT = 0x0189
LB_GETTEXTLEN = 0x018A
LB_SETSEL = 0x0185
LB_FINDSTRINGEXACT = 0x01A2
MF_BYPOSITION = 0x0400
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
CF_ENHMETAFILE = 14


USER32.GetClipboardData.restype = wintypes.HANDLE
GDI32.CopyEnhMetaFileW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR]
GDI32.CopyEnhMetaFileW.restype = wintypes.HANDLE
GDI32.DeleteEnhMetaFile.argtypes = [wintypes.HANDLE]
GDI32.DeleteEnhMetaFile.restype = wintypes.BOOL


@dataclass(frozen=True)
class PrintReceipt:
    hec_ras_version: str
    project_path: str
    plan_title: str
    result_hdf_path: str
    profile: str
    river: str
    reach: str
    native_locations: list[str]
    plots_per_page: int
    page_layout: str
    paper: str
    orientation: str
    mannings_n_enabled: bool
    native_plot_source: str
    pdf_path: str
    pdf_sha256: str
    generated_utc: str


def window_text(hwnd: int) -> str:
    length = USER32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length + 1)
    USER32.GetWindowTextW(hwnd, buffer, len(buffer))
    return buffer.value


def window_class(hwnd: int) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    USER32.GetClassNameW(hwnd, buffer, len(buffer))
    return buffer.value


def top_windows() -> list[int]:
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd: int, _lparam: int) -> bool:
        if USER32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True

    USER32.EnumWindows(callback, 0)
    return found


def child_windows(parent: int) -> list[int]:
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd: int, _lparam: int) -> bool:
        found.append(hwnd)
        return True

    USER32.EnumChildWindows(parent, callback, 0)
    return found


def wait_for_window(
    *,
    title: str | None = None,
    new_since: set[int] | None = None,
    timeout_s: float = 30.0,
) -> int:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        matches = top_windows()
        if title is not None:
            matches = [hwnd for hwnd in matches if window_text(hwnd) == title]
        if new_since is not None:
            matches = [hwnd for hwnd in matches if hwnd not in new_since]
        if len(matches) == 1:
            return matches[0]
        time.sleep(0.1)
    descriptions = [(window_text(hwnd), window_class(hwnd)) for hwnd in top_windows()]
    raise TimeoutError(
        f"Expected one window with title={title!r}; visible windows: {descriptions!r}"
    )


def wait_until_closed(hwnd: int, timeout_s: float = 10.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if not USER32.IsWindow(hwnd) or not USER32.IsWindowVisible(hwnd):
            return
        time.sleep(0.1)
    raise TimeoutError(f"Window did not close: {window_text(hwnd)!r}")


def find_child(parent: int, *, text: str, class_suffix: str | None = None) -> int:
    matches = [child for child in child_windows(parent) if window_text(child) == text]
    if class_suffix is not None:
        matches = [child for child in matches if window_class(child).endswith(class_suffix)]
    if len(matches) != 1:
        found = [(window_text(child), window_class(child)) for child in child_windows(parent)]
        raise RuntimeError(
            f"Expected one child text={text!r}, class suffix={class_suffix!r}; found {found!r}"
        )
    return matches[0]


def find_children_by_class(parent: int, class_suffix: str) -> list[int]:
    return [child for child in child_windows(parent) if window_class(child).endswith(class_suffix)]


def list_box_values(hwnd: int) -> list[str]:
    count = USER32.SendMessageW(hwnd, LB_GETCOUNT, 0, 0)
    values: list[str] = []
    for index in range(count):
        length = USER32.SendMessageW(hwnd, LB_GETTEXTLEN, index, 0)
        buffer = ctypes.create_unicode_buffer(length + 1)
        USER32.SendMessageW(hwnd, LB_GETTEXT, index, ctypes.byref(buffer))
        values.append(buffer.value)
    return values


def click(hwnd: int) -> None:
    USER32.SendMessageW(hwnd, BM_CLICK, 0, 0)


def set_checked(hwnd: int) -> None:
    if USER32.SendMessageW(hwnd, BM_GETCHECK, 0, 0) != BST_CHECKED:
        click(hwnd)
    if USER32.SendMessageW(hwnd, BM_GETCHECK, 0, 0) != BST_CHECKED:
        raise RuntimeError(f"Could not check {window_text(hwnd)!r}")


def menu_commands(hwnd: int) -> dict[str, int]:
    commands: dict[str, int] = {}

    def walk(menu: int, prefix: list[str]) -> None:
        for position in range(USER32.GetMenuItemCount(menu)):
            buffer = ctypes.create_unicode_buffer(512)
            USER32.GetMenuStringW(menu, position, buffer, len(buffer), MF_BYPOSITION)
            label = " ".join(buffer.value.replace("&", "").split())
            submenu = USER32.GetSubMenu(menu, position)
            path = [*prefix, label]
            if submenu:
                walk(submenu, path)
            elif label:
                commands[" > ".join(path)] = USER32.GetMenuItemID(menu, position)

    menu = USER32.GetMenu(hwnd)
    if not menu:
        raise RuntimeError("Cross Section window has no menu")
    walk(menu, [])
    return commands


def command_starting_with(commands: dict[str, int], prefix: str) -> int:
    matches = [command_id for path, command_id in commands.items() if path.startswith(prefix)]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one menu command starting with {prefix!r}: {commands!r}")
    return matches[0]


def post_menu_command(hwnd: int, command_id: int) -> None:
    if not USER32.PostMessageW(hwnd, WM_COMMAND, command_id, 0):
        raise ctypes.WinError(ctypes.get_last_error())


def select_only_may74(plot: int, commands: dict[str, int]) -> None:
    existing = set(top_windows())
    post_menu_command(plot, command_starting_with(commands, "Options > Profiles"))
    dialog = wait_for_window(title="Select Profiles", new_since=existing)
    children = child_windows(dialog)
    list_boxes = find_children_by_class(dialog, "ListBox")
    click(find_child(dialog, text="Clear All", class_suffix="CommandButton"))
    time.sleep(0.2)
    available = next((item for item in list_boxes if PROFILE_TEXT in list_box_values(item)), None)
    if available is None:
        raise RuntimeError(f"Profile not found: {PROFILE_TEXT!r}")
    selected = next(item for item in list_boxes if not list_box_values(item))
    profile_buffer = ctypes.create_unicode_buffer(PROFILE_TEXT)
    index = USER32.SendMessageW(available, LB_FINDSTRINGEXACT, -1, ctypes.byref(profile_buffer))
    if index < 0:
        raise RuntimeError(f"Profile not found: {PROFILE_TEXT!r}")
    USER32.SendMessageW(available, LB_SETSEL, 1, index)
    arrow = next(
        child
        for child in children
        if window_class(child).endswith("CommandButton") and not window_text(child)
    )
    click(arrow)
    time.sleep(0.2)
    if list_box_values(selected) != [PROFILE_TEXT]:
        raise RuntimeError(f"May '74 profile selection failed: {list_box_values(selected)!r}")
    click(find_child(dialog, text="OK", class_suffix="CommandButton"))
    wait_until_closed(dialog)


def ensure_mannings_n(plot: int, commands: dict[str, int]) -> bool:
    existing = set(top_windows())
    post_menu_command(plot, command_starting_with(commands, "Options > Variables"))
    dialog = wait_for_window(new_since=existing)
    checkbox = find_child(dialog, text="Mannings n", class_suffix="CheckBox")
    set_checked(checkbox)
    enabled = USER32.SendMessageW(checkbox, BM_GETCHECK, 0, 0) == BST_CHECKED
    click(find_child(dialog, text="OK", class_suffix="CommandButton"))
    wait_until_closed(dialog)
    return enabled


def discover_cross_section_locations(
    plot: int, commands: dict[str, int]
) -> tuple[list[str], list[str]]:
    existing = set(top_windows())
    post_menu_command(plot, command_starting_with(commands, "File > Print Multiple"))
    dialog = wait_for_window(title="Multiple Location Print - Select Locations", new_since=existing)
    children = child_windows(dialog)
    click(find_child(dialog, text="Clear Selected List", class_suffix="CommandButton"))
    available = next(
        child
        for child in find_children_by_class(dialog, "ListBox")
        if USER32.GetDlgCtrlID(child) == 11
    )
    selected = next(
        child
        for child in find_children_by_class(dialog, "ListBox")
        if USER32.GetDlgCtrlID(child) == 14
    )
    all_rs_buffer = ctypes.create_unicode_buffer("(All RS)")
    index = USER32.SendMessageW(available, LB_FINDSTRINGEXACT, -1, ctypes.byref(all_rs_buffer))
    USER32.SendMessageW(available, LB_SETSEL, 1, index)
    arrow = next(
        child
        for child in children
        if window_class(child).endswith("CommandButton") and not window_text(child)
    )
    click(arrow)
    time.sleep(0.2)
    labels = [value.rstrip() for value in list_box_values(selected)]
    stations = [value.split()[-1].rstrip("*") for value in labels]
    if not stations:
        raise RuntimeError("HEC-RAS returned no cross-section locations")
    click(find_child(dialog, text="Cancel", class_suffix="CommandButton"))
    wait_until_closed(dialog)
    return stations, labels


def empty_clipboard() -> None:
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if USER32.OpenClipboard(0):
            try:
                if not USER32.EmptyClipboard():
                    raise ctypes.WinError(ctypes.get_last_error())
            finally:
                USER32.CloseClipboard()
            return
        time.sleep(0.05)
    raise TimeoutError("Could not open the Windows clipboard")


def capture_plot_metafile(plot: int, commands: dict[str, int], output_emf: Path) -> None:
    if not USER32.SetWindowPos(
        plot,
        0,
        0,
        0,
        900,
        1120,
        SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE,
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    time.sleep(0.2)
    empty_clipboard()
    sequence = USER32.GetClipboardSequenceNumber()
    post_menu_command(plot, command_starting_with(commands, "File > Copy Plot to Clipboard"))
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        if USER32.GetClipboardSequenceNumber() != sequence and USER32.IsClipboardFormatAvailable(
            CF_ENHMETAFILE
        ):
            break
        time.sleep(0.05)
    else:
        raise TimeoutError("HEC-RAS did not place an enhanced metafile on the clipboard")

    if not USER32.OpenClipboard(0):
        raise ctypes.WinError(ctypes.get_last_error())
    copied = None
    try:
        source = USER32.GetClipboardData(CF_ENHMETAFILE)
        if not source:
            raise ctypes.WinError(ctypes.get_last_error())
        copied = GDI32.CopyEnhMetaFileW(source, str(output_emf))
        if not copied:
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        if copied:
            GDI32.DeleteEnhMetaFile(copied)
        USER32.CloseClipboard()
    if not output_emf.is_file() or output_emf.stat().st_size == 0:
        raise RuntimeError(f"HEC-RAS metafile was not saved: {output_emf}")


def wait_for_completed_file(path: Path, timeout_s: float = 120.0) -> None:
    deadline = time.monotonic() + timeout_s
    previous_size = -1
    stable_checks = 0
    while time.monotonic() < deadline:
        if path.exists():
            size = path.stat().st_size
            stable_checks = stable_checks + 1 if size == previous_size and size > 0 else 0
            previous_size = size
            if stable_checks >= 3:
                return
        time.sleep(0.5)
    raise TimeoutError(f"Output file was not completed: {path}")


def print_metafiles_to_pdf(emf_paths: list[Path], output_pdf: Path) -> None:
    dpi = 300
    page_size = (round(8.5 * dpi), round(11 * dpi))
    margin = round(0.20 * dpi)
    gutter = round(0.08 * dpi)
    cell_size = (
        (page_size[0] - 2 * margin - gutter) // 2,
        (page_size[1] - 2 * margin - gutter) // 2,
    )
    pages: list[Image.Image] = []
    for page_start in range(0, len(emf_paths), 4):
        page = Image.new("RGB", page_size, "white")
        for offset, emf_path in enumerate(emf_paths[page_start : page_start + 4]):
            with Image.open(emf_path) as native_plot:
                native_plot.load(dpi=dpi)
                plot_image = native_plot.convert("RGB")
            plot_image.thumbnail(cell_size, Image.Resampling.LANCZOS)
            row, column = divmod(offset, 2)
            cell_left = margin + column * (cell_size[0] + gutter)
            cell_top = margin + row * (cell_size[1] + gutter)
            left = cell_left + (cell_size[0] - plot_image.width) // 2
            top = cell_top + (cell_size[1] - plot_image.height) // 2
            page.paste(plot_image, (left, top))
        pages.append(page)
    if not pages:
        raise RuntimeError("No HEC-RAS native plot metafiles were captured")
    pages[0].save(
        output_pdf,
        "PDF",
        resolution=dpi,
        save_all=True,
        append_images=pages[1:],
        quality=95,
        subsampling=0,
    )
    wait_for_completed_file(output_pdf)
    if output_pdf.read_bytes()[:5] != b"%PDF-":
        raise RuntimeError(f"Output is not a PDF: {output_pdf}")


def ras_is_running() -> bool:
    result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq Ras.exe", "/FO", "CSV", "/NH"],
        check=True,
        capture_output=True,
        text=True,
    )
    return '"Ras.exe"' in result.stdout


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_paths(project: Path, output_dir: Path, overwrite: bool) -> None:
    repo = Path.cwd().resolve()
    work_root = (repo / "work").resolve()
    project = project.resolve()
    output_dir = output_dir.resolve()
    if work_root not in project.parents:
        raise ValueError(f"Project must be a disposable copy under {work_root}; got {project}")
    if not project.is_file():
        raise FileNotFoundError(project)
    for _plan, filename, result_hdf in PLAN_OUTPUTS:
        hdf = project.with_name(result_hdf)
        if not hdf.is_file():
            raise FileNotFoundError(f"Required computed result is missing: {hdf}")
        pdf = output_dir / filename
        if pdf.exists() and not overwrite:
            raise FileExistsError(f"Output already exists; use --overwrite: {pdf}")


def run(project: Path, output_dir: Path, overwrite: bool) -> list[Path]:
    project = project.resolve()
    output_dir = output_dir.resolve()
    validate_paths(project, output_dir, overwrite)
    if ras_is_running():
        raise RuntimeError("Close all HEC-RAS windows before running this automation")
    output_dir.mkdir(parents=True, exist_ok=True)
    if overwrite:
        for _plan, filename, _hdf in PLAN_OUTPUTS:
            (output_dir / filename).unlink(missing_ok=True)

    controller = win32com.client.Dispatch(HEC_RAS_PROG_ID)
    outputs: list[Path] = []
    receipts: list[PrintReceipt] = []
    temp_root = Path.cwd() / "tmp" / "pdfs"
    temp_root.mkdir(parents=True, exist_ok=True)
    try:
        controller.ShowRas()
        controller.Project_Open(str(project))
        for plan_title, filename, result_hdf in PLAN_OUTPUTS:
            selected = controller.PlanOutput_SetCurrent(plan_title)
            if selected is False:
                raise RuntimeError(f"HEC-RAS did not select plan {plan_title!r}")

            controller.PlotXS(RIVER, REACH, FIRST_STATION)
            plot = wait_for_window(title="Cross Section")
            commands = menu_commands(plot)
            stations, locations = discover_cross_section_locations(plot, commands)
            post_menu_command(plot, command_starting_with(commands, "File > Exit"))
            wait_until_closed(plot)

            output_pdf = output_dir / filename
            n_checks: list[bool] = []
            with tempfile.TemporaryDirectory(
                prefix=f"{project.stem}_{plan_title.lower().replace('/', '_').replace(' ', '_')}_",
                dir=temp_root,
            ) as temp_dir:
                metafiles: list[Path] = []
                for position, station in enumerate(stations, start=1):
                    controller.PlotXS(RIVER, REACH, station)
                    plot = wait_for_window(title="Cross Section")
                    commands = menu_commands(plot)
                    select_only_may74(plot, commands)
                    n_checks.append(ensure_mannings_n(plot, commands))
                    emf_path = Path(temp_dir) / f"{position:02d}_{station.replace('.', '_')}.emf"
                    capture_plot_metafile(plot, commands, emf_path)
                    metafiles.append(emf_path)
                    post_menu_command(plot, command_starting_with(commands, "File > Exit"))
                    wait_until_closed(plot)
                print_metafiles_to_pdf(metafiles, output_pdf)

            outputs.append(output_pdf)
            receipts.append(
                PrintReceipt(
                    hec_ras_version=HEC_RAS_VERSION,
                    project_path=str(project),
                    plan_title=plan_title,
                    result_hdf_path=str(project.with_name(result_hdf)),
                    profile="May '74 flood",
                    river=RIVER,
                    reach=REACH,
                    native_locations=[value.rstrip() for value in locations],
                    plots_per_page=4,
                    page_layout="2 rows x 2 columns",
                    paper="US Letter (8.5 x 11 in)",
                    orientation="portrait",
                    mannings_n_enabled=all(n_checks),
                    native_plot_source="HEC-RAS Copy Plot to Clipboard (enhanced metafile)",
                    pdf_path=str(output_pdf),
                    pdf_sha256=sha256(output_pdf),
                    generated_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                )
            )
    finally:
        controller.QuitRas()

    receipt_path = output_dir / "native_print_receipt.json"
    receipt_path.write_text(
        json.dumps([asdict(receipt) for receipt in receipts], indent=2) + os.linesep,
        encoding="utf-8",
    )
    return outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=DEFAULT_PROJECT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    if os.name != "nt":
        raise SystemExit("This automation requires Windows and HEC-RAS 7.0.1")
    args = parse_args()
    for output in run(args.project, args.output_dir, args.overwrite):
        print(output)


if __name__ == "__main__":
    main()
