"""直接用 chain 测 Warma"""
import os
os.environ.pop("UAPIS_CN_API_KEY", None)

from bilibili_tool.uapi import UapisCnProvider, SelfWbiProvider, SelfLegacyProvider, AuthorArchiveChain, UapiRateLimitError, UapiError

# 用 primary=uapis.cn, 备用=uapis.cn, 末位=self-legacy
chain = AuthorArchiveChain([
    UapisCnProvider(),  # primary
    UapisCnProvider(),  # 备用
    SelfLegacyProvider(),  # 末位
])
print("=== chain 抓 Warma 53456 unlimited=True max=200 ===")
try:
    archives = chain.fetch_author_archives(uid=53456, unlimited=True, max_count=200)
    a = archives[0]
    print(f"  OK {len(archives)} archives")
    print(f"  _chain={a.get('_chain')}")
    print(f"  _completeness={a.get('_completeness')}")
    print(f"  _provider_total={a.get('_provider_total')}")
    print(f"  _actual_count={a.get('_actual_count')}")
except UapiRateLimitError as e:
    print(f"  RATE_LIMIT: {e}")
except UapiError as e:
    print(f"  UAPI_ERROR ({type(e).__name__}): {e}")
except Exception as e:
    print(f"  EXCEPTION: {type(e).__name__}: {e}")
