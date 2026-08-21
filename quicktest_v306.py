"""v3.0.6 mock 端到端测试：profile 批量抓取 + 进度 + 导出"""
import json
import time
import os
import sys


# 关键：先 patch UapisCnProvider.fetch_user_info 避免真实调 uapis
from unittest.mock import patch, MagicMock


def fake_fetch_user_info(self, uid):
    """Mock：返回固定的 profile 数据。"""
    fake_data = {
        1: {"mid": 1, "name": "bishi", "level": 6, "sex": "保密",
             "sign": "哔哩哔哩 - ( ゜- ゜)つロ 乾杯~", "vip_type": 2, "vip_status": 1,
             "following": 148, "follower": 228929, "archive_count": 44, "article_count": 12},
        53456: {"mid": 53456, "name": "Warma", "level": 6, "sex": "男",
                "sign": "微剧透警告", "vip_type": 2, "vip_status": 1,
                "following": 89, "follower": 5125917, "archive_count": 262, "article_count": 0},
        483307278: {"mid": 483307278, "name": "Shuakami", "level": 6, "sex": "保密",
                    "sign": "THE FINALS 玩家", "vip_type": 0, "vip_status": 0,
                    "following": 50, "follower": 1356, "archive_count": 27, "article_count": 0},
        1751577265: {"mid": 1751577265, "name": "春山响hibiki", "level": 6, "sex": "女",
                     "sign": "来听我唱歌吧", "vip_type": 2, "vip_status": 1,
                     "following": 23, "follower": 123456, "archive_count": 50, "article_count": 0},
    }
    if uid in fake_data:
        return fake_data[uid]
    # 不存在的 UID 模拟 404
    from bilibili_tool.uapi import UapiNotFoundError
    raise UapiNotFoundError(f"user {uid} not found")


# 在 import 之前 patch
patch_target = "bilibili_tool.uapi.UapisCnProvider.fetch_user_info"
patcher = patch(patch_target, new=fake_fetch_user_info)
patcher.start()


# 启动 Flask（用 subprocess 在另一个端口）
import subprocess
import urllib.request
import urllib.error


def start_flask(port):
    proc = subprocess.Popen(
        [sys.executable, "run_web.py", "--port", str(port)],
        cwd=".",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    # 等启动
    for _ in range(30):
        time.sleep(0.5)
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1)
            return proc
        except Exception:
            continue
    return proc


def req(method, path, body=None, port=5057):
    url = f"http://127.0.0.1:{port}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    r = urllib.request.Request(url, data=data, method=method,
                              headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


if __name__ == "__main__":
    os.chdir(r"E:\桌面\暑期可做\22-Bilibili Tool完善\Bilibili_tool\bilibili_tool_v2")
    port = 5057
    print(f"启动 Flask (mock 模式) 端口 {port} ...")
    proc = start_flask(port)
    if not proc:
        print("Flask 启动失败")
        sys.exit(1)
    print("Flask 启动成功\n")
    try:
        # 测试 1: 启动批量抓取
        print("=== 1. 启动批量抓取（4 个 UP 主 + 1 个不存在）===")
        code, body = req("POST", "/api/author/profile", {
            "inputs": "1\n53456\n483307278\n1751577265\n999999999",  # 999999999 触发 404
            "delay": 0.1,
        }, port=port)
        print(f"status={code}")
        data = json.loads(body)
        print(f"job_id: {data.get('job_id')}, total: {data.get('total')}")
        job_id = data["job_id"]
        print()

        # 轮询进度
        print("=== 2. 轮询进度 ===")
        for i in range(15):
            time.sleep(0.5)
            code, body = req("GET", f"/api/author/profile/progress?job_id={job_id}", port=port)
            if code != 200:
                print(f"  轮询失败: {body}")
                break
            d = json.loads(body)
            pct = round(d["processed"] / d["total"] * 100) if d["total"] else 0
            print(f"  [{i+1:2d}] status={d['status']}, {d['processed']}/{d['total']} "
                  f"({pct}%), OK={d['ok_count']}, FAIL={d['fail_count']}, "
                  f"current={d.get('current', '')[:20]!r}")
            if d["status"] in ("done", "error"):
                print()
                print(f"  csv_path: {d.get('csv_path')}")
                print(f"  xlsx_path: {d.get('xlsx_path')}")
                if d["status"] == "error":
                    print(f"  error: {d.get('error')}")
                print()
                print("  log_tail:")
                for line in d.get("log_tail", []):
                    print(f"    {line}")
                break
        print()

        # 测试 3: 列文件
        print("=== 3. /api/author/profile/files ===")
        code, body = req("GET", "/api/author/profile/files", port=port)
        data = json.loads(body)
        print(f"files: {len(data['files'])}")
        for f in data["files"][:3]:
            print(f"  {f['name']} ({f['size']}B)")

    finally:
        proc.terminate()
        proc.wait(timeout=5)
        patcher.stop()
        print("\nFlask 已停")
