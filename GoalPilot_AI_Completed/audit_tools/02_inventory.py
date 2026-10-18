"""Build a complete inventory of the workspace and the GoalPilot_AI project."""
import csv
import hashlib
import json
import os
from collections import defaultdict
from pathlib import Path

ROOT = Path(r"S:\fyp")
OUT = Path(r"S:\fyp\_audit")
OUT.mkdir(exist_ok=True)

SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".ipynb_checkpoints", "node_modules"}


def walk(base: Path):
    rows = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            p = Path(dirpath) / fn
            try:
                st = p.stat()
            except OSError:
                continue
            rows.append({
                "rel": str(p.relative_to(ROOT)),
                "size": st.st_size,
                "mtime": st.st_mtime,
                "ext": p.suffix.lower(),
            })
    return rows


def md5(p: Path, limit=None):
    h = hashlib.md5()
    try:
        with open(p, "rb") as f:
            while True:
                b = f.read(1 << 20)
                if not b:
                    break
                h.update(b)
    except OSError:
        return "ERR"
    return h.hexdigest()


def main():
    rows = walk(ROOT)
    print(f"TOTAL FILES: {len(rows)}  TOTAL MB: {sum(r['size'] for r in rows)/1e6:,.1f}")

    # ---- top-level view
    print()
    print("=" * 78)
    print("TOP-LEVEL ENTRIES")
    print("=" * 78)
    tops = defaultdict(lambda: [0, 0])
    for r in rows:
        top = r["rel"].split(os.sep)[0]
        tops[top][0] += 1
        tops[top][1] += r["size"]
    for k in sorted(tops, key=lambda x: -tops[x][1]):
        print(f"  {k:34s} files={tops[k][0]:<6} MB={tops[k][1]/1e6:>10,.2f}")

    # ---- largest files
    print()
    print("=" * 78)
    print("20 LARGEST FILES")
    print("=" * 78)
    for r in sorted(rows, key=lambda r: -r["size"])[:20]:
        print(f"  {r['size']/1e6:>9,.2f} MB  {r['rel']}")

    # ---- duplicate detection by (size) then hash
    print()
    print("=" * 78)
    print("DUPLICATE GROUPS (identical content, >=2 copies)")
    print("=" * 78)
    by_size = defaultdict(list)
    for r in rows:
        if r["size"] > 0:
            by_size[r["size"]].append(r)
    groups = []
    for size, items in by_size.items():
        if len(items) < 2:
            continue
        by_hash = defaultdict(list)
        for it in items:
            by_hash[md5(ROOT / it["rel"])].append(it)
        for h, its in by_hash.items():
            if len(its) > 1:
                groups.append((size, h, sorted(i["rel"] for i in its)))
    groups.sort(key=lambda g: -g[0] * len(g[2]))
    print(f"duplicate groups: {len(groups)}")
    wasted = sum(g[0] * (len(g[2]) - 1) for g in groups)
    print(f"redundant bytes : {wasted/1e6:,.2f} MB")
    for size, h, rels in groups[:40]:
        print(f"  size={size:,} copies={len(rels)}")
        for x in rels:
            print(f"      {x}")

    # ---- extension census
    print()
    print("=" * 78)
    print("EXTENSION CENSUS")
    print("=" * 78)
    ext = defaultdict(lambda: [0, 0])
    for r in rows:
        ext[r["ext"] or "(none)"][0] += 1
        ext[r["ext"] or "(none)"][1] += r["size"]
    for k in sorted(ext, key=lambda x: -ext[x][1])[:30]:
        print(f"  {k:14s} files={ext[k][0]:<6} MB={ext[k][1]/1e6:>10,.2f}")

    # ---- write csv
    csvp = OUT / "inventory_full.csv"
    with open(csvp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["rel", "size", "mtime", "ext"])
        w.writeheader()
        for r in sorted(rows, key=lambda r: r["rel"]):
            w.writerow(r)
    print()
    print("wrote", csvp)

    with open(OUT / "duplicates.json", "w", encoding="utf-8") as f:
        json.dump([{"size": s, "md5": h, "paths": p} for s, h, p in groups], f, indent=2)
    print("wrote", OUT / "duplicates.json")


if __name__ == "__main__":
    main()
