"""Hydrate a tier twice into fresh directories and require identical bytes (DDR-0004)."""

import filecmp
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
tier = sys.argv[1] if len(sys.argv) > 1 else "conformance"
with tempfile.TemporaryDirectory() as tmp:
    outs = [os.path.join(tmp, name) for name in ("a", "b")]
    for out in outs:
        subprocess.run([sys.executable, os.path.join(HERE, "corpus.py"), "hydrate", "--tier", tier, "--output", out], check=True)
        subprocess.run([sys.executable, os.path.join(HERE, "corpus.py"), "verify", "--root", out], check=True)
    files = 0
    for dirpath, _, names in os.walk(outs[0]):
        for name in names:
            a = os.path.join(dirpath, name)
            b = os.path.join(outs[1], os.path.relpath(a, outs[0]))
            if not filecmp.cmp(a, b, shallow=False):
                sys.exit("hydrate-twice: %s differs" % os.path.relpath(a, outs[0]))
            files += 1
    count_b = sum(len(n) for _, _, n in os.walk(outs[1]))
    if files != count_b:
        sys.exit("hydrate-twice: file counts differ (%d vs %d)" % (files, count_b))
    print("hydrate-twice: %s tier identical across two runs (%d files)" % (tier, files))
