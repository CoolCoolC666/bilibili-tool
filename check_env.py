"""环境健康检查：检测本项目依赖是否齐全。

用法：
    py -3.13 check_env.py

输出：
    - Python 版本
    - 关键包是否装好 + 版本
    - 缺哪个包提示一键安装命令
"""
from __future__ import annotations

import subprocess
import sys
from importlib.metadata import version as pkg_version, PackageNotFoundError

# 本项目关键依赖
REQUIRED = {
    "requests": ">=2.28",
    "openpyxl": ">=3.0",
    "flask": ">=2.0",
}


def check_one(name: str, spec: str) -> tuple:
    """返回 (status, version_str)：
    - ('ok', '2.31.0')
    - ('missing', None)
    - ('no_version_check', '2.31.0')  # 包装了但没写 spec
    """
    try:
        v = pkg_version(name)
    except PackageNotFoundError:
        return ("missing", None)
    return ("ok", v)


def parse_spec(s: str) -> tuple:
    """'>=2.28' -> ('>=', '2.28')"""
    import re
    m = re.match(r"^(>=|>|<=|<|==|!=)(.+)$", s.strip())
    if m:
        return (m.group(1), m.group(2).strip())
    return (None, s.strip())


def version_ge(installed: str, required: str) -> bool:
    """简化版 >= 比较（a.b.c 形式）。"""
    def parts(v):
        return [int(x) for x in re.findall(r"\d+", v)]
    import re
    iv, rv = parts(installed), parts(required)
    # 补齐长度
    while len(iv) < len(rv):
        iv.append(0)
    while len(rv) < len(iv):
        rv.append(0)
    return iv >= rv


def main() -> int:
    print("=" * 60)
    print(f"Python: {sys.version}")
    print(f"Executable: {sys.executable}")
    print("=" * 60)
    print()

    missing = []
    bad_version = []

    for name, spec in REQUIRED.items():
        op, req_v = parse_spec(spec)
        status, inst_v = check_one(name, spec)
        if status == "missing":
            print(f"  [X] {name:12s}  未安装")
            missing.append(name)
        else:
            if op == ">=" and not version_ge(inst_v, req_v):
                print(f"  [!] {name:12s}  {inst_v} (要求 {spec}, 不满足)")
                bad_version.append((name, inst_v, spec))
            else:
                print(f"  [OK] {name:12s}  {inst_v}")

    print()
    if not missing and not bad_version:
        print("OK: 所有依赖齐全。")
        return 0

    if missing:
        print(f"[!] 缺 {len(missing)} 个包，一键安装：")
        print(f"    {sys.executable} -m pip install {' '.join(missing)}")
    if bad_version:
        print(f"[!] {len(bad_version)} 个包版本不满足：")
        for name, iv, spec in bad_version:
            print(f"    - {name}: 当前 {iv}, 要求 {spec}")
    return 1


if __name__ == "__main__":
    import re
    sys.exit(main())
