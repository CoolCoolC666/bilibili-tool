"""v3.0.8 测试 open-folder 智能定位（不 mock subprocess，让 explorer 真启动但不阻塞）"""
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error


def req(method, path, body=None, port=5060):
    url = f"http://127.0.0.1:{port}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    r = urllib.request.Request(url, data=data, method=method,
                              headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


def start_flask(port):
    proc = subprocess.Popen(
        [sys.executable, "run_web.py", "--port", str(port)],
        cwd=".",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    for _ in range(30):
        time.sleep(0.5)
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1)
            return proc
        except Exception:
            continue
    return proc


if __name__ == "__main__":
    os.chdir(r"E:\桌面\暑期可做\22-Bilibili Tool完善\Bilibili_tool\bilibili_tool_v2")

    port = 5060
    proc = start_flask(port)
    if not proc:
        print("Flask 启动失败")
        sys.exit(1)
    print(f"Flask 启动 端口 {port}（explorer 会被真调用，但不阻塞）\n")
    try:
        # 测试 1: provider 列表（含 data_limit）
        print("=== 1. /api/author/providers（含 data_limit）===")
        code, body = req("GET", "/api/author/providers", port=port)
        d = json.loads(body)
        for p in d["providers"]:
            dl = (p.get('data_limit') or '(none)').encode('ascii', 'replace').decode('ascii')[:60]
            print(f"  {p['id']}: data_limit={dl!r}")
        print()

        # 测试 2: 不指定 select → 打开 DEFAULT_OUT
        print("=== 2. open-folder 无 select ===")
        code, body = req("POST", "/api/open-output-folder", {}, port=port)
        d = json.loads(body)
        print(f"  status={code}, opened={d.get('opened')}, highlight={d.get('highlight')}")
        print()

        # 测试 3: select 是 CSV → 打开 DEFAULT_OUT
        print("=== 3. open-folder select=author_53456_xxx.csv（CSV）===")
        # 先创建测试文件
        csv_path = os.path.join("output", "author_test_53456_xxx.csv")
        with open(csv_path, "w") as f:
            f.write("test")
        code, body = req("POST", "/api/open-output-folder", {
            "select": "author_test_53456_xxx.csv",
        }, port=port)
        d = json.loads(body)
        print(f"  status={code}, opened={d.get('opened')}, highlight={d.get('highlight')}")
        os.remove(csv_path)
        print()

        # 测试 4: select 是 xlsx/... 路径 → 打开 DEFAULT_XLSX
        print("=== 4. open-folder select=xlsx/author_detail_xxx.xlsx ===")
        os.makedirs("output/xlsx", exist_ok=True)
        xlsx_path = os.path.join("output/xlsx", "test_xxx.xlsx")
        with open(xlsx_path, "wb") as f:
            f.write(b"test xlsx")
        code, body = req("POST", "/api/open-output-folder", {
            "select": "xlsx/test_xxx.xlsx",
        }, port=port)
        d = json.loads(body)
        print(f"  status={code}, opened={d.get('opened')}, highlight={d.get('highlight')}")
        os.remove(xlsx_path)
        print()

        # 测试 5: 边界 - 只给文件名（无 xlsx/ 前缀）但 .xlsx 后缀
        print("=== 5. open-folder select=test_xxx.xlsx（无 xlsx/ 前缀）===")
        with open(xlsx_path, "wb") as f:
            f.write(b"test xlsx")
        code, body = req("POST", "/api/open-output-folder", {
            "select": "test_xxx.xlsx",
        }, port=port)
        d = json.loads(body)
        print(f"  status={code}, opened={d.get('opened')}, highlight={d.get('highlight')}")
        os.remove(xlsx_path)

    finally:
        proc.terminate()
        proc.wait(timeout=5)
        print("\nFlask 已停")
