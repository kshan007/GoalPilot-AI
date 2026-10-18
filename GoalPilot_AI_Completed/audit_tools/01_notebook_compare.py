"""Compare the two RL PreCheck notebooks."""
import json
import sys
from pathlib import Path

import nbformat

PAIRS = [
    (r"S:\fyp\GoalPilot_RL_PreCheck.ipynb", "ROOT"),
    (r"S:\fyp\GoalPilot_AI\Copy of GoalPilot_RL_PreCheck.ipynb", "IN_FOLDER"),
]


def describe(path, tag):
    p = Path(path)
    print("=" * 74)
    print(f"[{tag}] {p}")
    if not p.exists():
        print("  NOT FOUND")
        return None
    st = p.stat()
    print(f"  size_bytes = {st.st_size:,}")
    print(f"  mtime      = {__import__('datetime').datetime.fromtimestamp(st.st_mtime)}")
    nb = nbformat.read(str(p), as_version=4)
    cells = nb.cells
    code = [c for c in cells if c.cell_type == "code"]
    md = [c for c in cells if c.cell_type == "markdown"]
    with_out = [c for c in code if c.get("outputs")]
    execs = [c.get("execution_count") for c in code]
    print(f"  nbformat   = {nb.nbformat}.{nb.nbformat_minor}")
    print(f"  cells      = {len(cells)} (code={len(code)}, md={len(md)})")
    print(f"  code_with_outputs = {len(with_out)}")
    print(f"  exec_counts = {execs}")
    ki = nb.metadata.get("kernelspec", {})
    print(f"  kernel     = {ki.get('name')} / {ki.get('display_name')}")
    print(f"  lang_ver   = {nb.metadata.get('language_info', {}).get('version')}")
    src_all = "\n".join(c.source for c in cells)
    imports = sorted({ln.strip() for ln in src_all.splitlines()
                      if ln.strip().startswith(("import ", "from "))})
    print(f"  nb total source chars = {len(src_all):,}")
    return {
        "tag": tag, "path": str(p), "cells": len(cells), "code": len(code),
        "md": len(md), "with_out": len(with_out), "execs": execs,
        "source_chars": len(src_all), "imports": imports,
        "src_all": src_all, "nb": nb,
    }


def main():
    infos = []
    for path, tag in PAIRS:
        i = describe(path, tag)
        if i:
            infos.append(i)

    if len(infos) == 2:
        a, b = infos
        print()
        print("=" * 74)
        print("SOURCE-LEVEL DIFF")
        print("=" * 74)
        sa, sb = a["src_all"], b["src_all"]
        print(f"identical_source = {sa == sb}")
        if sa != sb:
            la, lb = sa.splitlines(), sb.splitlines()
            print(f"lines: {a['tag']}={len(la)}  {b['tag']}={len(lb)}")
            import difflib
            d = list(difflib.unified_diff(la, lb, fromfile=a["tag"], tofile=b["tag"], lineterm="", n=1))
            print(f"diff_lines={len(d)}")
            for ln in d[:400]:
                print("  " + ln[:200])
            if len(d) > 400:
                print(f"  ... {len(d)-400} more diff lines")

        print()
        print("=" * 74)
        print("IMPORTS: only-in-ROOT / only-in-IN_FOLDER")
        print("=" * 74)
        ia, ib = set(a["imports"]), set(b["imports"])
        print("only ROOT:")
        for x in sorted(ia - ib):
            print("   -", x)
        print("only IN_FOLDER:")
        for x in sorted(ib - ia):
            print("   +", x)

        print()
        print("=" * 74)
        print("CODE CELL SOURCES (side by side, non-empty, truncated)")
        print("=" * 74)
        for i, (ca, cb) in enumerate(zip(
            [c for c in a["nb"].cells if c.cell_type == "code"],
            [c for c in b["nb"].cells if c.cell_type == "code"],
        )):
            same = ca.source == cb.source
            print(f"[{i}] same={same}  root_len={len(ca.source)} folder_len={len(cb.source)}")
            if not same:
                print("   ROOT  :", ca.source.strip().replace("\n", " | ")[:220])
                print("   FOLDER:", cb.source.strip().replace("\n", " | ")[:220])


if __name__ == "__main__":
    main()
