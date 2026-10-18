"""Extract the RL PreCheck notebook into analyzable artifacts."""
import json
import re
from pathlib import Path

import nbformat

NB = Path(r"S:\fyp\GoalPilot_RL_PreCheck.ipynb")
OUT = Path(r"S:\fyp\_audit")
OUT.mkdir(exist_ok=True)

nb = nbformat.read(str(NB), as_version=4)
cells = nb.cells


def out_summary(cell):
    parts = []
    for o in cell.get("outputs", []):
        t = o.get("output_type")
        if t == "stream":
            txt = "".join(o.get("text", []))
            parts.append(("stream:" + o.get("name", "?"), txt))
        elif t in ("execute_result", "display_data"):
            d = o.get("data", {})
            if "text/plain" in d:
                parts.append((t + ":text", "".join(d["text/plain"])))
            if "image/png" in d:
                parts.append((t + ":png", f"<{len(d['image/png'])} b64 chars>"))
        elif t == "error":
            parts.append(("error", "\n".join(o.get("traceback", []))))
    return parts


# ---- full source dump
lines = []
index = []
for i, c in enumerate(cells):
    tag = f"# ===== CELL {i} =====  type={c.cell_type}  exec={c.get('execution_count')}"
    lines.append(tag)
    if c.cell_type == "code":
        lines.append(c.source)
    else:
        lines.append("# (markdown)")
    lines.append("")
    first = c.source.strip().splitlines()
    index.append({
        "i": i, "type": c.cell_type, "exec": c.get("execution_count"),
        "chars": len(c.source),
        "head": (first[0][:120] if first else ""),
        "n_outputs": len(c.get("outputs", [])),
    })

(OUT / "rL_precheck_flat.py").write_text("\n".join(lines), encoding="utf-8")

# ---- cell index with outputs
rep = []
for i, c in enumerate(cells):
    rep.append(f"[{i:03d}] exec={c.get('execution_count')} chars={len(c.source):5d} outs={len(c.get('outputs', []))}")
    src = c.source.strip().splitlines()
    for ln in src[:12]:
        rep.append("      | " + ln[:170])
    if len(src) > 12:
        rep.append(f"      | ... (+{len(src)-12} lines)")
    for kind, txt in out_summary(c):
        if kind.endswith("png"):
            rep.append(f"      OUT[{kind}] {txt}")
        else:
            tl = txt.rstrip().splitlines()
            rep.append(f"      OUT[{kind}] ({len(tl)} lines)")
            for ln in tl[:8]:
                rep.append("      > " + ln[:170])
            if len(tl) > 8:
                rep.append(f"      > ... (+{len(tl)-8} lines)")
    rep.append("")
(OUT / "rL_precheck_cells.txt").write_text("\n".join(rep), encoding="utf-8")

# ---- outputs only (for evidence)
outlines = []
for i, c in enumerate(cells):
    for kind, txt in out_summary(c):
        outlines.append(f"### CELL {i} [{kind}]")
        outlines.append(txt if not kind.endswith("png") else txt)
        outlines.append("")
(OUT / "rL_precheck_outputs.txt").write_text("\n".join(outlines), encoding="utf-8")

print("cells:", len(cells))
print("wrote:", OUT / "rL_precheck_flat.py", (OUT / 'rL_precheck_flat.py').stat().st_size)
print("wrote:", OUT / "rL_precheck_cells.txt", (OUT / 'rL_precheck_cells.txt').stat().st_size)
print("wrote:", OUT / "rL_precheck_outputs.txt", (OUT / 'rL_precheck_outputs.txt').stat().st_size)

# ---- quick keyword census
src_all = "\n".join(c.source for c in cells if c.cell_type == "code")
kws = ["goalpilot_env", "GoalPilotEnv", "PPO(", "stable_baselines3", "pulp", "linprog",
       "savings_only", "mixed", "baseline", "reward", "double count", "double_count",
       "goal_target", "COLAB", "gym.make", "DummyVecEnv", "EvalCallback", "total_budget",
       "contribution", "borrow", "loan", "goal_funding", "earmark"]
print()
print("KEYWORD CENSUS")
for k in kws:
    n = len(re.findall(re.escape(k), src_all, flags=re.IGNORECASE))
    print(f"  {k:22s} {n}")
