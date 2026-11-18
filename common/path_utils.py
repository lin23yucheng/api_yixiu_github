"""
路径工具模块 - 用于处理项目资源和数据文件的路径查询

该模块主要用于：
1. 定位项目根目录（支持开发环境和打包后的应用）
2. 获取项目中各类资源文件的路径
3. 处理PyInstaller等打包工具生成的冻结应用的特殊路径情况
"""

import sys
from pathlib import Path


def _candidate_project_roots():
    """
    获取候选的项目根目录列表

    该函数会根据不同的运行环境返回可能的项目根目录：
    - 开发环境：当前文件所在目录的父目录
    - 打包应用（PyInstaller）：考虑临时文件夹、exe所在目录等位置
    """
    # 开发环境中，项目根目录是此文件所在目录的父目录的父目录
    current_root = Path(__file__).resolve().parent.parent
    candidates = [current_root]

    # 检测是否由PyInstaller等工具冻结打包（frozen = True表示已打包）
    if getattr(sys, "frozen", False):
        # _MEIPASS 是PyInstaller生成的临时文件夹路径
        meipass = getattr(sys, "_MEIPASS", "")
        # 可执行文件所在的目录
        exe_dir = Path(sys.executable).resolve().parent

        # 优先级顺序添加备选路径：
        if meipass:
            candidates.insert(0, Path(meipass).resolve())  # 最高优先级：PyInstaller临时目录
        candidates.insert(1, exe_dir)  # 次优先级：exe所在目录
        candidates.append(exe_dir.parent)  # 低优先级：exe父目录

    # 去重处理 - 确保列表中不包含重复的路径
    seen = set()
    unique = []
    for path in candidates:
        path_str = str(path)
        if path_str not in seen:
            seen.add(path_str)
            unique.append(path)
    return unique


def get_resource_path(*parts: str) -> str:
    """
    获取项目资源文件的绝对路径

    该函数会遍历候选的项目根目录，找到第一个存在的资源路径。
    如果都不存在，则返回第一个候选目录下的路径（用于创建新文件时）。
    """
    # 遍历所有候选的项目根目录，找到实际存在的路径
    for root in _candidate_project_roots():
        candidate = root.joinpath(*parts)
        if candidate.exists():
            return str(candidate)

    # 如果文件不存在，返回第一个候选目录下的路径（通常用于创建新文件）
    return str(_candidate_project_roots()[0].joinpath(*parts))


def get_testdata_path(file_name: str) -> str:
    """
    获取测试数据文件的绝对路径

    便捷函数，用于获取 testdata 目录下的文件路径。
    """
    return get_resource_path("testdata", file_name)

