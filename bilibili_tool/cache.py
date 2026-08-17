"""JSON 缓存 + 断点续传 + 字段新鲜度 + 跨 AV/BV 双索引。

设计哲学：
- B 站数据是"实时更新"的——抓一次播放量 1000，几小时后可能 5000
- 所以 cache 不能无限保留。需要按字段类型区分：
  * 静态字段（标题、UP主、发布时间、时长...）：视频发布后基本不变 → 永远 cache
  * 动态字段（播放、点赞、收藏...）：实时变 → 按 max_age 过期
  * 失败状态（not_found / failed）：视频失效不会"复活" → 永远 cache
- 跨 AV/BV 双索引：同一视频的 BV 号和 AV 号都指向同一条 cache 记录
  * 用户输入 "BV1xxx 170001"，第一次跑就只发 1 个请求，第二次更不用说

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
from typing import Dict, List, Optional

from .models import VideoInfo


def _all_keys(info: VideoInfo) -> List[str]:
    """一条 VideoInfo 可能对应的所有 cache key。

    同一条记录会按 BV / AV / raw 同时索引，这样用户用任意一种 ID 都能命中。
    """
    keys = []
    if info.bvid:
        keys.append(f"bv:{info.bvid}")
    if info.aid:
        keys.append(f"av:{info.aid}")
    if not keys and info.raw_input:
        keys.append(f"raw:{info.raw_input}")
    return keys


def _primary_key(info: VideoInfo) -> str:
    """取第一个可用的 key（用于向后兼容 has() 等单 key 场景）。"""
    keys = _all_keys(info)
    return keys[0] if keys else f"raw:{info.raw_input}"


def parse_duration(s: str) -> Optional[int]:
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
        # 升级：旧 cache 是单 key 索引，遍历 records 重新 put 让它变成双索引
        self._upgrade_dual_index()

    def _upgrade_dual_index(self) -> None:
        """检查每条记录的 bvid/aid，把缺失的 key 补上。

        旧版本 cache 只按一种 key 索引，新版本按 bvid+aid 双索引。
        启动时遍历一遍 records，看哪些 key 缺失就补上。补完不一定 save（不修改用户磁盘文件），
        但下次 put 会自动持久化。
        """
        # 先收集所有需要补的 (key, payload)
        upgrades = []
        seen_payloads: set = set()  # 用 id() 避免重复处理同一条 in-memory dict
        for key, payload in list(self._data.items()):
            if id(payload) in seen_payloads:
                continue
            seen_payloads.add(id(payload))
            # 这条 payload 应该有哪些 key
            wanted_keys = set()
            if payload.get("bvid"):
                wanted_keys.add(f"bv:{payload['bvid']}")
            if payload.get("aid"):
                wanted_keys.add(f"av:{payload['aid']}")
            if not wanted_keys and payload.get("raw_input"):
                wanted_keys.add(f"raw:{payload['raw_input']}")
            # 缺的补上
            for w in wanted_keys:
                if w not in self._data:
                    upgrades.append((w, payload))
        for w, payload in upgrades:
            self._data[w] = payload

    def has(self, info: VideoInfo) -> bool:
        return any(k in self._data for k in _all_keys(info))

    def get(self, info: VideoInfo) -> Optional[VideoInfo]:
        """不管新鲜度，直接拿 cache 记录。尝试所有可能的 key。"""
        for k in _all_keys(info):
            d = self._data.get(k)
            if d:
                return VideoInfo(**d)
        return None

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
        """存一条记录，**按所有可能的 key 同时索引**。

        比如一条记录同时有 bvid=BV1xxx 和 aid=170001：
        - cache["bv:BV1xxx"] = record
        - cache["av:170001"] = record
        下次用户输入任意一种 ID 都能命中同一条。
        """
        keys = _all_keys(info)
        if not keys:
            # 没有任何 ID 的 fallback，用 raw_input 作 key
            keys = [f"raw:{info.raw_input}"]
        payload = info.to_dict()
        for k in keys:
            self._data[k] = payload

    def all_records(self) -> List[VideoInfo]:
        """返回去重后的所有记录（双索引会指向同一份 dict，需要去重）。

        用 (bvid, aid, raw_input) 作为内容指纹——不论从内存 dict 还是 JSON
        加载回来的新 dict 都能正确去重。
        """
        seen: set = set()
        out: List[VideoInfo] = []
        for d in self._data.values():
            fingerprint = (d.get("bvid") or "", d.get("aid"), d.get("raw_input") or "")
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            out.append(VideoInfo(**d))
        return out

    def unique_count(self) -> int:
        """返回去重后的"实际视频数"（不受双索引影响）。"""
        return len(self.all_records())

    def save(self) -> None:
        """原子写入：先写临时文件再 rename，避免中断时损坏。"""
        if not self.path:
            return
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
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
        ok = sum(1 for d in self.all_records() if d.status == "ok")
        fail = sum(1 for d in self.all_records() if d.status in ("failed", "not_found"))
        return {"total": self.unique_count(), "ok": ok, "failed": fail}
