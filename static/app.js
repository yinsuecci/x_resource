let items = [];
let imageItems = [];
let activeTag = "全部";
let activeImgCat = "全部";
let mode = "news";

const grid = document.getElementById("grid");
const empty = document.getElementById("empty");
const statusEl = document.getElementById("status");
const countLabel = document.getElementById("countLabel");
const updatedLabel = document.getElementById("updatedLabel");
const refreshBtn = document.getElementById("refreshBtn");
const refreshImagesBtn = document.getElementById("refreshImagesBtn");
const imageGrid = document.getElementById("imageGrid");
const imgEmpty = document.getElementById("imgEmpty");
const imgCountLabel = document.getElementById("imgCountLabel");
const newsPanel = document.getElementById("newsPanel");
const imagesPanel = document.getElementById("imagesPanel");
const tabNews = document.getElementById("tabNews");
const tabImages = document.getElementById("tabImages");

function toast(msg) {
  let el = document.querySelector(".toast");
  if (!el) {
    el = document.createElement("div");
    el.className = "toast";
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(toast._t);
  toast._t = setTimeout(function () {
    el.classList.remove("show");
  }, 1800);
}

function formatTime(iso) {
  if (!iso) return "尚未刷新";
  try {
    const d = new Date(iso);
    return "更新于 " + d.toLocaleString("zh-CN", { hour12: false });
  } catch (e) {
    return "更新时间未知";
  }
}

function filtered() {
  if (activeTag === "全部") return items;
  return items.filter(function (it) {
    return (it.tags || []).indexOf(activeTag) >= 0;
  });
}

function postText(it) {
  return [
    it.hook || it.title_zh || it.title,
    "",
    it.summary_zh || "",
    "",
    "来源：" + it.source,
    "链接：" + it.link,
  ].join("\n");
}

function imagePostText(im) {
  const size = im.width && im.height ? im.width + "×" + im.height : "";
  return [
    "【美图背景·" + (im.category || "") + "】" + (im.title || ""),
    im.author ? "作者：" + im.author : "",
    "来源：" + im.source + (size ? " · " + size : ""),
    "作品页：" + (im.page_url || ""),
    "图片：" + (im.image_url || im.thumb_url || ""),
  ]
    .filter(Boolean)
    .join("\n");
}

function copyText(text) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(
      function () {
        toast("已复制");
      },
      function () {
        fallbackCopy(text);
      }
    );
  } else {
    fallbackCopy(text);
  }
}

function fallbackCopy(text) {
  const ta = document.createElement("textarea");
  ta.value = text;
  document.body.appendChild(ta);
  ta.select();
  document.execCommand("copy");
  ta.remove();
  toast("已复制");
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
function escapeAttr(s) {
  return escapeHtml(s).replace(/'/g, "&#39;");
}

function setMode(next) {
  mode = next || "news";
  if (tabNews) tabNews.classList.toggle("active", mode === "news");
  if (tabImages) tabImages.classList.toggle("active", mode === "images");
  if (newsPanel) newsPanel.classList.toggle("hidden", mode !== "news");
  if (imagesPanel) imagesPanel.classList.toggle("hidden", mode !== "images");
  if (refreshBtn) refreshBtn.classList.toggle("hidden", mode !== "news");
  if (refreshImagesBtn) refreshImagesBtn.classList.toggle("hidden", mode !== "images");
  if (statusEl) {
    statusEl.textContent = mode === "images" ? "美图模式" : "热点发文模式";
  }
  if (mode === "images" && imageItems.length === 0) {
    loadImages();
  }
}

function render() {
  const list = filtered();
  if (countLabel) countLabel.textContent = list.length + " 条可发";
  if (!grid) return;
  grid.innerHTML = "";
  if (!list.length) {
    if (empty) empty.classList.remove("hidden");
    return;
  }
  if (empty) empty.classList.add("hidden");
  for (let i = 0; i < list.length; i++) {
    const it = list[i];
    const card = document.createElement("article");
    card.className = "card";
    const tags = (it.tags || [])
      .map(function (t) {
        return '<span class="tag">' + escapeHtml(t) + "</span>";
      })
      .join("");
    card.innerHTML =
      '<div class="card-head"><div><div class="source">' +
      escapeHtml(it.source || "") +
      '</div><div class="tags" style="margin-top:0.35rem">' +
      tags +
      '</div></div><div class="score">流量分 ' +
      (it.score != null ? it.score : "-") +
      '</div></div><h2 class="title">' +
      escapeHtml(it.title_zh || it.title || "") +
      '</h2><p class="hook">' +
      escapeHtml(it.hook || "") +
      '</p><p class="summary">' +
      escapeHtml(it.summary_zh || "") +
      '</p><p class="orig">原文：' +
      escapeHtml(it.title || "") +
      '</p><a class="link" href="' +
      escapeAttr(it.link || "#") +
      '" target="_blank" rel="noopener noreferrer">' +
      escapeHtml(it.link || "") +
      '</a><div class="actions"><button type="button" class="btn ghost" data-act="copy">复制发文</button><button type="button" class="btn ghost" data-act="copy-link">只复制链接</button><a class="btn ghost" href="' +
      escapeAttr(it.link || "#") +
      '" target="_blank" rel="noopener noreferrer" style="text-decoration:none">打开原文</a></div>';
    card.querySelector('[data-act="copy"]').onclick = function () {
      copyText(postText(it));
    };
    card.querySelector('[data-act="copy-link"]').onclick = function () {
      copyText(it.link || "");
    };
    grid.appendChild(card);
  }
}

function renderImages() {
  const list =
    activeImgCat === "全部"
      ? imageItems
      : imageItems.filter(function (im) {
          return im.category === activeImgCat;
        });
  if (imgCountLabel) imgCountLabel.textContent = list.length + " 张背景图";
  if (!imageGrid) return;
  imageGrid.innerHTML = "";
  if (!list.length) {
    if (imgEmpty) imgEmpty.classList.remove("hidden");
    return;
  }
  if (imgEmpty) imgEmpty.classList.add("hidden");
  for (let i = 0; i < list.length; i++) {
    const im = list[i];
    const card = document.createElement("article");
    card.className = "img-card";
    const tags = (im.tags || [])
      .slice(0, 5)
      .map(function (t) {
        return '<span class="tag">' + escapeHtml(String(t)) + "</span>";
      })
      .join("");
    const size = im.width && im.height ? im.width + "×" + im.height : "";
    card.innerHTML =
      '<div class="img-frame"><img src="' +
      escapeAttr(im.thumb_url || im.image_url || "") +
      '" alt="' +
      escapeAttr(im.title || "") +
      '" loading="lazy" referrerpolicy="no-referrer" /></div><div class="img-body"><div class="img-meta"><span>' +
      escapeHtml(im.source || "") +
      "</span><span>" +
      escapeHtml(im.category || "") +
      (size ? " · " + size : "") +
      '</span></div><h3 class="img-title">' +
      escapeHtml(im.title || "") +
      "</h3>" +
      (im.author ? '<p class="img-author">' + escapeHtml(im.author) + "</p>" : "") +
      '<div class="img-tags">' +
      tags +
      '</div><div class="actions"><button type="button" class="btn ghost" data-act="copy">复制出处</button><button type="button" class="btn ghost" data-act="copy-img">复制图片链接</button><a class="btn ghost" href="' +
      escapeAttr(im.page_url || "#") +
      '" target="_blank" rel="noopener noreferrer" style="text-decoration:none">打开原页</a></div></div>';
    card.querySelector('[data-act="copy"]').onclick = function () {
      copyText(imagePostText(im));
    };
    card.querySelector('[data-act="copy-img"]').onclick = function () {
      copyText(im.image_url || im.thumb_url || "");
    };
    imageGrid.appendChild(card);
  }
}

function loadFeed() {
  return fetch("/api/feed")
    .then(function (res) {
      return res.json();
    })
    .then(function (data) {
      items = data.items || [];
      if (updatedLabel) updatedLabel.textContent = formatTime(data.updated_at);
      if (statusEl) {
        statusEl.textContent = data.refreshing
          ? data.message || "刷新中…"
          : data.message || (items.length ? "就绪" : "点击刷新拉取推送");
      }
      render();
      return data;
    });
}

function refresh() {
  if (refreshBtn) refreshBtn.disabled = true;
  if (statusEl) statusEl.textContent = "正在抓取并生成中文摘要…";
  fetch("/api/refresh?force=true", { method: "POST" })
    .then(function (res) {
      return res.json();
    })
    .then(function (data) {
      items = data.items || items;
      if (updatedLabel) updatedLabel.textContent = formatTime(data.updated_at);
      if (statusEl) statusEl.textContent = data.message || (data.ok ? "刷新完成" : "刷新失败");
      render();
      toast(data.ok ? "已更新 " + items.length + " 条" : data.message || "刷新失败");
    })
    .catch(function (e) {
      if (statusEl) statusEl.textContent = "网络或服务异常";
      toast(String(e));
    })
    .finally(function () {
      if (refreshBtn) refreshBtn.disabled = false;
    });
}

function loadImages() {
  if (refreshImagesBtn) refreshImagesBtn.disabled = true;
  if (statusEl) statusEl.textContent = "正在拉取美图…";
  fetch("/api/images?category=" + encodeURIComponent(activeImgCat))
    .then(function (res) {
      return res.json();
    })
    .then(function (data) {
      imageItems = data.items || [];
      const errN = data.errors && data.errors.length ? data.errors.length : 0;
      if (statusEl) {
        statusEl.textContent = "美图 " + imageItems.length + " 张" + (errN ? "（" + errN + " 个源失败）" : "");
      }
      renderImages();
      toast("已加载 " + imageItems.length + " 张");
    })
    .catch(function (e) {
      if (statusEl) statusEl.textContent = "美图拉取失败";
      toast(String(e));
    })
    .finally(function () {
      if (refreshImagesBtn) refreshImagesBtn.disabled = false;
    });
}

if (tabNews) {
  tabNews.onclick = function (e) {
    e.preventDefault();
    e.stopPropagation();
    setMode("news");
  };
}
if (tabImages) {
  tabImages.onclick = function (e) {
    e.preventDefault();
    e.stopPropagation();
    setMode("images");
  };
}

const filtersEl = document.getElementById("filters");
if (filtersEl) {
  filtersEl.onclick = function (e) {
    const btn = e.target.closest ? e.target.closest(".chip") : null;
    if (!btn) return;
    e.preventDefault();
    const chips = filtersEl.querySelectorAll(".chip");
    for (let i = 0; i < chips.length; i++) chips[i].classList.remove("active");
    btn.classList.add("active");
    activeTag = btn.getAttribute("data-tag") || "全部";
    render();
    toast("筛选：" + activeTag);
  };
}

const imageFiltersEl = document.getElementById("imageFilters");
if (imageFiltersEl) {
  imageFiltersEl.onclick = function (e) {
    const btn = e.target.closest ? e.target.closest(".chip") : null;
    if (!btn) return;
    e.preventDefault();
    const chips = imageFiltersEl.querySelectorAll(".chip");
    for (let i = 0; i < chips.length; i++) chips[i].classList.remove("active");
    btn.classList.add("active");
    activeImgCat = btn.getAttribute("data-img-cat") || "全部";
    loadImages();
  };
}

if (refreshBtn) refreshBtn.onclick = refresh;
if (refreshImagesBtn) refreshImagesBtn.onclick = loadImages;

setMode("news");

loadFeed()
  .then(function () {
    if (!items.length) refresh();
  })
  .catch(function (e) {
    if (statusEl) statusEl.textContent = "加载失败，请确认已启动本地服务";
    toast(String(e));
  });
