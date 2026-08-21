"""诊断 chain 对 Warma 的行为"""
import os
os.environ.pop("UAPIS_CN_API_KEY", None)

from bilibili_tool.uapi import UapisCnProvider, SelfWbiProvider, SelfLegacyProvider, AuthorArchiveChain

chain = AuthorArchiveChain([
    UapisCnProvider(),  # primary
    UapisCnProvider(),  # 备用
    SelfLegacyProvider(),
])
try:
    archives = chain.fetch_author_archives(uid=53456, unlimited=True, max=200)
    print("OK: %d archives" % len(archives))
    a = archives[0]
    print("_chain: %s" % a.get("_chain"))
    print("_completeness: %s" % a.get("_completeness"))
    print("_provider_total: %s" % a.get("_provider_total"))
    print("_actual_count: %s" % a.get("_actual_count"))
except Exception as e:
    print("FAIL: %s: %s" % (type(e).__name__, e))
