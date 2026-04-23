"""
PyInstaller 打包脚本
将 client_gui.py 打包为 Windows EXE，包含所有必要的资源文件
"""
import subprocess
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SPEC_PATH = os.path.join(PROJECT_ROOT, "yixiu_client.spec")

# 统一走 spec，避免 CLI 参数和 spec 漂移导致打包行为不一致
pyinstaller_cmd = [
    "pyinstaller",
    "--noconfirm",           # 覆盖已有的 dist/build
    "--clean",               # 清理临时文件
    SPEC_PATH,
]

print("=" * 80)
print("开始打包 EXE...")
print("=" * 80)
if not os.path.exists(SPEC_PATH):
    print(f"未找到 spec 文件: {SPEC_PATH}")
    sys.exit(1)
print("\n命令：")
print(" ".join(pyinstaller_cmd))
print("\n" + "=" * 80)

# 执行打包
result = subprocess.run(pyinstaller_cmd, cwd=PROJECT_ROOT)

if result.returncode == 0:
    print("\n" + "=" * 80)
    print("✓ 打包成功！")
    print("=" * 80)
    exe_path = os.path.join(PROJECT_ROOT, "dist", "yixiu_client", "yixiu_client.exe")
    print(f"\nEXE 文件位置：")
    print(f"  {exe_path}")
    print(f"\n可以直接双击运行：")
    print(f"  {exe_path}")
else:
    print("\n" + "=" * 80)
    print("✗ 打包失败！")
    print("=" * 80)
    sys.exit(1)

