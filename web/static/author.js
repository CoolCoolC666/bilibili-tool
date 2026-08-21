// v3.0+ author 页面：provider 切换 + 阶段 1（拉列表） + 阶段 2（抓详情）
// 关键：API key 只存 localStorage，不上传服务器（key 只在 fetch /api/author/list 时临时传递）
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const KEY_STORAGE_PREFIX = "bilibili_tool:uapi_key:";   // localStorage key 前缀
  const INTERVAL_STORAGE_KEY = "bilibili_tool:uapi_interval_ms";  // v3.0.9+：翻页间隔
  const DISABLE_CACHE_KEY = "bilibili_tool:uapi_disable_cache";  // v3.1.0+：Q12 绕过缓存
  const DEFAULT_INTERVAL_MS = 250;  // 4 QPS（uapis 访客档位）

  // ----------------------------------------------------------------
  // v3.0+ 数据源管理
  // ----------------------------------------------------------------
  let PROVIDERS = [];      // 缓存 /api/author/providers 的结果
  let CURRENT_PROVIDER_ID = null;  // 当前选中的 provider

  // v3.0.9+：读全局 interval（localStorage → 默认值）
  function getIntervalMs() {
    const saved = localStorage.getItem(INTERVAL_STORAGE_KEY);
    if (saved && !isNaN(parseInt(saved, 10)) && parseInt(saved, 10) >= 0) {
      return parseInt(saved, 10);
    }
    return DEFAULT_INTERVAL_MS;
  }

  function saveInterval() {
    const v = parseInt($("up-interval").value, 10);
    if (isNaN(v) || v < 0) {
      showResult("up-result", "⚠ 请求间隔必须是非负整数（毫秒）", true);
      return;
    }
    localStorage.setItem(INTERVAL_STORAGE_KEY, String(v));
    $("interval-status").textContent = `（已保存：${v}ms）`;
    showResult("up-result", `✅ 请求间隔已保存到本地：${v}ms`, false);
  }

  // v3.1.0+ Q12：disable_cache 全局开关
  function getDisableCache() {
    return localStorage.getItem(DISABLE_CACHE_KEY) === "true";
  }

  // v3.1.0+ Q26：查询剩余额度
  async function queryUsage() {
    const k = (CURRENT_PROVIDER_ID === "uapis.cn") ? $("up-api-key").value.trim() : "";
    const body = { disable_cache: getDisableCache() };
    if (k) body.api_key = k;
    $("usage-status").textContent = "（查询中...）";
    try {
      const r = await fetch("/api/author/usage", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await r.json();
      if (!r.ok || !data.ok) {
        const err = data.error || r.statusText;
        $("usage-status").textContent = `（查询失败：${err}）`;
        showResult("up-result", `❌ 剩余额度查询失败：${err}`, true);
        return;
      }
      // 渲染剩余额度
      renderUsage(data);
      $("usage-status").textContent = `（已查询：${new Date().toLocaleTimeString()}）`;
    } catch (e) {
      $("usage-status").textContent = `（查询失败：${e.message}）`;
      showResult("up-result", `❌ 剩余额度查询失败：${e.message}`, true);
    }
  }

  function renderUsage(data) {
    const card = $("usage-card");
    const content = $("usage-content");
    if (!data.usage) {
      card.style.display = "none";
      return;
    }
    card.style.display = "";
    const u = data.usage;
    const modeBadge = data.mode === "logged_in"
      ? '<span class="badge badge-info">登录用户</span>'
      : '<span class="badge badge-warn">访客模式</span>';
    // uapis /status/usage 响应字段（参考 FAQ Q26）：
    // - visitor_quota: { remaining, monthly, used } —— 访客本月剩余
    // - billing: { quota, balance, ... }
    // - rate_limit: { qps, ... }
    let html = `<div>${modeBadge}</div>`;
    if (u.visitor_quota) {
      const vq = u.visitor_quota;
      html += `<div style="margin-top:4px">访客额度：<b>${vq.remaining || 0}</b> / ${vq.monthly || 1500} 积分（已用 ${vq.used || 0}）</div>`;
    }
    if (u.billing) {
      const b = u.billing;
      html += `<div>资源包剩余：<b>${b.quota || 0}</b> 积分</div>`;
      if (b.balance !== undefined) {
        html += `<div>账户余额：<b>${(b.balance / 100).toFixed(2)}</b> 元（${b.balance} 分）</div>`;
      }
    }
    if (u.rate_limit) {
      html += `<div>当前 QPS：<b>${u.rate_limit.qps || "?"}</b></div>`;
    }
    // 兜底：显示原始 JSON（如果有未识别的字段）
    html += `<details style="margin-top:6px"><summary>查看原始响应</summary><pre style="font-size:0.8em; margin-top:4px; padding:6px; background:#f5f5f5; border-radius:4px; overflow:auto">${escapeHtml(JSON.stringify(u, null, 2))}</pre></details>`;
    content.innerHTML = html;
  }

  async function loadProviders() {
    try {
      const r = await fetch("/api/author/providers");
      const data = await r.json();
      PROVIDERS = data.providers || [];
      const sel = $("up-provider");
      sel.innerHTML = "";
      PROVIDERS.forEach((p) => {
        const opt = document.createElement("option");
        opt.value = p.id;
        opt.textContent = p.name;
        sel.appendChild(opt);
      });
      // 默认选 uapis.cn（v3.0+ 推荐：受网络影响最小）
      const defaultId = "uapis.cn";
      if (PROVIDERS.find((p) => p.id === defaultId)) {
        sel.value = defaultId;
        onProviderChange();
      }
    } catch (e) {
      $("up-provider").innerHTML = `<option value="">加载失败：${e.message}</option>`;
    }
  }

  function onProviderChange() {
    const sel = $("up-provider");
    const id = sel.value;
    CURRENT_PROVIDER_ID = id;
    const provider = PROVIDERS.find((p) => p.id === id);
    if (!provider) return;

    // API key 输入框显隐
    $("up-key-label").style.display = (id === "uapis.cn") ? "" : "none";

    // 从 localStorage 恢复 key
    if (id === "uapis.cn") {
      const saved = localStorage.getItem(KEY_STORAGE_PREFIX + id) || "";
      $("up-api-key").value = saved;
      $("key-status").textContent = saved ? "（已保存到本地）" : "（未保存，访客模式）";
    }

    // v3.0.9+：切 provider 时刷新请求间隔推荐值
    const recommended = provider.recommended_interval_ms || DEFAULT_INTERVAL_MS;
    const current = getIntervalMs();
    if ($("up-interval").value !== String(current)) {
      $("up-interval").value = current;
    }
    $("interval-status").textContent = `（当前：${current}ms · 推荐：${recommended}ms）`;

    // 风险提示
    $("provider-status").textContent = provider.name;
    const list = $("risk-list");
    list.innerHTML = "";
    [
      provider.credit_cost && `💰 ${provider.credit_cost}`,
      provider.rate_limit && `🚦 ${provider.rate_limit}`,
      provider.cache && `⏱ ${provider.cache}`,
      provider.data_limit && `📊 ${provider.data_limit}`,
      provider.recommended_interval_ms && `⏱ 推荐翻页间隔：${provider.recommended_interval_ms}ms`,
    ].filter(Boolean).forEach((text) => {
      const li = document.createElement("li");
      li.textContent = text;
      list.appendChild(li);
    });
    const riskP = $("risk-extra");
    if (provider.risk) {
      riskP.textContent = "⚠ " + provider.risk;
      riskP.style.display = "";
    } else {
      riskP.style.display = "none";
    }
    $("risk-card").style.display = "";
  }

  function saveKey() {
    const id = CURRENT_PROVIDER_ID;
    if (id !== "uapis.cn") {
      showResult("up-result", "当前 provider 不需要 key", true);
      return;
    }
    const key = $("up-api-key").value.trim();
    if (!key) {
      localStorage.removeItem(KEY_STORAGE_PREFIX + id);
      $("key-status").textContent = "（已清除，访客模式）";
      showResult("up-result", "✅ Key 已从本地清除，下次访问将走访客模式", false);
      return;
    }
    if (!key.startsWith("uapi-")) {
      if (!confirm("Key 不以 'uapi-' 开头，uapis.cn 通常拒绝。仍要保存？")) return;
    }
    localStorage.setItem(KEY_STORAGE_PREFIX + id, key);
    $("key-status").textContent = "（已保存到本地）";
    showResult("up-result", "✅ Key 已保存到 localStorage（仅本浏览器）", false);
  }

  function clearAllKeys() {
    if (!confirm("确认清除所有 uapi_key 本地缓存？此操作不可撤销。")) return;
    const keysToRemove = Object.keys(localStorage).filter((k) => k.startsWith(KEY_STORAGE_PREFIX));
    keysToRemove.forEach((k) => localStorage.removeItem(k));
    $("up-api-key").value = "";
    $("key-status").textContent = "（已清除，访客模式）";
    showResult("up-result", `✅ 已清除 ${keysToRemove.length} 个本地 Key`, false);
  }

  // ----------------------------------------------------------------
  // 阶段 1：拉列表
  // ----------------------------------------------------------------
  // v3.0.3+：日期快捷按钮（近 7/30/90 天 / 全部时间）
  let DATE_PRESET = null;  // 记录当前预设（提交时传给后端）
  function applyDatePreset(preset) {
    const $days = $("up-days");
    const $since = $("up-since");
    const $until = $("up-until");
    const $status = $("up-date-preset-status");
    if (preset === "all") {
      // "全选" = 抓所有时间（不限）
      $days.value = "";
      $since.value = "";
      $until.value = "";
      $status.textContent = "（不限时间）";
      DATE_PRESET = "all";
    } else {
      // 数字预设（7/30/90）：设 days，清空 since/until
      const n = parseInt(preset, 10);
      $days.value = n;
      $since.value = "";
      $until.value = "";
      $status.textContent = `（近 ${n} 天）`;
      DATE_PRESET = null;  // 用 days 即可，后端不需要 unlimited
    }
  }
  document.querySelectorAll("[data-date-preset]").forEach((btn) => {
    btn.addEventListener("click", () => applyDatePreset(btn.dataset.datePreset));
  });

  $("up-btn").addEventListener("click", async () => {
    const inputs = $("up-input").value.trim();
    if (!inputs) {
      showResult("up-result", "请先输入 UP 主 UID 或链接", true);
      return;
    }
    if (!CURRENT_PROVIDER_ID) {
      showResult("up-result", "请先选择数据源", true);
      return;
    }

    const body = { inputs, provider: CURRENT_PROVIDER_ID };
    // 只有 uapis.cn 才传 key
    if (CURRENT_PROVIDER_ID === "uapis.cn") {
      const k = $("up-api-key").value.trim();
      if (k) body.api_key = k;
    }
    const days = $("up-days").value;
    const since = $("up-since").value;
    const until = $("up-until").value;
    const max = $("up-max").value;
    const timeout = $("up-timeout").value;
    // v3.0.9+：所有抓取都带 interval_ms（从顶部设置取）
    body.interval_ms = getIntervalMs();
    // v3.1.0+ Q12：所有抓取都带 disable_cache
    body.disable_cache = getDisableCache();
    // v3.0.3+：点过"全选"按钮时传 unlimited=true
    if (DATE_PRESET === "all") {
      body.unlimited = true;
    } else if (days) {
      body.days = parseInt(days, 10);
    }
    if (since) body.since = since;
    if (until) body.until = until;
    if (max) body.max = parseInt(max, 10);
    if (timeout) body.timeout = parseFloat(timeout);

    $("up-btn").disabled = true;
    showResult("up-result", `正在通过 [${CURRENT_PROVIDER_ID}] 拉取列表... (interval=${body.interval_ms}ms, disable_cache=${body.disable_cache})`);

    try {
      const r = await fetch("/api/author/list", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await r.json();
      if (!r.ok) {
        showResult("up-result", `失败：${data.error || r.statusText}`, true);
        return;
      }
      // 渲染结果
      const lines = (data.results || []).map((res) => {
        if (res.error) {
          return `<li>UP ${res.uid}：<span style="color:#e74c3c">失败：${res.error}</span></li>`;
        }
        // v3.0.5+：完整性提示（uapis 数据不完整时显示警告）
        let warn = "";
        if (res.completeness === "partial") {
          warn = ` <span class="badge badge-warn" title="uapis 报告 ${res.provider_total} 条，实际拿到 ${res.actual_count} 条（分页 bug）">⚠ 数据可能不完整</span>`;
        }
        return `<li>UP ${res.uid}：<b>${res.count}</b> 条（来源：<code>${res.source}</code>）${warn} → <code>${res.path}</code></li>`;
      });
      const modeInfo = data.has_key
        ? '<span class="badge badge-info">已用 Key</span>'
        : '<span class="badge badge-warn">访客模式</span>';
      const html = `${modeInfo} 拉取完成，共 ${data.uids.length} 个 UP 主。<ul>${lines.join("")}</ul>`;
      showResult("up-result", html);
      // 刷新阶段 2 的文件列表
      loadAuthorFiles();
    } catch (e) {
      showResult("up-result", `请求失败：${e.message}`, true);
    } finally {
      $("up-btn").disabled = false;
    }
  });

  // ----------------------------------------------------------------
  // 阶段 2：抓详情（v3.0.4+ 异步 + 实时进度）
  // ----------------------------------------------------------------
  let DETAIL_POLL_TIMER = null;

  function stopDetailPolling() {
    if (DETAIL_POLL_TIMER) {
      clearInterval(DETAIL_POLL_TIMER);
      DETAIL_POLL_TIMER = null;
    }
  }

  function renderDetailProgress(job) {
    // v3.0.7+：支持批量模式（sub_done / sub_total / xlsx_paths）
    const isBatch = (job.sub_total || 0) > 1;

    // 子任务进度（多个 CSV 完成度）
    let subBar = "";
    if (isBatch) {
      const subPct = job.sub_total > 0
        ? Math.round((job.sub_done / job.sub_total) * 100)
        : 0;
      subBar = `
        <div class="progress-row">
          <div class="bar"><div class="bar-fill" style="width:${subPct}%"></div></div>
          <span class="counter">📁 CSV: ${job.sub_done} / ${job.sub_total} (${subPct}%)</span>
        </div>
      `;
    }

    // 当前 CSV 内的视频进度
    const pct = job.total > 0 ? Math.round((job.processed / job.total) * 100) : 0;
    const bar = job.total > 0
      ? `<div class="bar"><div class="bar-fill" style="width:${pct}%"></div></div>`
      : `<div class="bar"><div class="bar-fill" style="width:0%"></div></div>`;
    const logLines = (job.log_tail || []).slice(-15).map((l) =>
      `<div>${escapeHtml(l)}</div>`
    ).join("");
    const logBlock = logLines
      ? `<details class="log-block" open><summary>📋 实时日志（最近 15 条）</summary><div class="log-mini">${logLines}</div></details>`
      : "";

    let html = "";
    if (job.status === "running" || job.status === "pending") {
      const subCurrent = job.sub_current ? `当前 CSV：<code>${escapeHtml(job.sub_current)}</code><br>` : "";
      html = `
        <div class="info">
          <b>🔄 抓取中</b> ${isBatch ? "(批量模式)" : ""}
          ${subBar}
          ${subCurrent}
          <div class="progress-row">
            ${bar}
            <span class="counter">${job.processed} / ${job.total || "?"} (${pct}%)</span>
          </div>
          <div class="stats">
            <span>✓ 成功 <b>${job.ok_count}</b></span>
            <span>✗ 失败 <b>${job.fail_count}</b></span>
            ${job.current ? `<span>📺 当前：<code>${escapeHtml(job.current)}</code></span>` : ""}
          </div>
          ${logBlock}
        </div>
      `;
    } else if (job.status === "done") {
      // v3.0.8+：用"另存"按钮（不自动 trigger，避免浏览器弹"另存为"）
      // 浏览器支持 File System Access API 时，弹文件选择器（不弹浏览器"另存为"）
      // 不支持时 fallback 到普通 <a download> 链接
      let saveButtons = "";
      if (isBatch && job.xlsx_paths && job.xlsx_paths.length > 0) {
        saveButtons = job.xlsx_paths
          .map((p) =>
            `<button class="ghost save-xlsx-btn" data-path="${escapeHtml(p)}" style="margin:2px 4px 2px 0">📥 另存 ${escapeHtml(p.split("/").pop())}</button>`
          ).join("");
        saveButtons += `<br><small class="hint">共 ${job.xlsx_paths.length} 个 XLSX · 浏览器支持 File System Access API 时会弹文件选择器，否则按普通下载</small>`;
      } else if (job.xlsx_path) {
        saveButtons =
          `<button class="primary save-xlsx-btn" data-path="${escapeHtml(job.xlsx_path)}">📥 另存 XLSX</button>` +
          `<br><small class="hint">浏览器支持 File System Access API 时会弹文件选择器，否则按普通下载</small>`;
      }
      const errors = (job.errors || []).map((e) =>
        `<li>❌ <code>${escapeHtml(e.file)}</code>: ${escapeHtml(e.error)}</li>`
      ).join("");
      html = `
        <div class="info">
          ✅ <b>完成</b> · 成功 <b>${job.ok_count}</b> / 失败 <b>${job.fail_count}</b>
          ${isBatch ? ` / CSV: <b>${job.sub_done}/${job.sub_total}</b>` : ""}
          <br>${saveButtons || "（无 XLSX 输出）"}
          ${errors ? `<br><b>失败的 CSV：</b><ul>${errors}</ul>` : ""}
          ${logBlock}
        </div>
      `;
      // 绑定另存按钮事件
      setTimeout(() => {
        document.querySelectorAll(".save-xlsx-btn").forEach((btn) => {
          btn.addEventListener("click", () => saveXlsxAs(btn.dataset.path));
        });
      }, 0);
    } else if (job.status === "error") {
      html = `
        <div class="error">
          💥 <b>异常</b>：${escapeHtml(job.error || "未知错误")}
          ${logBlock}
        </div>
      `;
    }
    return html;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  // v3.0.8+：另存为（用 File System Access API 避免浏览器"另存为"弹窗）
  // 浏览器支持：Chrome 86+, Edge 86+；不支持时回退到 <a download>
  const FILE_SAVE_SUPPORT = "showSaveFilePicker" in window;

  async function saveXlsxAs(serverPath) {
    // serverPath 例如 "xlsx/author_detail_53456_xxx.xlsx"
    const url = `/api/outputs/${encodeURIComponent(serverPath)}`;
    const filename = serverPath.split("/").pop();
    try {
      // 拿文件内容（fetch 拿到 Blob）
      const r = await fetch(url);
      if (!r.ok) throw new Error(`下载失败：${r.status}`);
      const blob = await r.blob();

      if (FILE_SAVE_SUPPORT) {
        // 用 File System Access API：弹文件选择器（不弹浏览器"另存为"）
        try {
          const handle = await window.showSaveFilePicker({
            suggestedName: filename,
            types: [{
              description: "XLSX 文件",
              accept: { "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"] },
            }],
          });
          const writable = await handle.createWritable();
          await writable.write(blob);
          await writable.close();
          // 成功：显示小提示
          console.log("已保存：", filename);
        } catch (e) {
          if (e.name === "AbortError") return;  // 用户取消
          throw e;
        }
      } else {
        // 回退：用 <a download>（浏览器弹"另存为"——不可控）
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(a.href);
      }
    } catch (e) {
      showResult("detail-result", `另存失败：${e.message}`, true);
    }
  }

  async function pollDetailProgress(jobId, filename) {
    try {
      const r = await fetch(`/api/author/detail/progress?job_id=${encodeURIComponent(jobId)}`);
      if (!r.ok) {
        stopDetailPolling();
        showResult("detail-result", `轮询失败：${r.status}`, true);
        return;
      }
      const job = await r.json();
      showResult("detail-result", renderDetailProgress(job));
      if (job.status === "done") {
        stopDetailPolling();
        $("detail-btn").disabled = false;
        // 刷新文件列表（新生成的 xlsx 已在 DEFAULT_XLSX 里，但列表只显示 csv，不用刷）
      } else if (job.status === "error") {
        stopDetailPolling();
        $("detail-btn").disabled = false;
      }
    } catch (e) {
      // 网络抖动不立即停
      console.warn("轮询异常:", e);
    }
  }

  $("detail-btn").addEventListener("click", async () => {
    const sel = $("detail-file");
    const selected = Array.from(sel.selectedOptions).map((o) => o.value).filter(Boolean);
    if (selected.length === 0) {
      showResult("detail-result", "请先选择至少 1 个 CSV 文件（按住 Ctrl/Shift 多选）", true);
      return;
    }
    const max = $("detail-max").value;
    const delay = $("detail-delay").value;
    const retry = $("detail-retry").value;
    const timeout = $("detail-timeout").value;
    const commonBody = {};
    if (max) commonBody.max = parseInt(max, 10);
    // v3.0.9+：interval_ms 优先于 delay（统一用全局间隔）
    commonBody.interval_ms = getIntervalMs();
    // v3.1.0+ Q12：detail 端点也带 disable_cache
    commonBody.disable_cache = getDisableCache();
    // 后向兼容：仅在用户没设 interval 时才用 delay
    if (delay && !commonBody.interval_ms) commonBody.delay = parseFloat(delay);
    if (retry) commonBody.retry = parseInt(retry, 10);
    if (timeout) commonBody.timeout = parseFloat(timeout);

    $("detail-btn").disabled = true;

    // v3.0.7+：多选 → 用 /batch 端点；单选 → 用单文件端点（向后兼容）
    const useBatch = selected.length > 1;
    const body = useBatch
      ? { ...commonBody, filenames: selected }
      : { ...commonBody, filename: selected[0] };
    const endpoint = useBatch ? "/api/author/detail/batch" : "/api/author/detail";
    const label = useBatch
      ? `批量抓取 ${selected.length} 个 CSV`
      : `抓取详情：${selected[0]}`;

    showResult("detail-result", `🔄 ${label}...`);

    try {
      const r = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await r.json();
      if (!r.ok) {
        showResult("detail-result", `失败：${data.error || r.statusText}`, true);
        $("detail-btn").disabled = false;
        return;
      }
      const jobId = data.job_id;
      showResult("detail-result", `🔄 任务已启动（job_id=${jobId}），等待 1 秒拿到首批进度...`);
      setTimeout(() => pollDetailProgress(jobId, useBatch ? selected : selected[0]), 500);
      DETAIL_POLL_TIMER = setInterval(() => pollDetailProgress(jobId, useBatch ? selected : selected[0]), 600);
    } catch (e) {
      showResult("detail-result", `请求失败：${e.message}`, true);
      $("detail-btn").disabled = false;
    }
  });

  // ----------------------------------------------------------------
  // 文件列表（v3.0.7+ 多选 + 全选 + 打开文件夹）
  // ----------------------------------------------------------------
  async function loadAuthorFiles() {
    try {
      const r = await fetch("/api/author/files");
      const data = await r.json();
      const sel = $("detail-file");
      const prevSelected = Array.from(sel.selectedOptions).map((o) => o.value);
      sel.innerHTML = "";
      const files = data.files || [];
      if (files.length === 0) {
        sel.innerHTML = '<option value="">-- output/ 里还没有 CSV --</option>';
        $("detail-btn").disabled = true;
        $("detail-delete").disabled = true;
        updateSelectedInfo();
        return;
      }
      // v3.0.7+：多选（<select multiple>），按 group 分组
      files.forEach((f) => {
        const opt = document.createElement("option");
        opt.value = f.name;
        const sizeKb = (f.size / 1024).toFixed(1);
        const mtime = new Date(f.mtime * 1000).toLocaleString("zh-CN");
        // 短标签 + 完整 tooltip
        opt.textContent = `[${f.group}] ${f.name}  (${sizeKb} KB, ${mtime})`;
        opt.title = `${f.name}\n${sizeKb} KB, ${mtime}\n分组：${f.group}`;
        if (prevSelected.includes(f.name)) opt.selected = true;
        sel.appendChild(opt);
      });
      $("detail-btn").disabled = false;
      $("detail-delete").disabled = false;
      updateSelectedInfo();
    } catch (e) {
      $("detail-file").innerHTML = `<option value="">加载失败：${e.message}</option>`;
    }
  }

  function updateSelectedInfo() {
    const sel = $("detail-file");
    const n = sel.selectedOptions.length;
    $("detail-selected-info").textContent = `已选 ${n} 个`;
  }

  // "全选所有 author_*.csv" 按钮：v3.0.7+ 批量选择
  $("detail-select-all").addEventListener("click", () => {
    const sel = $("detail-file");
    Array.from(sel.options).forEach((opt) => {
      if (opt.value) opt.selected = true;
    });
    updateSelectedInfo();
  });

  $("detail-select-none").addEventListener("click", () => {
    const sel = $("detail-file");
    Array.from(sel.options).forEach((opt) => {
      opt.selected = false;
    });
    updateSelectedInfo();
  });

  $("detail-file").addEventListener("change", updateSelectedInfo);

  // "在文件管理器中打开" 按钮
  $("detail-open-folder").addEventListener("click", async () => {
    const sel = $("detail-file");
    const first = sel.selectedOptions[0]?.value || "";
    try {
      const r = await fetch("/api/open-output-folder", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ select: first }),
      });
      const data = await r.json();
      if (!r.ok) {
        showResult("detail-result", `打开失败：${data.error}`, true);
        return;
      }
      const msg = first
        ? `已打开文件管理器并高亮：${first}`
        : `已打开文件管理器：${data.opened}`;
      showResult("detail-result", msg);
    } catch (e) {
      showResult("detail-result", `打开失败：${e.message}`, true);
    }
  });

  // ----------------------------------------------------------------
  // 删除选中文件
  // ----------------------------------------------------------------
  $("detail-delete").addEventListener("click", async () => {
    const filename = $("detail-file").value;
    if (!filename) {
      showResult("detail-result", "请先选择要删除的文件", true);
      return;
    }
    if (!confirm(`确认删除文件？\n\n${filename}\n\n（删除后不可恢复）`)) return;
    try {
      const r = await fetch(`/api/author/files/${encodeURIComponent(filename)}`, {
        method: "DELETE",
      });
      const data = await r.json();
      if (!r.ok) {
        showResult("detail-result", `删除失败：${data.error || r.statusText}`, true);
        return;
      }
      showResult("detail-result", `✅ 已删除：${data.deleted}`);
      loadAuthorFiles();
    } catch (e) {
      showResult("detail-result", `删除失败：${e.message}`, true);
    }
  });

  // ----------------------------------------------------------------
  // 清空所有缓存（防干扰）
  // ----------------------------------------------------------------
  $("cache-clear").addEventListener("click", async () => {
    if (!confirm("确认清空所有缓存？\n\n会删除 data/cache.json 等 3 类缓存文件，\n下次抓取时所有数据都会重新拉取（不会命中缓存）。")) return;
    try {
      const r = await fetch("/api/cache", { method: "DELETE" });
      const data = await r.json();
      if (!r.ok) {
        showResult("detail-result", `清缓存失败：${data.error || r.statusText}`, true);
        return;
      }
      showResult("detail-result", "✅ 已清空所有缓存，下次抓取会重新拉取");
      loadCacheStats();
    } catch (e) {
      showResult("detail-result", `清缓存失败：${e.message}`, true);
    }
  });

  // ----------------------------------------------------------------
  // 批量删除文件（v3.0.2+：路径输入 + 通配符）
  // ----------------------------------------------------------------
  $("batch-delete-btn").addEventListener("click", async () => {
    const text = $("batch-delete-paths").value.trim();
    if (!text) {
      showResult("detail-result", "请先输入要删除的路径（每行一个）", true);
      return;
    }
    const paths = text.split("\n").map((l) => l.trim()).filter(Boolean);
    if (!confirm(`确认批量删除 ${paths.length} 个路径？\n\n（支持通配符 * / ? / [seq]）`)) return;
    try {
      const r = await fetch("/api/author/files/delete-batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ paths }),
      });
      const data = await r.json();
      if (!r.ok) {
        showResult("detail-result", `批量删除失败：${data.error || r.statusText}`, true);
        return;
      }
      // 渲染结果
      const ok = (data.deleted || []).map((p) => `<li>✅ ${p}</li>`).join("");
      const fail = (data.failed || []).map((f) =>
        `<li>❌ <code>${f.path}</code> — ${f.error}</li>`
      ).join("");
      const html = `<b>批量删除完成：${data.deleted.length} 成功 / ${data.failed.length} 失败</b>
                    <ul style="margin-top:6px">${ok}${fail}</ul>`;
      showResult("detail-result", html, data.failed.length > 0);
      // 刷新列表 + 状态
      loadAuthorFiles();
      $("batch-delete-status").textContent =
        `上次：✅${data.deleted.length} ❌${data.failed.length}`;
    } catch (e) {
      showResult("detail-result", `批量删除失败：${e.message}`, true);
    }
  });

  $("batch-delete-clear").addEventListener("click", () => {
    $("batch-delete-paths").value = "";
    $("batch-delete-status").textContent = "";
  });

  // ----------------------------------------------------------------
  // ③ UP 主主页信息批量抓取（v3.0.6+）
  // ----------------------------------------------------------------
  let PROFILE_POLL_TIMER = null;

  function stopProfilePolling() {
    if (PROFILE_POLL_TIMER) {
      clearInterval(PROFILE_POLL_TIMER);
      PROFILE_POLL_TIMER = null;
    }
  }

  function renderProfileProgress(job) {
    const pct = job.total > 0 ? Math.round((job.processed / job.total) * 100) : 0;
    const bar = `<div class="bar"><div class="bar-fill" style="width:${pct}%"></div></div>`;
    const logLines = (job.log_tail || []).slice(-15).map((l) =>
      `<div>${escapeHtml(l)}</div>`
    ).join("");
    const logBlock = logLines
      ? `<details class="log-block" open><summary>📋 实时日志（最近 15 条）</summary><div class="log-mini">${logLines}</div></details>`
      : "";

    if (job.status === "running" || job.status === "pending") {
      return `
        <div class="info">
          <b>🔄 抓取中</b> · ${job.processed} / ${job.total} (${pct}%)
          <div class="progress-row" style="margin-top:8px">
            ${bar}
            <span class="counter">${job.ok_count} 成功 / ${job.fail_count} 失败</span>
          </div>
          ${job.current ? `<div style="margin-top:6px">📺 当前：<code>${escapeHtml(job.current)}</code></div>` : ""}
          ${logBlock}
        </div>
      `;
    } else if (job.status === "done") {
      // v3.0.8+：另存按钮（避免浏览器"另存为"弹窗）
      const csvBtn = job.csv_path
        ? `<button class="primary save-xlsx-btn" data-path="${escapeHtml(job.csv_path)}" style="margin:2px 4px 2px 0">📥 另存 CSV</button>`
        : "";
      const xlsxBtn = job.xlsx_path
        ? `<button class="primary save-xlsx-btn" data-path="${escapeHtml(job.xlsx_path)}" style="margin:2px 4px 2px 0">📊 另存 XLSX</button>`
        : "";
      setTimeout(() => {
        document.querySelectorAll(".save-xlsx-btn").forEach((btn) => {
          if (!btn.dataset.bound) {
            btn.dataset.bound = "1";
            btn.addEventListener("click", () => saveXlsxAs(btn.dataset.path));
          }
        });
      }, 0);
      return `
        <div class="info">
          ✅ <b>完成</b> · ${job.ok_count} 成功 / ${job.fail_count} 失败
          ${csvBtn ? `<br>${csvBtn}` : ""}
          ${xlsxBtn ? `<br>${xlsxBtn}` : ""}
          ${logBlock}
        </div>
      `;
    } else if (job.status === "error") {
      return `
        <div class="error">
          💥 <b>异常</b>：${escapeHtml(job.error || "未知错误")}
          ${logBlock}
        </div>
      `;
    }
    return "";
  }

  async function pollProfileProgress(jobId) {
    try {
      const r = await fetch(`/api/author/profile/progress?job_id=${encodeURIComponent(jobId)}`);
      if (!r.ok) {
        stopProfilePolling();
        showResult("profile-result", `轮询失败：${r.status}`, true);
        return;
      }
      const job = await r.json();
      showResult("profile-result", renderProfileProgress(job));
      if (job.status === "done" || job.status === "error") {
        stopProfilePolling();
        $("profile-btn").disabled = false;
      }
    } catch (e) {
      console.warn("轮询异常:", e);
    }
  }

  $("profile-btn").addEventListener("click", async () => {
    const inputs = $("profile-input").value.trim();
    if (!inputs) {
      showResult("profile-result", "请先输入 UP 主 UID 或链接", true);
      return;
    }
    const body = { inputs };
    // uapis.cn key 从顶部数据源设置卡取
    if (CURRENT_PROVIDER_ID === "uapis.cn") {
      const k = $("up-api-key").value.trim();
      if (k) body.api_key = k;
    }
    // v3.0.9+：interval_ms 优先于 delay
    body.interval_ms = getIntervalMs();
    // v3.1.0+ Q12：profile 也带 disable_cache
    body.disable_cache = getDisableCache();
    const delay = $("profile-delay").value;
    if (delay && !body.interval_ms) body.delay = parseFloat(delay);

    $("profile-btn").disabled = true;
    showResult("profile-result", `🔄 启动批量抓取任务... (interval=${body.interval_ms}ms, disable_cache=${body.disable_cache})`);

    try {
      const r = await fetch("/api/author/profile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await r.json();
      if (!r.ok) {
        showResult("profile-result", `失败：${data.error || r.statusText}`, true);
        $("profile-btn").disabled = false;
        return;
      }
      const jobId = data.job_id;
      showResult("profile-result", `🔄 任务已启动（job_id=${jobId}, ${data.total} 个 UP 主），等待 1 秒拿到首批进度...`);
      setTimeout(() => pollProfileProgress(jobId), 500);
      PROFILE_POLL_TIMER = setInterval(() => pollProfileProgress(jobId), 600);
    } catch (e) {
      showResult("profile-result", `请求失败：${e.message}`, true);
      $("profile-btn").disabled = false;
    }
  });

  // ----------------------------------------------------------------
  // 缓存统计（顶部信息条 + 阶段 2 详情）
  // ----------------------------------------------------------------
  async function loadCacheStats() {
    try {
      const r = await fetch("/api/cache/stats");
      const data = await r.json();
      if (data.exists) {
        const s = data.stats;
        const text = `缓存：${s.total} 条（✓ ${s.ok} / ✗ ${s.failed}）`;
        $("cache-info").textContent = text;
        $("cache-stats").textContent = text;
      } else {
        $("cache-info").textContent = "缓存：空";
        $("cache-stats").textContent = "缓存：空";
      }
    } catch (e) {
      $("cache-info").textContent = "缓存：--";
    }
  }
  loadCacheStats();

  $("detail-refresh").addEventListener("click", () => {
    loadAuthorFiles();
    loadCacheStats();
  });
  loadAuthorFiles();

  // ----------------------------------------------------------------
  // 绑定 + 初始化
  // ----------------------------------------------------------------
  $("up-provider").addEventListener("change", onProviderChange);
  $("up-key-save").addEventListener("click", saveKey);
  $("up-key-clear").addEventListener("click", clearAllKeys);
  $("up-interval-save").addEventListener("click", saveInterval);
  $("up-usage-btn").addEventListener("click", queryUsage);
  // v3.1.0+ Q12：disable_cache 复选框 + 实时保存
  $("up-disable-cache").checked = getDisableCache();
  $("up-disable-cache").addEventListener("change", (e) => {
    localStorage.setItem(DISABLE_CACHE_KEY, e.target.checked ? "true" : "false");
    showResult("up-result", e.target.checked
      ? "🔓 已开启 disableCache（Q12 绕过服务端缓存，每次都是新查询）"
      : "🔒 已关闭 disableCache（恢复 15 分钟缓存）", false);
  });
  // 初始化 interval 输入框
  $("up-interval").value = getIntervalMs();
  $("interval-status").textContent = `（当前：${getIntervalMs()}ms）`;
  loadProviders();   // 初始化加载 provider 列表

  // ----------------------------------------------------------------
  // 辅助
  // ----------------------------------------------------------------
  function showResult(id, html, isError) {
    const el = $(id);
    el.innerHTML = `<div class="${isError ? "error" : "info"}">${html}</div>`;
  }
})();
