// 视频号「视频管理」列表：按关键词锁定目标作品卡片 → 定位它操作栏里的「删除」条目。
// __ARG__       = 作品**文案**关键词（必填，必须能在卡片 textContent 里命中）
// __CLICKDEL__  = true 才允许点「删除」条目（**只有 Python 侧显式 --apply 才置 true**）
// __CLICKMORE__ = true 允许点卡片里的「更多」展开按钮（无害，只是展开菜单）
//
// ★★ 安全约定（2026-09-21 封面误改事故的教训，逐步照抄 _sh_open_list_entry.js）：
//   1) 关键词没命中 → ok=false 并回传前 8 条卡片文案(heads)，**绝不退化成列表第一条**。
//   2) 本脚本**只定位、只高亮**；__CLICKDEL__ !== true 时**一个删除类按钮都不点**。
//   3) 「删除」条目按**文案**挑（不按类名猜），因为类名未实测过：先把目标卡片里所有
//      `[class*="opr-item"]` 条目的 className/text/rect 全 dump 出来(entries)，
//      再挑 textContent 含「删除」且**面积最小**的那个（最内层热区）。挑不到 → ok=false。
//   4) 删除 / 编辑封面都是**不可逆**动作，命中不确定就宁可失败。
//
// ★ 卡片 textContent = **作品描述的正文**（视频号列表不显示短标题）。关键词要取自
//   ``publishtask.desc`` 首段；拿短标题会一张卡都匹配不到（2026-09-21 实测）。
// ★ 操作栏条目在 **shadow DOM** 里（父级 .opr / 祖父 .post-feed-item），条目类名形如
//   `opr-item-wrap` + 语义后缀（已知「修改描述和封面」那条是 div.opr-item-wrap.edit-cover-item）。
// ★ Vue 事件走原生 addEventListener + 节点在 shadow DOM：Playwright 的 locator.click()
//   会「点击成功但毫无反应」，只有 JS el.click() 才真正触发处理器 —— 所以这里点两次
//   （内层 div.opr-item + 外层 wrap），与 _sh_open_list_entry.js 一致。
// ★ 视口必须 ≥1920 宽：操作栏 rect.x ≈ 1353，1280 视口下被挤到屏幕外点不到。
// ★ 列表在微前端里渲染时机不定（实测同一命令有时 total=12、有时 total=0），
//   所以这里自己轮询等，不靠调用方固定 sleep。
(async () => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const kw = String(__ARG__ || "");
  const clickDel = (__CLICKDEL__ === true);
  const clickMore = (__CLICKMORE__ === true);
  const norm = (s) => (s || "").replace(/\s+/g, "").trim();
  const clsOf = (el) => String((el && el.className) || "").slice(0, 90);
  const rr = (el) => {
    const b = el.getBoundingClientRect();
    return [Math.round(b.x), Math.round(b.y), Math.round(b.width), Math.round(b.height)];
  };
  const area = (el) => { try { const b = el.getBoundingClientRect(); return b.width * b.height; }
                         catch (e) { return 1e12; } };
  const vis = (el) => {
    try {
      const cs = getComputedStyle(el);
      if (cs.display === "none" || cs.visibility === "hidden") return false;
      if (Number(cs.opacity) === 0) return false;
      const b = el.getBoundingClientRect();
      return b.width > 1 && b.height > 1;
    } catch (e) { return false; }
  };
  const inShadow = (el) => { try { return el.getRootNode() !== document; } catch (e) { return false; } };

  const roots = () => {
    const out = [{ root: document }];
    const dig = (r, d) => {
      if (!r || d > 5) return;
      let els = [];
      try { els = r.querySelectorAll("*"); } catch (e) { return; }
      for (const el of els) {
        if (el.shadowRoot) { out.push({ root: el.shadowRoot }); dig(el.shadowRoot, d + 1); }
      }
    };
    dig(document, 0);
    for (const f of document.querySelectorAll("iframe")) {
      let d = null;
      try { d = f.contentDocument; } catch (e) { d = null; }
      if (d && d.body) { out.push({ root: d }); dig(d, 0); }
    }
    return out;
  };

  const collect = () => {
    const items = [];
    for (const item of roots()) {
      let els = [];
      try { els = item.root.querySelectorAll('[class*="post-feed-item"]'); } catch (e) { continue; }
      for (const el of els) if (items.indexOf(el) < 0) items.push(el);
    }
    return items;
  };

  // 递归扫一个根的 shadow DOM（含根本身的 shadowRoot），收集命中选择器的元素
  const scanSel = (root, depth, sel, out) => {
    if (!root || depth > 6) return;
    let els = [];
    try { els = root.querySelectorAll(sel); } catch (e) { els = []; }
    for (const el of els) if (out.indexOf(el) < 0) out.push(el);
    const sub = [];
    if (root.shadowRoot) sub.push(root.shadowRoot);
    let all = [];
    try { all = root.querySelectorAll("*"); } catch (e) { all = []; }
    for (const el of all) if (el.shadowRoot) sub.push(el.shadowRoot);
    for (const s of sub) scanSel(s, depth + 1, sel, out);
  };

  // ── 0) 等列表渲染 ────────────────────────────────────────────────────────
  let items = [];
  let waited = 0;
  for (let i = 0; i < 26; i++) {
    items = collect();
    if (items.length) break;
    await sleep(2500);
    waited += 2500;
  }
  if (!items.length) {
    return { ok: false, why: "等了 " + Math.round(waited / 1000) + "s 页面仍没有 post-feed-item",
             total: 0, kw, entryFound: false, dialogShown: false, heads: [] };
  }
  const heads = items.slice(0, 8).map((el) => norm(el.textContent).slice(0, 60));
  const base = { total: items.length, waitedMs: waited, kw, heads };
  const fail = (why, extra) => Object.assign(
    { ok: false, why }, base, { entryFound: false, dialogShown: false }, extra || {});

  // ── 1) 按关键词锁定卡片（★ 绝不退回第一条） ──────────────────────────────
  if (!kw) {
    // 没给关键词 = 无法确定点哪一条。以前同类脚本会退化成「点列表第一条」，
    // 等价于随机挑一条作品去删（**不可逆**）⇒ 直接中止。
    return fail("没给关键词，按「绝不猜」中止（绝不点列表第一条）");
  }
  let target = null;
  for (const el of items) {
    if (norm(el.textContent).indexOf(norm(kw)) >= 0) { target = el; break; }
  }
  if (!target) {
    // ★ 2026-09-21 事故同源：给了关键词却没有任何卡片命中时，原实现静默取 items[0]
    //   （= 列表最新一条），把 A 的封面改到了 B 上，且视频号不可撤回。
    //   ⇒ 现在宁可失败，绝不猜。
    return fail("列表里没有卡片的文案包含关键词「" + kw + "」，按「绝不猜」中止（不再取第一条）");
  }
  const title = norm(target.textContent).slice(0, 46);

  // ── 2) dump 目标卡片操作栏里的所有条目 ───────────────────────────────────
  const listEntries = () => {
    const els = [];
    scanSel(target, 0, '[class*="opr-item"]', els);
    return els.map((el) => ({ el: el, info: {
      cls: clsOf(el), text: norm(el.textContent).slice(0, 24), tag: el.tagName,
      rect: rr(el), visible: vis(el), shadow: inShadow(el) } }));
  };
  // 「类名不是 opr-item」时的兜底视图：文案恰好是「删除」的节点，单独 dump 一份
  const listDeleteLike = () => {
    const els = [];
    scanSel(target, 0, "div,span,a,li,button", els);
    const out = [];
    for (const el of els) {
      const t = norm(el.textContent);
      if (t === "删除" || t === "删除作品" || t === "确认删除") {
        out.push({ el: el, info: {
          cls: clsOf(el), text: t, tag: el.tagName, rect: rr(el),
          visible: vis(el), shadow: inShadow(el) } });
      }
    }
    return out;
  };

  let entries = listEntries();
  let delLike = listDeleteLike();

  // 全页「含『删除』的短文案」清单（**含隐藏节点**）——用于在**不点任何删除按钮**的
  // 前提下，看二次确认弹层是不是已经预渲染在 DOM 里（视频号弹层常是 display:none 模板）。
  const listDelTexts = () => {
    const out = [];
    const seen = {};
    for (const item of roots()) {
      let els = [];
      try { els = item.root.querySelectorAll("div,span,a,li,button,p,label"); } catch (e) { continue; }
      for (const el of els) {
        let t = "";
        try { t = norm(el.textContent); } catch (e) { continue; }
        if (!t || t.length > 40 || t.indexOf("删除") < 0) continue;
        if (seen[t]) continue;
        seen[t] = 1;
        out.push({ text: t, cls: clsOf(el), tag: el.tagName, visible: vis(el),
                   rect: rr(el), shadow: inShadow(el) });
        if (out.length >= 25) return out;
      }
    }
    return out;
  };

  // 按**文案**挑「删除」条目（不猜类名）。2026-09-21 实测：操作栏一条 = 外层
  // div.opr-item-wrap(56×57) + 内层 icon div.opr-item(32×32) + 文字 div.action-content(24×17)，
  // 三者的 textContent 都含「删除」。**要点的是外层 wrap**（和 _sh_open_list_entry.js 点
  // .edit-cover-item 一致：Vue 的 @click 挂在 wrap 上），所以排序规则是
  // 「wrap 优先 → 可见优先 → 面积最小」。
  const isWrap = (one) => String(one.info.cls || "").indexOf("opr-item-wrap") >= 0;
  const rankOf = (one) => (isWrap(one) ? 2 : 0) + (one.info.visible ? 1 : 0);
  const pickDelete = (arr) => {
    let best = null;
    for (const one of arr) {
      if (one.info.text.indexOf("删除") < 0) continue;
      if (!best) { best = one; continue; }
      const br = rankOf(best), orank = rankOf(one);
      if (orank > br) { best = one; continue; }
      if (orank === br && area(one.el) < area(best.el)) best = one;
    }
    return best;
  };
  const cand = entries.concat(delLike.filter(
    (o) => !entries.some((e) => e.el === o.el)));
  let entry = pickDelete(cand);

  // ── 3) 可选：点一下卡片里的「更多」把操作栏展开（无害），再重扫 ──────────
  let moreClicked = null;
  if (!entry && clickMore) {
    let moreEl = null, moreInfo = null;
    const cands = [];
    scanSel(target, 0, "div,span,a,button,li", cands);
    for (const el of cands) {
      const t = norm(el.textContent);
      const c = clsOf(el).toLowerCase();
      const looksMore = (c.indexOf("more") >= 0) || (t === "更多") || (t === "...") || (t === "···");
      if (!looksMore) continue;
      if (!vis(el)) continue;
      if (area(el) > 40000) continue;              // 排除整卡/整栏
      const info = { cls: clsOf(el), text: t.slice(0, 8), tag: el.tagName, rect: rr(el) };
      if (!moreEl || area(el) < area(moreEl)) { moreEl = el; moreInfo = info; }
    }
    if (moreEl) {
      try { moreEl.scrollIntoView({ block: "center" }); } catch (e) {}
      try { moreEl.click(); } catch (e) {}
      moreClicked = moreInfo;
      await sleep(1800);
      entries = listEntries();
      delLike = listDeleteLike();
      entry = pickDelete(entries.concat(delLike));
    }
  }

  const dump = { entries: entries.map((o) => o.info), delLike: delLike.map((o) => o.info),
                 delTexts: listDelTexts(), moreClicked: moreClicked };

  if (!entry) {
    return Object.assign(
      { title: title, dialogShown: false }, base,
      { ok: false, entryFound: false, why: "这条作品的卡片里没找到「删除」条目（操作栏 dump 见 entries/delLike）" },
      dump);
  }

  // ── 4) 高亮「删除」条目的位置（截图取证用，不改页面逻辑） ────────────────
  try { entry.el.scrollIntoView({ block: "center" }); } catch (e) {}
  await sleep(500);
  try {
    entry.el.setAttribute("data-sh-del-mark", "1");
    entry.el.style.outline = "3px solid #ff2d2d";
    entry.el.style.outlineOffset = "2px";
    entry.el.style.background = "rgba(255,45,45,0.18)";
  } catch (e) {}
  // ★ 2026-09-21 实测：不 hover 卡片时操作栏**有布局盒但不绘制**（rect 56×57 正常，
  //   截图里那块是空白），所以光给元素本身加 outline 在截图上看不见。
  //   ⇒ 另画一个 **position:fixed** 的红框 + 文字标签，钉在它的屏幕矩形上。
  const entryRect = rr(entry.el);
  try {
    const box = document.createElement("div");
    box.setAttribute("data-sh-del-box", "1");
    box.style.cssText = "position:fixed;z-index:2147483646;pointer-events:none;" +
      "box-sizing:border-box;border:3px solid #ff2d2d;background:rgba(255,45,45,0.10);" +
      "left:" + entryRect[0] + "px;top:" + entryRect[1] + "px;" +
      "width:" + Math.max(entryRect[2], 24) + "px;height:" + Math.max(entryRect[3], 20) + "px;";
    document.body.appendChild(box);
    const lab = document.createElement("div");
    lab.setAttribute("data-sh-del-label", "1");
    lab.textContent = "★删除入口";
    lab.style.cssText = "position:fixed;z-index:2147483647;pointer-events:none;" +
      "font:12px/16px sans-serif;color:#fff;background:#ff2d2d;padding:2px 4px;" +
      "left:" + Math.max(0, entryRect[0]) + "px;top:" +
      Math.max(0, entryRect[1] - 20) + "px;";
    document.body.appendChild(lab);
  } catch (e) {}

  const out = Object.assign({}, base, {
    ok: true, title: title, entryFound: true,
    entryText: entry.info.text, entryCls: entry.info.cls, entryTag: entry.info.tag,
    rect: entryRect, cardRect: rr(target), visible: vis(entry.el), shadow: inShadow(entry.el),
    clickedDelete: false, moreClicked: moreClicked,
  }, dump);

  // ── 5) 扫页面里已有的对话框（含**隐藏**模板：视频号的弹层常常是预渲染后 display:none）
  const findDialogs = () => {
    const found = [];
    for (const item of roots()) {
      let els = [];
      try {
        els = item.root.querySelectorAll(
          '[class*="dialog"],[class*="modal"],[class*="popup"],[class*="confirm"],[role="dialog"]');
      } catch (e) { continue; }
      for (const el of els) {
        const t = norm(el.textContent);
        if (t.indexOf("删除") < 0) continue;
        const btns = [];
        let inner = [];
        try { inner = el.querySelectorAll("button,a,div,span"); } catch (e) { inner = []; }
        for (const b of inner) {
          const bt = norm(b.textContent);
          if (!bt || bt.length > 8) continue;
          if (bt.indexOf("取消") < 0 && bt.indexOf("删除") < 0 && bt.indexOf("确定") < 0
              && bt.indexOf("确认") < 0) continue;
          if (!vis(b)) continue;
          const one = { text: bt, cls: clsOf(b), tag: b.tagName, rect: rr(b) };
          if (!btns.some((x) => x.text === one.text && x.rect[0] === one.rect[0])) btns.push(one);
        }
        const one = { cls: clsOf(el), visible: vis(el), rect: rr(el),
                      text: t.slice(0, 160), btns: btns.slice(0, 6) };
        if (!found.some((x) => x.cls === one.cls && x.text === one.text)) found.push(one);
      }
    }
    return found.slice(0, 6);
  };

  let dialogs = findDialogs();
  const dlgVisible = () => dialogs.some((d) => d.visible);

  // ── 6) 只有显式 __CLICKDEL__=true 才点「删除」条目，并等二次确认弹窗 ─────
  if (clickDel) {
    // 点两次：先点内层 div.opr-item（事件处理器挂在它上面），再点外层 wrap。
    const inner = entry.el.querySelector('[class*="opr-item"]');
    try { if (inner) inner.click(); } catch (e) {}
    try { entry.el.click(); } catch (e) {}
    out.clickedDelete = true;
    for (let i = 0; i < 12; i++) {
      await sleep(1500);
      dialogs = findDialogs();
      if (dlgVisible()) break;
    }
  }

  out.dialogShown = dlgVisible();
  out.dialogs = dialogs;
  out.url = String(location.href).slice(0, 160);
  out.inner = [window.innerWidth, window.innerHeight];
  return out;
})()
