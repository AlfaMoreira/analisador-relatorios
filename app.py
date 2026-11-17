"""Entrada para empacotamento Windows."""
import sys

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--apply-update":
        from revisor.updates import apply_plan
        raise SystemExit(apply_plan(sys.argv[2]))
    else:
        from revisor.__main__ import main
        raise SystemExit(main())
