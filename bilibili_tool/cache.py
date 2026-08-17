"""JSON 缓存 + 断点续传 + 字段新鲜度。

设计哲学：
- B 站数据是"实时更新"的——抓一次播放量 1000，几小时后可能 5000
- 所以 cache 不能无限保留。需要按字段类型区分：
  * 静态字段（标题、UP主、发布时间、时长...）：视频发布后基本不变 → 永远 cache
  * 动态字段（播放、点赞、收藏...）：实时变 → 按 max_age 过期
  * 失败状态（not_found / failed）：视频失效不会"复活" → 永远 cache

使用：
  cache = Cache("data/cache.json")

  # 默认：静态永远，动态 1h 内
  cached = cache.get_fresh(info) or fetcher.fetch_with_retry(target)

  # 自定义：静态永远，动态 24h 内
  cached = cache.get_fresh(info, max_age_seconds=86400) or ...

  # 强制不缓存
  cached = cache.get_fresh(info, max_age_seconds=0) or ...
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from .models import VideoInfo


def _key(info: VideoInfo) -> str:
    if info.bvid:
        return f"bv:{info.bvid}"
    if info.aid:
        return f"av:{info.aid}"
    return f"raw:{info.raw_input}"


def parse_duration(s: str) -> Optional[timedelta]:
    """把 '1h' / '24h' / '7d' / '30m' / '0' / '' 解析为秒数。
    失败或 'never'/'always'/None 返回 None（表示不设过期）。
    """
    if s is None:
        return None
    s = s.strip().lower()
    if s in ("", "never", "always", "inf", "infinite", "-1"):
        return None
    if s in ("0", "no", "off"):
        return 0
    if not s:
        return None
    # 数字 + 单位
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
    if s[-1] in units:
        try:
            n = int(s[:-1])
            return n * units[s[-1]]
        except ValueError:
            return None
    # 纯数字按小时
    try:
        return int(s) * 3600
    except ValueError:
        return None


class Cache:
    def __init__(self, path: str):
        self.path = path
        self._data: Dict[str, dict] = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    self._data = loaded
            except (json.JSONDecodeError, OSError):
                # 损坏的缓存不要影响主流程，直接当空
                self._data = {}

    def has(self, info: VideoInfo) -> bool:
        return _key(info) in self._data

    def get(self, info: VideoInfo) -> Optional[VideoInfo]:
        """不管新鲜度，直接拿 cache 记录。"""
        d = self._data.get(_key(info))
        if not d:
            return None
        return VideoInfo(**d)

    def is_fresh(self, info: VideoInfo, max_age_seconds) -> bool:
        """判断 cache 是否还在新鲜度内。

        max_age_seconds:
          None  / < 0  → 永远新鲜（信任 cache）
          0            → 永远不新鲜（不信任 cache）
          正数         → 抓取时间距今不超过这个秒数就算新鲜
        """
        if max_age_seconds is None or max_age_seconds < 0:
            return True
        if max_age_seconds == 0:
            return False
        if not info.fetched_at:
            return False
        try:
            fetched = datetime.strptime(info.fetched_at, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return False
        age = (datetime.now() - fetched).total_seconds()
        return age <= max_age_seconds

    def get_fresh(
        self, info: VideoInfo, max_age_seconds
    ) -> Optional[VideoInfo]:
        """拿 cache 记录，但**只在新鲜度内**才返回；否则返回 None。

        失败/失效状态（status != "ok"）**永远算新鲜**（视频失效不会"复活"）。
        """
        cached = self.get(info)
        if not cached:
            return None
        # 失败状态永远算新鲜
        if cached.status != "ok":
            return cached
        # 成功状态：判断动态字段是否过期
        return cached if self.is_fresh(cached, max_age_seconds) else None

    def put(self, info: VideoInfo) -> None:
        # 任何状态都存：ok / failed / not_found 都对未来"不要重复请求"有用
        self._data[_key(info)] = info.to_dict()

    def all_records(self) -> List[VideoInfo]:
        return [VideoInfo(**d) for d in self._data.values()]

    def save(self) -> None:
        """原子写入：先写临时文件再 rename，避免中断时损坏。"""
        if not self.path:
            return
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        # 写到同目录临时文件，Windows rename 在同盘是原子的
        dir_ = os.path.dirname(self.path) or "."
        fd, tmp = tempfile.mkstemp(prefix=".cache.", suffix=".json", dir=dir_)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def stats(self) -> Dict[str, int]:
        ok = sum(1 for d in self._data.values() if d.get("status") == "ok")
        fail = sum(1 for d in self._data.values() if d.get("status") in ("failed", "not_found"))
        return {"total": len(self._data), "ok": ok, "failed": fail}
