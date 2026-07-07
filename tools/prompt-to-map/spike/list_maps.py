"""SPIKE helper: list map names inside a .BIG archive."""
import sys
sys.path.insert(0, sys.path[0])
from big_extract import list_entries

data = open(sys.argv[1], "rb").read()
maps = [(n, s) for (n, o, s) in list_entries(data) if n.lower().endswith(".map")]
names = {}
for n, s in maps:
    base = n.replace("\\", "/").split("/")[-1][:-4]
    names[base] = s
for nm in sorted(names):
    print(f"{names[nm]:>9,}  {nm}")
print("----- total:", len(names))
