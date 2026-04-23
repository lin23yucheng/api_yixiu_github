import sys
from pathlib import Path


def _candidate_project_roots():
    current_root = Path(__file__).resolve().parent.parent
    candidates = [current_root]

    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "")
        exe_dir = Path(sys.executable).resolve().parent
        if meipass:
            candidates.insert(0, Path(meipass).resolve())
        candidates.insert(1, exe_dir)
        candidates.append(exe_dir.parent)

    seen = set()
    unique = []
    for path in candidates:
        path_str = str(path)
        if path_str not in seen:
            seen.add(path_str)
            unique.append(path)
    return unique


def get_resource_path(*parts: str) -> str:
    for root in _candidate_project_roots():
        candidate = root.joinpath(*parts)
        if candidate.exists():
            return str(candidate)
    return str(_candidate_project_roots()[0].joinpath(*parts))


def get_testdata_path(file_name: str) -> str:
    return get_resource_path("testdata", file_name)

