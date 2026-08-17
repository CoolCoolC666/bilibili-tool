"""JSON 缓存 + 断点续传。

设计：用一个 cache.json 存"已成功 / 已确认失败"的结果。
key 优先用 BV 号（稳定 + URL 友好），无 BV 时用 aid。
value 直接存 VideoInfo.to_dict()。

断点续传：调用 batch_fetch 前先 load；fetch 完成后立刻 save。
脚本中断后下次跑会跳过已记录的项。
"""
from __future__ import annotations

import json
import os
import tempfile
from typing import Dict, List, Optional, Tuple

from .models import VideoInfo


def _key(info: VideoInfo) -> str:
    if info.bvid:
        return f"bv:{info.bvid}"
    if info.aid:
        return f"av:{info.aid}"
    return f"raw:{info.raw_input}"


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
        d = self._data.get(_key(info))
        if not d:
            return None
        vi = VideoInfo(**d)
        return vi

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
