from pathlib import Path

import pytest

from scripts.run_all_example_plans import build_execution_batches, classify_project


def make_project(
    corpus_root: Path,
    project_relative_path: str,
    flow_files: list[str],
) -> dict[str, object]:
    project_path = Path(project_relative_path)
    plans = []
    for number, flow_file in enumerate(flow_files, start=1):
        plan_relative_path = project_path.with_suffix(f".p{number:02d}")
        plan_path = corpus_root / plan_relative_path
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(f"Plan Title=Test\nFlow File={flow_file}\n", encoding="utf-8")
        plans.append(
            {
                "plan_relative_path": plan_relative_path.as_posix(),
                "plan_number": f"{number:02d}",
            }
        )
    return {
        "project_relative_path": project_path.as_posix(),
        "project_title": project_path.stem,
        "plans": plans,
    }


def test_build_execution_batches_keeps_projects_together(tmp_path: Path) -> None:
    projects = [
        make_project(tmp_path, "Steady/A.prj", ["f01"] * 6),
        make_project(tmp_path, "Steady/B.prj", ["f01"] * 5),
        make_project(tmp_path, "Unsteady/C.prj", ["u01"] * 6),
        make_project(tmp_path, "2D Unsteady Flow Hydraulics/D.prj", ["u01"] * 2),
        make_project(tmp_path, "1D Sediment Transport/E.prj", ["q01"]),
        make_project(tmp_path, "Pipes/F.prj", ["u01"]),
    ]
    inventory_data = {
        "projects": projects,
        "plan_count": sum(len(project["plans"]) for project in projects),
    }

    batches = build_execution_batches(inventory_data, tmp_path, steady_cap=10, unsteady_cap=5)

    assert [batch["execution_batch_id"] for batch in batches] == [
        "B001",
        "B002",
        "B003",
        "B004",
        "B005",
        "B006",
    ]
    assert [batch["category"] for batch in batches] == [
        "steady",
        "steady",
        "unsteady_1d",
        "unsteady_2d",
        "sediment",
        "pipes",
    ]
    assert [batch["plan_count"] for batch in batches] == [6, 5, 6, 2, 1, 1]
    assert batches[2]["over_cap"] is True
    assert all(batch["project_count"] == 1 for batch in batches)


def test_classify_project_rejects_missing_flow_file(tmp_path: Path) -> None:
    project = make_project(tmp_path, "Steady/A.prj", ["f01"])
    plan_path = tmp_path / Path(project["plans"][0]["plan_relative_path"])
    plan_path.write_text("Plan Title=Test\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Unrecognized Flow File"):
        classify_project(project, tmp_path)
