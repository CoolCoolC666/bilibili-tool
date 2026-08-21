"""v3.0.7 mock 端到端测试：批量抓取 + 打开文件夹"""
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
from unittest.mock import patch, MagicMock


# Mock：AuthorDetailExporter.export 返回假 xlsx
def fake_export(self, csv_path, *, max_count=None, output_dir=None):
    """Mock：不真调 B 站，返回 2 行结果。"""
    up_uid = "999"
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    od = output_dir or self.output_dir
    os.makedirs(od, exist_ok=True)
    xlsx_path = os.path.abspath(os.path.join(od, f"author_detail_{up_uid}_{ts}.xlsx"))
    # 写个空 xlsx 标记
    with open(xlsx_path, "wb") as f:
        f.write(b"mock xlsx content for " + csv_path.encode("utf-8"))
    time.sleep(0.3)  # 模拟抓取耗时
    return xlsx_path, 2, 0  # (path, ok, fail)


patcher = patch(
    "bilibili_tool.author_detail.AuthorDetailExporter.export",
    new=fake_export,
)
patcher.start()


def req(method, path, body=None, port=5058):
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

    # 准备测试 CSV 文件
    test_files = ["author_test_v307_1.csv", "author_test_v307_2.csv", "author_test_v307_3.csv"]
    for f in test_files:
        with open(os.path.join("output", f), "w", encoding="utf-8-sig", newline="") as fp:
            fp.write("bvid,aid,title,duration,pubdate,tid,up_uid\n")
            fp.write("BV1xx1,1,test1,100,2026-01-01 00:00:00,0,999\n")
            fp.write("BV1xx2,2,test2,200,2026-01-01 00:00:00,0,999\n")
    print(f"已准备 {len(test_files)} 个测试 CSV")

    port = 5058
    print(f"启动 Flask (mock) 端口 {port} ...")
    proc = start_flask(port)
    if not proc:
        print("Flask 启动失败")
        sys.exit(1)
    print("Flask 启动成功\n")
    try:
        # 测试 1: 批量抓 3 个 CSV
        print(f"=== 1. 批量抓 {len(test_files)} 个 CSV ===")
        code, body = req("POST", "/api/author/detail/batch", {
            "filenames": test_files,
            "max": 5, "delay": 0.1, "timeout": 5, "retry": 0,
        }, port=port)
        print(f"status={code}")
        data = json.loads(body)
        print(f"job_id: {data.get('job_id')}, total_files: {data.get('total_files')}")
        job_id = data["job_id"]
        print()

        # 轮询进度
        print("=== 2. 轮询进度 ===")
        for i in range(20):
            time.sleep(0.5)
            code, body = req("GET", f"/api/author/detail/progress?job_id={job_id}", port=port)
            if code != 200:
                print(f"  轮询失败: {body}")
                break
            d = json.loads(body)
            sub_pct = round(d["sub_done"] / d["sub_total"] * 100) if d.get("sub_total") else 0
            print(f"  [{i+1:2d}] status={d['status']}, "
                  f"sub={d.get('sub_done')}/{d.get('sub_total')} ({sub_pct}%), "
                  f"cur={d.get('processed')}/{d.get('total', '?')}, "
                  f"OK={d.get('ok_count')}, FAIL={d.get('fail_count')}, "
                  f"xlsx_n={len(d.get('xlsx_paths', []))}")
            if d["status"] in ("done", "error"):
                if d["status"] == "done":
                    print(f"\n  生成的 XLSX:")
                    for xp in d.get("xlsx_paths", []):
                        print(f"    {xp}")
                break
        print()

        # 测试 3: 单个文件（向后兼容）
        print("=== 3. 单个文件（向后兼容）===")
        code, body = req("POST", "/api/author/detail", {
            "filename": test_files[0],
            "max": 5, "delay": 0.1, "timeout": 5, "retry": 0,
        }, port=port)
        data = json.loads(body)
        print(f"status={code}, job_id: {data.get('job_id')}")
        print()

        # 测试 4: 打开文件夹（只在 Windows 测试 subprocess）
        print("=== 4. 打开文件管理器 ===")
        code, body = req("POST", "/api/open-output-folder", {}, port=port)
        data = json.loads(body)
        print(f"status={code}, ok={data.get('ok')}, opened={data.get('opened')}")
        print()

        # 测试 5: 打开 + 高亮文件
        print("=== 5. 打开并高亮文件 ===")
        code, body = req("POST", "/api/open-output-folder", {
            "select": test_files[0],
        }, port=port)
        data = json.loads(body)
        print(f"status={code}, ok={data.get('ok')}, opened={data.get('opened')}")

    finally:
        proc.terminate()
        proc.wait(timeout=5)
        # 清理 mock 写的 xlsx
        for xlsx in os.listdir("output/xlsx"):
            if "999_" in xlsx:
                try:
                    os.remove(os.path.join("output/xlsx", xlsx))
                except OSError:
                    pass
        # 清理测试 CSV
        for f in test_files:
            try:
                os.remove(os.path.join("output", f))
            except OSError:
                pass
        patcher.stop()
        print("\nFlask 已停，测试文件已清理")
