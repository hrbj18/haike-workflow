# OpenMontage

**MANDATORY: Read `AGENT_GUIDE.md` before responding to ANY user message.**

Do not act on the user's request until you have read AGENT_GUIDE.md.
It contains routing rules that determine your first action based on what the user asked.
Skipping it WILL cause you to take the wrong action.

For new, changed or reviewed video templates, read `../Haike-Videohub/agent-runbooks/视频模板编写标准.md` and the matching template runbook before implementation or production.

If the user says the exact Chinese call sign **「模板图文视频」**, after reading
`AGENT_GUIDE.md` immediately load `../Haike-Videohub/agent-runbooks/模板图文视频.md`.
That exact call sign wins over generic video-type inference. Do not route it to
window-remake, material-remake, or the generic agent-native production line.

For repeated cross-repository operations, after reading the guide, use `../Haike-Videohub/agent-runbooks/README.md` when that sibling repository exists. Read the matching runbook and verify live state. Report new evidence as a proposal; edit the shared runbook only when explicitly assigned knowledge-base maintenance and after checking its governance rules.
