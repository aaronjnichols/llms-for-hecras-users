"""Check launchers without changing system Python or running models."""

import json
import os
import subprocess
from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts import course_setup as setup

REPO = Path(__file__).resolve().parents[1]
POWERSHELL = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"


def ps(code):
    script = str(REPO / "scripts/setup_course.ps1").replace("'", "''")
    result = subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            f". '{script}' -FunctionsOnly; try {{ {code} }} catch {{ Write-Error $_; exit 1 }}; exit 0",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_bootstrap_selection_and_registered_rejection():
    assert "good" in ps("""
function Get-PythonInfo($Path) { if ($Path -eq 'bad') { throw 'bad' }; return @{version='3.13.15'} }
$chosen = Select-CoursePython @(@{Path='bad';Registered=$false}, @{Path='good';Registered=$true})
if ($chosen -ne 'good') { throw 'Selection differs' }
try { Select-CoursePython @(@{Path='good';Registered=$true}, @{Path='bad';Registered=$true}); throw 'ACCEPTED' }
catch { if ($_.Exception.Message -eq 'ACCEPTED') { throw } }
Write-Output $chosen
""")


@pytest.mark.parametrize(
    "status,subject", [("Invalid", "O=Python Software Foundation"), ("Valid", "O=Other")]
)
def test_installer_signature_rejection(status, subject):
    ps(f"""
function Get-FileHash {{ return @{{Hash='edec09c4853aeae9ac36efb8c9f95b6b8e2fee65eee56d9767a8b7c69c574403'}} }}
function Get-AuthenticodeSignature {{ return @{{Status='{status}';SignerCertificate=@{{Subject='{subject}'}}}} }}
try {{ Assert-Installer 'fixture'; throw 'ACCEPTED' }} catch {{ if ($_.Exception.Message -eq 'ACCEPTED') {{ throw }} }}
""")


def test_installer_hash_and_arguments():
    ps("""
function Get-FileHash { return @{Hash='wrong'} }
function Get-AuthenticodeSignature { throw 'Signature must not run' }
try { Assert-Installer 'fixture'; throw 'ACCEPTED' } catch { if ($_.Exception.Message -notmatch 'SHA-256') { throw } }
$argsList = Get-InstallerArguments 'C:\\path with spaces' 'C:\\log path'
foreach ($required in @('/norestart','Include_pip=1','Include_test=0','Include_launcher=0','InstallAllUsers=0','PrependPath=0','AssociateFiles=0')) {
if ($argsList -notcontains $required) { throw "Missing $required" }
}
if ($argsList -notcontains 'TargetDir="C:\\path with spaces"') { throw 'Target quoting differs' }
""")


def test_failure_propagation_and_partial_venv(tmp_path):
    root = str(tmp_path).replace("'", "''")
    ps(f"""
function fakePython {{ $global:LASTEXITCODE = 17 }}
try {{ Invoke-CourseStep fakePython @('test'); throw 'ACCEPTED' }} catch {{ if ($_.Exception.Message -notmatch '17') {{ throw }} }}
$null = New-Item -ItemType Directory -Path '{root}\\.venv'
try {{ Get-CourseVenv '{root}' 'DO-NOT-RUN'; throw 'ACCEPTED' }} catch {{ if ($_.Exception.Message -notmatch 'incomplete') {{ throw }} }}
""")


def test_linked_output_rejection(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "outputs"
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True
    )
    if result.returncode:
        ps("""
function Test-Path { return $true }
function Get-Item { return @{Attributes=[IO.FileAttributes]::ReparsePoint} }
try { Assert-PlainPath 'C:\\fixture\\outputs'; throw 'ACCEPTED' }
catch { if ($_.Exception.Message -notmatch 'linked path') { throw } }
""")
    else:
        try:
            ps(
                f"try {{ Assert-PlainPath '{link}'; throw 'ACCEPTED' }} catch {{ if ($_.Exception.Message -notmatch 'linked path') {{ throw }} }}"
            )
        finally:
            link.rmdir()


def test_archive_revision_without_git(tmp_path, monkeypatch):
    (tmp_path / ".git_archival.txt").write_text("a" * 40 + "\n")
    monkeypatch.setattr(setup.subprocess, "run", lambda *a, **k: pytest.fail("Git must not run"))
    assert setup.provenance(tmp_path) == {
        "revision": "a" * 40,
        "method": "git archive export-subst",
    }


@pytest.mark.parametrize("failure", [False, True])
def test_run_all_order_and_summary(tmp_path, monkeypatch, failure):
    monkeypatch.setattr(setup, "runtime", lambda root: {})
    monkeypatch.setattr(setup, "provenance", lambda root: {"revision": "test"})
    calls = []

    def run(root, model, ras_exe, timeout):
        calls.append(("run", model, timeout))
        output = root / "outputs" / model
        output.mkdir(parents=True)
        setup.save_json(
            output / "run.json", {"project": "work/project.prj", "result": "work/result.hdf"}
        )
        return output

    def check(root, output):
        calls.append(("check", output.name))
        if failure:
            raise ValueError("Fixture check failure")

    monkeypatch.setattr(setup, "run", run)
    monkeypatch.setattr(setup, "check", check)
    if failure:
        with pytest.raises(ValueError, match="Fixture check failure"):
            setup.run_all(tmp_path, Path("Ras.exe"))
    else:
        setup.run_all(tmp_path, Path("Ras.exe"))
    assert calls[:2] == [("run", "beaver-creek", 900), ("check", "beaver-creek")]
    assert len(calls) == (2 if failure else 4)
    summary = next((tmp_path / "outputs").glob("lesson00_*/run-all.json"))
    record = json.loads(summary.read_text())
    assert record["success"] is not failure
    assert len(record["models"]) == (1 if failure else 2)
    text = (summary.parent / "FIRST_RUN_RESULTS.txt").read_text()
    assert ("FAIL" if failure else "PASS") in text
    assert "Work project: work/project.prj" in text
    assert "Result HDF: work/result.hdf" in text
    assert record["models"][0]["checks_passed"] is not failure


@pytest.mark.parametrize(
    "field,value",
    [
        ("implementation", "PyPy"),
        ("version", "3.12.9"),
        ("bits", 32),
        ("gil", False),
        ("conda", True),
    ],
)
def test_interpreter_details_rejected(field, value):
    info = {
        "implementation": "CPython",
        "version": "3.13.15",
        "bits": 64,
        "gil": True,
        "conda": False,
    }
    info[field] = value
    payload = json.dumps(info)
    ps(f"""
function Test-Path {{ return $true }}
function fixturePython {{ $global:LASTEXITCODE=0; return '{payload}' }}
try {{ Get-PythonInfo 'fixturePython'; throw 'ACCEPTED' }}
catch {{ if ($_.Exception.Message -notmatch 'standard CPython') {{ throw }} }}
""")


def test_real_course_interpreter():
    exe = REPO / ".venv/Scripts/python.exe"
    assert "3.13." in ps(f"(Get-PythonInfo '{exe}').version")


def test_cmd_launchers_no_pause_and_exit_codes(tmp_path):
    root = tmp_path / "course with spaces"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts/setup_course.ps1").write_text("exit 23\n")
    for name, expected in (("Setup Course.cmd", 23), ("Run Models.cmd", 1)):
        launcher = root / name
        launcher.write_bytes((REPO / name).read_bytes())
        result = subprocess.run(
            ["cmd", "/c", str(launcher), "--no-pause"], capture_output=True, text=True, timeout=15
        )
        assert result.returncode == expected, result.stdout + result.stderr
        assert "Press any key" not in result.stdout


def test_venv_system_packages_rejected(tmp_path):
    venv = tmp_path / ".venv"
    venv.mkdir()
    (venv / "pyvenv.cfg").write_text("include-system-site-packages = true\n")
    ps(
        f"try {{ Get-CourseVenv '{tmp_path}' 'DO-NOT-RUN'; throw 'ACCEPTED' }} catch {{ if ($_.Exception.Message -notmatch 'system packages') {{ throw }} }}"
    )


def test_poisoned_pip_and_python_settings_cannot_redirect_install(tmp_path, monkeypatch):
    python = REPO / ".venv/Scripts/python.exe"
    monkeypatch.setenv("TEMP", str(tmp_path))
    monkeypatch.setenv("TMP", str(tmp_path))
    venv = tmp_path / "isolated course"
    subprocess.run([str(python), "-I", "-m", "venv", str(venv)], check=True, capture_output=True)
    venv_python = venv / "Scripts/python.exe"
    wheel = tmp_path / "course_pip_probe-1.0-py3-none-any.whl"
    with ZipFile(wheel, "w") as archive:
        archive.writestr("course_pip_probe.py", "VALUE = 42\n")
        archive.writestr(
            "course_pip_probe-1.0.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: course-pip-probe\nVersion: 1.0\n",
        )
        archive.writestr(
            "course_pip_probe-1.0.dist-info/WHEEL",
            "Wheel-Version: 1.0\nGenerator: course test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        archive.writestr("course_pip_probe-1.0.dist-info/RECORD", "")
    target = tmp_path / "forbidden target"
    prefix = tmp_path / "forbidden prefix"
    root = tmp_path / "forbidden root"
    config_target = tmp_path / "forbidden config target"
    config = tmp_path / "poison.ini"
    config.write_text(f"[install]\ntarget = {config_target}\n")
    site_config = venv / "pip.ini"
    site_config.write_text(config.read_text())
    for key, value in {
        "PIP_TARGET": str(target),
        "PIP_PREFIX": str(prefix),
        "PIP_ROOT": str(root),
        "PIP_USER": "true",
        "PIP_CONFIG_FILE": str(config),
        "PYTHONHOME": str(tmp_path / "invalid Python home"),
        "PYTHONPATH": str(tmp_path / "invalid module path"),
        "PYTHONUSERBASE": str(tmp_path / "forbidden user base"),
    }.items():
        monkeypatch.setenv(key, value)
    before = dict(os.environ)
    # PIP_USER also selects the user file for the pip config command.
    config_env = dict(os.environ)
    config_env.pop("PIP_USER")
    # Check that this process supplies poisoned pip settings to the child.
    raw = subprocess.run(
        [str(venv_python), "-E", "-m", "pip", "config", "list"],
        check=True,
        capture_output=True,
        text=True,
        env=config_env,
    )
    assert "forbidden target" in raw.stdout and "forbidden config target" in raw.stdout
    (tmp_path / "local_sibling.py").write_text("VALUE = 17\n")
    probe_script = tmp_path / "probe_script.py"
    probe_script.write_text(
        "import local_sibling, course_pip_probe; assert local_sibling.VALUE == 17; assert course_pip_probe.VALUE == 42\n"
    )
    ps(f"""
Set-CoursePipEnvironment
if ($env:PIP_CONFIG_FILE -cne 'nul' -or $env:PIP_REQUIRE_VIRTUALENV -ne 'true') {{ throw 'pip guard missing' }}
if (Test-Path Env:PYTHONHOME) {{ throw 'Python override remains' }}
Invoke-CourseStep '{venv_python}' @('-m','pip','install','--no-index','--no-deps','--no-cache-dir','--disable-pip-version-check','{wheel}')
Invoke-CourseStep '{venv_python}' @('{probe_script}')
""")
    assert (venv / "Lib/site-packages/course_pip_probe.py").is_file()
    for forbidden in (target, prefix, root, config_target, tmp_path / "forbidden user base"):
        assert not forbidden.exists()
    assert dict(os.environ) == before
    assert site_config.read_text() == config.read_text()


def test_run_all_cli_completion_points_to_readable_summary(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(setup.sys, "argv", ["course_setup.py", "run-all"])
    summary = tmp_path / "run-all.json"
    monkeypatch.setattr(setup, "run_all", lambda root, ras_exe: summary)
    assert setup.main() == 0
    output = capsys.readouterr().out
    assert f"Models complete. Read {tmp_path / 'FIRST_RUN_RESULTS.txt'}" in output
    assert "run-all.json" not in output


def test_models_cmd_ignores_python_overrides_and_keeps_local_imports(tmp_path):
    root = tmp_path / "model launcher with spaces"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    subprocess.run(
        [
            str(REPO / ".venv/Scripts/python.exe"),
            "-I",
            "-m",
            "venv",
            "--without-pip",
            str(root / ".venv"),
        ],
        check=True,
        capture_output=True,
    )
    launcher = root / "Run Models.cmd"
    launcher.write_bytes((REPO / "Run Models.cmd").read_bytes())
    (scripts / "neighbor.py").write_text("VALUE = 42\n")
    (scripts / "course_setup.py").write_text(
        "import neighbor, sys; assert neighbor.VALUE == 42; assert sys.argv[1:] == ['run-all']; print('MODEL LAUNCHER CHECK PASSED')\n"
    )
    env = dict(os.environ)
    env.update(PYTHONHOME=str(root / "invalid home"), PYTHONPATH=str(root / "invalid modules"))
    result = subprocess.run(
        ["cmd", "/c", str(launcher), "--no-pause"],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MODEL LAUNCHER CHECK PASSED" in result.stdout
    assert "Press any key" not in result.stdout
