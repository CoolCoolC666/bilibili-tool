// 状态：当前任务 id、SSE EventSource、log buffer
const state = {
  jobId: null,
  sse: null,
};

// DOM 引用
const el = (id) => document.getElementById(id);

async function refreshCacheInfo() {
  try {
    const r = await fetch("/api/cache/stats");
    const d = await r.json();
    if (!d.exists) {
      el("cache_info").textContent = "缓存：无";
    } else {
      el("cache_info").textContent =
        `缓存：${d.stats.ok + d.stats.failed} 条（成功 ${d.stats.ok} / 失败 ${d.stats.failed}）`;
    }
  } catch (e) {
    el("cache_info").textContent = "缓存：—";
  }
}

function setStatusBadge(s) {
  const tag = el("status_tag");
  tag.className = "status-tag " + s;
  tag.textContent = s;
}

function updateProgress(d) {
  const pct = d.total > 0 ? Math.round((d.processed / d.total) * 100) : 0;
  el("bar_fill").style.width = pct + "%";
  el("counter").textContent = `${d.processed} / ${d.total}  (${pct}%)`;
  el("ok_count").textContent = d.ok_count;
  el("failed_count").textContent = d.failed_count;
  el("from_cache").textContent = d.from_cache;
  setStatusBadge(d.status);
}

function appendLog(lines) {
  if (!lines || !lines.length) return;
  const log = el("log");
  for (const line of lines) {
    const span = document.createElement("span");
    if (line.includes("✓") || line.includes("完成")) span.className = "ok";
    else if (line.includes("✗") || line.includes("❌") || line.includes("异常")) span.className = "failed";
    else span.className = "info";
    span.textContent = line + "\n";
    log.appendChild(span);
  }
  log.scrollTop = log.scrollHeight;
}

function renderResults(results) {
  const tbody = el("result_body");
  tbody.innerHTML = "";
  for (const r of results) {
    const tr = document.createElement("tr");
    // 类型标签（v2.8.0：区分视频/专栏/番剧）
    const kind = r.kind || "video";
    let kindTag = "";
    if (kind === "article") kindTag = '<span class="kind-tag article">专栏</span>';
    else if (kind === "bangumi") kindTag = '<span class="kind-tag bangumi">番剧</span>';
    else kindTag = '<span class="kind-tag video">视频</span>';
    // ID 列：视频显示 BV/AV；专栏显示 cv；番剧显示 ss/ep
    let idText = "";
    if (kind === "article") idText = r.cv_id || r.raw_input || "";
    else if (kind === "bangumi") {
      idText = r.season_id ? `ss${r.season_id}` : (r.ep_id ? `ep${r.ep_id}` : (r.raw_input || ""));
    } else {
      idText = r.bvid || r.aid || r.raw_input || "";
    }
    // UP/作者/番剧类型 三选一
    let meta = "";
    if (kind === "article") meta = escapeHtml(r.author_name || "");
    else if (kind === "bangumi") meta = escapeHtml((r.type_name || "") + (r.rating_score ? ` · ⭐${r.rating_score}` : ""));
    else meta = escapeHtml(r.up_name || "");
    // 描述：专栏用 summary，番剧用 desc，视频用 desc
    let desc = r.desc || r.summary || "";
    tr.innerHTML = `
      <td>${kindTag}<br/><span class="${r.status === "ok" ? "ok" : "failed"}">${r.status === "ok" ? "✓ ok" : "✗ " + (r.status || "fail")}</span></td>
      <td>${idText}</td>
      <td class="title-cell">${escapeHtml(r.title || "(无标题)")}<br/>
          <span class="desc-cell">${escapeHtml((desc || "").slice(0, 80))}</span></td>
      <td>${meta}</td>
      <td class="num">${fmt(r.view)}</td>
      <td class="num">${fmt(r.like)}</td>
      <td class="num">${fmt(r.reply)}</td>
      <td>${r.pubdate || r.publish_date || r.pubtime || ""}</td>
      <td>${r.url ? `<a href="${r.url}" target="_blank">打开</a>` : ""}</td>
    `;
    tbody.appendChild(tr);
  }
}

function renderDownloads(outputs) {
  const box = el("downloads");
  box.innerHTML = "";
  for (const fmt of Object.keys(outputs)) {
    const a = document.createElement("a");
    a.href = `/api/outputs/${outputs[fmt]}`;
    a.textContent = `下载 ${fmt.toUpperCase()}`;
    a.download = outputs[fmt];
    box.appendChild(a);
  }
}

function fmt(n) {
  if (n === null || n === undefined || n === "") return "";
  if (typeof n === "number") return n.toLocaleString();
  return n;
}

function escapeHtml(s) {
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function startJob() {
  const targets = el("targets").value.trim();
  if (!targets) {
    alert("请输入要抓取的 AV / BV / URL");
    return;
  }
  const options = {
    targets,
    delay: parseFloat(el("delay").value) || 0.5,
    retry: parseInt(el("retry").value) || 1,
    timeout: parseFloat(el("timeout").value) || 10.0,
    no_cache: el("no_cache").checked,
    allow_bare_numbers: el("allow_bare_numbers").checked,
    max_age: el("max_age").value || "1h",
    dedupe: el("dedupe").checked,
    exclude_invalid: el("exclude_invalid").checked,
    fetch_articles: el("fetch_articles").checked,
    fetch_bangumi: el("fetch_bangumi").checked,
  };

  el("start").disabled = true;
  el("progress_card").hidden = false;
  el("result_card").hidden = true;
  el("log").textContent = "";
  el("bar_fill").style.width = "0%";
  el("counter").textContent = "0 / 0";
  el("ok_count").textContent = 0;
  el("failed_count").textContent = 0;
  el("from_cache").textContent = 0;
  setStatusBadge("pending");

  try {
    const r = await fetch("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(options),
    });
    if (!r.ok) {
      const d = await r.json();
      alert("启动失败：" + (d.error || r.statusText));
      el("start").disabled = false;
      return;
    }
    const d = await r.json();
    state.jobId = d.id;
    openSSE(d.id);
  } catch (e) {
    alert("网络错误：" + e.message);
    el("start").disabled = false;
  }
}

function openSSE(jobId) {
  if (state.sse) state.sse.close();
  const es = new EventSource(`/api/jobs/${jobId}/stream`);
  state.sse = es;
  es.onmessage = (ev) => {
    try {
      const d = JSON.parse(ev.data);
      updateProgress(d);
      appendLog(d.new_logs);
      if (d.status === "done" || d.status === "error") {
        es.close();
        state.sse = null;
        el("start").disabled = false;
        fetchFinal(jobId);
      }
    } catch (e) {
      // ignore
    }
  };
  es.onerror = () => {
    // 浏览器会自动重连；任务结束后服务端会关闭
  };
}

async function fetchFinal(jobId) {
  try {
    const r = await fetch(`/api/jobs/${jobId}`);
    const d = await r.json();
    if (d.results) {
      el("result_card").hidden = false;
      renderResults(d.results);
      renderDownloads(d.outputs || {});
    }
    refreshCacheInfo();
  } catch (e) {
    appendLog(["获取结果失败：" + e.message]);
  }
}

document.getElementById("start").addEventListener("click", startJob);
document.getElementById("clear_log").addEventListener("click", () => {
  el("log").textContent = "";
});

refreshCacheInfo();
setInterval(refreshCacheInfo, 5000);
