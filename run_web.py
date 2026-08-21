"""Web 应用启动脚本。

用法：
    python run_web.py                 # 默认 http://127.0.0.1:5050
    python run_web.py --port 8080     # 自定义端口
    python run_web.py --host 0.0.0.0  # 局域网可访问（注意：同网段都能访问）
"""
from __future__ import annotations

import argparse


def main() -> int:
    parser = argparse.ArgumentParser(description="B 站视频信息抓取工具 - Web 版")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1）")
    parser.add_argument("--port", type=int, default=5050, help="端口（默认 5050）")
    parser.add_argument("--debug", action="store_true", help="打开 Flask debug 模式")
    args = parser.parse_args()

    from web.app import app
    # Windows GBK 终端下 emoji 会炸，全部改成 ASCII 字符
    print("=" * 60)
    print(f"[Web]  B 站视频信息抓取工具  Web 版")
    print(f"[URL]  http://{args.host}:{args.port}")
    print(f"[Cache] data/cache.json")
    print(f"[Output] output/")
    print("=" * 60)
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
