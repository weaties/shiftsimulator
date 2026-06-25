"""Run every ``test_*`` function in this directory without needing pytest.

    python tests/run_all.py

(``pytest`` also works if you have it installed.) The ``validate-physics``
skill uses this so the model can check the simulator anywhere.
"""
import importlib
import os
import sys
import traceback

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "src"))


def main() -> int:
    modules = [f[:-3] for f in os.listdir(HERE)
               if f.startswith("test_") and f.endswith(".py")]
    sys.path.insert(0, HERE)
    passed = failed = 0
    failures = []
    for modname in sorted(modules):
        mod = importlib.import_module(modname)
        for name in sorted(dir(mod)):
            if not name.startswith("test_"):
                continue
            fn = getattr(mod, name)
            if not callable(fn):
                continue
            try:
                fn()
                passed += 1
                print(f"  PASS {modname}.{name}")
            except Exception as e:  # noqa: BLE001
                failed += 1
                failures.append((f"{modname}.{name}", e, traceback.format_exc()))
                print(f"  FAIL {modname}.{name}: {e}")
    print(f"\n{passed} passed, {failed} failed")
    for name, _e, tb in failures:
        print(f"\n--- {name} ---\n{tb}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
