# Repository skills

Place repo-scoped Codex skills at:

```text
.agents/skills/<skill-name>/SKILL.md
```

Use a skill for a repeatable student task with a clear trigger, inputs, procedure, safety
boundary, and output. Keep stable project-wide conventions in the root `AGENTS.md` instead.

Do not create a broad "HEC-RAS helper" skill. Prefer one focused workflow after the lesson has
been performed and reviewed manually—for example, inspecting an HDF inventory, comparing two
plans, or producing a run-health evidence packet. Instruction-only skills are the default; add
scripts or references only when they make the workflow more reliable.

