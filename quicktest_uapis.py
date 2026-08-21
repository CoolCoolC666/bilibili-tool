"""v2.10.0+ 真实 UAPI 测试脚本（访客模式）。

测试当前网络 + 设备对 uapis.cn 的连通性。
用最便宜的端点（userinfo 4 积分 + archives 4 积分），
先验证连通性再考虑深度测试。

UID 选 B 站官方账户 2 = bishi（永久存在，不会被风控）。
"""
import os
import sys
import json
import time

# 强制无环境变量（测纯访客模式）
os.environ.pop("UAPIS_CN_API_KEY", None)

from bilibili_tool.uapi import (
    UapisCnProvider,
    UapiError,
    UapiRateLimitError,
    UapiAuthError,
    UapiNotFoundError,
)


def section(title: str) -> None:
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


def main() -> int:
    print("UAPI 访客模式真实测试")
    print(f"  Python: {sys.version.split()[0]}")
    print(f"  时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # 1. 初始化访客模式
    section("1. 初始化访客模式（不传 key）")
    try:
        provider = UapisCnProvider()  # 访客
    except Exception as e:
        print(f"  [FAIL] 初始化失败: {e}")
        return 1
    print(f"  [OK] provider = {provider.name}")
    print(f"  [OK] mode = {provider.mode}")
    print(f"  [OK] is_visitor = {provider.is_visitor}")
    print(f"  [OK] session headers (Authorization) = "
          f"{'有' if 'Authorization' in provider.sess.headers else '无'}")

    # 2. 测 userinfo（最便宜，单次 4 积分）
    section("2. 真实调用 fetch_user_info(2)  # B 站官方账户 bishi")
    try:
        info = provider.fetch_user_info(2)
    except UapiRateLimitError as e:
        print(f"  [FAIL] 限流: {e}")
        return 2
    except UapiError as e:
        print(f"  [FAIL] 错误: {e}")
        return 2
    print(f"  [OK] 返回字段: {list(info.keys())}")
    print(f"  [OK] name = {info.get('name')!r}")
    print(f"  [OK] level = {info.get('level')}")
    print(f"  [OK] follower = {info.get('follower')}")
    print(f"  [OK] archive_count = {info.get('archive_count')}")

    # 3. 测 archives（核心端点，单次 4 积分）
    section("3. 真实调用 fetch_author_archives(2, max_count=3)  # 拿 3 条投稿")
    try:
        archives = provider.fetch_author_archives(2, max_count=3)
    except UapiRateLimitError as e:
        print(f"  [FAIL] 限流: {e}")
        return 3
    except UapiError as e:
        print(f"  [FAIL] 错误: {e}")
        return 3
    print(f"  [OK] 拿到 {len(archives)} 条投稿")
    for i, arc in enumerate(archives, 1):
        print(f"  [{i}] bvid={arc.get('bvid')} title={arc.get('title', '')[:50]!r}")
        print(f"      pubdate={arc.get('pubdate')} duration={arc.get('duration')}s play={arc.get('play')}")
        print(f"      _source={arc.get('_source')}")

    # 4. 测 videoinfo（单视频详情）
    if archives:
        first_bvid = archives[0].get("bvid")
        section(f"4. 真实调用 fetch_video_info(bvid='{first_bvid}')")
        try:
            vinfo = provider.fetch_video_info(bvid=first_bvid)
        except UapiError as e:
            print(f"  [FAIL] 错误: {e}")
            return 4
        print(f"  [OK] title = {vinfo.get('title', '')[:50]!r}")
        print(f"  [OK] stat.view = {vinfo.get('stat', {}).get('view')}")
        print(f"  [OK] stat.like = {vinfo.get('stat', {}).get('like')}")
        print(f"  [OK] duration = {vinfo.get('duration')}s")
        print(f"  [OK] owner.name = {vinfo.get('owner', {}).get('name')}")

    # 5. 测 404（不存在的 UID）
    section("5. 真实调用 fetch_user_info(99999999)  # 测 404 错误码")
    try:
        provider.fetch_user_info(99999999)
        print("  [WARN] 期望抛 NotFound 但返回成功")
    except UapiNotFoundError as e:
        print(f"  [OK] UapiNotFoundError 正确抛出: {e}")
    except UapiError as e:
        print(f"  [WARN] 抛了其他错误: {type(e).__name__}: {e}")

    # 6. 健康检查（默认用 fetch_author_archives(2, max_count=1) 试探）
    section("6. health_check() 默认实现")
    try:
        ok = provider.health_check()
        print(f"  [OK] health_check 返回 {ok}")
    except Exception as e:
        print(f"  [INFO] health_check 抛错: {e}")

    print()
    print("=" * 60)
    print("  [完成] 访客模式真实测试 OK")
    print(f"  积分消耗估算: 4 (userinfo) + 4 (archives) + 4 (videoinfo) = 12 积分")
    print(f"  访客月额度: 1500 积分（按 IP 计算）")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"\n[CRASH] 未捕获异常: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(99)
