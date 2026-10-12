"""抖音发布时顺带设置**竖封面 3:4**(任务级 ``cover_path``,best-effort)。

设计决策
--------
1. **任务级封面**:每条发布任务自带 ``cover_path``(不是进程级环境变量),由
   ``PublishTask.cover_path`` / ``PublishIn.cover_path`` 一路传到发布器。
2. **只设竖封面 3:4**:抖音信息流主展示位是竖封面;横封面 4:3 本轮不做。
3. **best-effort**:抖音不设封面就是取视频首帧,发布照常成功 —— 所以这里失败
   **绝不阻断发布**,只把原因串回给调用方记日志。
   (对照:视频号封面是**发布前置条件**,设不上会卡在「发表」校验弹层,所以
   ``channels/publish.py::_set_cover`` 失败必须明确回报。)

2026-09-14 已实测结论(防「假成功」的三条)
------------------------------------------
1. 文案为「设置封面」的只是**区块标题 DIV**,点它什么都不发生;真正能点的是
   「选择封面」/「编辑封面」。
2. 封面弹层里**还有**「AI生成封面 / 生成参考图」区的别的 ``input[type=file]``。
   按「第一个 ``accept`` 含 image 的 input」投喂会**喂错地方** —— 编辑器照常关闭、
   封面 ``src`` 也变了,但封面其实没换(典型假成功)。判据必须是祖先文案**同时**
   命中「拖拽」和「上传封面」。
3. 封面是否真换了**只能看像素** —— ``img.src`` 在上传未生效时也会变(换 CDN 变体)。

2026-09-21 补上「生效确认 + 失败换路重试」
------------------------------------------
投喂成功、弹层收起都**不等于**封面挂上去了(第 4 条:像素才作数)。所以第 9 步读回
封面区的实际状态后,再过一道 :func:`_cover_verdict` 三态判定:
``changed``(已生效)/ ``unchanged``(明确没变 → 才值得重试)/ ``unknown``(**判不准**
→ fail-open 当作已生效,绝不重试)。判 ``unchanged`` 时由 :func:`_confirm_cover`
**换路**(重开封面编辑器 → 重新 ``set_input_files`` 投喂)最多重试 3 轮。
返回串只在「重试完仍明确没生效」时非空;确认逻辑只**加日志与重试**,不新增 ``raise``、
不提前 ``return`` 中断发布 —— 与同日视频号 ``channels/publish.py::_set_cover`` 同一套
口径(那边是发布前置条件,这边是 best-effort)。

对外只暴露 :func:`set_douyin_cover`。本模块**自带** logger,刻意不 import
``publish.py`` 的 ``_log``(会形成循环导入)。
"""
from __future__ import annotations

import hashlib
import time
from datetime import datetime
from pathlib import Path

# 上传前的封面像素基线必须**先**取(此时缩略图是干净像素),再打开封面编辑器。
# 打开编辑器时会注入 hover-show 样式,必须能撤掉 —— 见 _force_show_hover。
_HOVER_STYLE_ID = "chrc-hover-show"

_DEBUG_DIR = Path("./data/debug")


def _log(msg: str) -> None:
    """本模块专用 logger(不依赖 publish.py,避免循环导入)。"""
    print(f"[dy-cover] {msg}", flush=True)


# ── 内联的 JS 片段(运行时**不能**依赖 scripts/,必须自带)──────────────────
#
# 1) 把封面弹层里**真正的投放区** input[type=file] 标上 data-bfc-upload="1"。
#    见 scripts/_mark_upload_input.js 的注释:同一页面还有「AI生成封面/生成参考图」
#    区的别的图片输入框,按「第一个 accept 含 image」投喂会喂错地方 —— 编辑器照常
#    关闭、封面 src 也变了,但封面其实没换。判据:向上 6 层祖先文案**同时**含
#    「拖拽」+「上传封面」。
_MARK_UPLOAD_JS = r"""
(() => {
  const norm = (s) => (s || "").replace(/\s+/g, " ").trim();
  const inputs = Array.from(document.querySelectorAll('input[type="file"]'));
  inputs.forEach((el) => el.removeAttribute("data-bfc-upload"));
  const scored = inputs.map((el, index) => {
    let parent = el.parentElement;
    let chainText = "";
    for (let depth = 0; depth < 6 && parent; depth += 1, parent = parent.parentElement) {
      chainText += " " + norm(parent.textContent);
    }
    const cls = String(el.className || "");
    let score = 0;
    if (chainText.includes("拖拽")) score += 10;
    if (chainText.includes("上传封面")) score += 10;
    if (cls.includes("semi-upload-hidden-input") && !cls.includes("replace")) score += 5;
    if ((el.accept || "").includes("image")) score += 2;
    if (el.getBoundingClientRect().width > 0) score += 1;
    return { index, score, accept: el.accept || "", tag: el.tagName,
             cls: cls.slice(0, 60),
             drag: chainText.includes("拖拽"),
             chainHit: chainText.includes("拖拽") && chainText.includes("上传封面") };
  });
  // 只接受「投放区」:优先同时命中「拖拽」+「上传封面」。
  // ★ 2026-09-21 事故(Task #62):抖音改版把「上传封面」挪到了弹层左侧工具栏,
  //   与投放区不再同一子树 ⇒ chainHit 恒为 false ⇒ 一个都不标 ⇒ 文件根本没喂进去,
  //   残留弹层随后吃掉「发布」的点击(同批改版还新增了「视频预览功能」提示条)。
  //   放宽:chainHit 优先;退而求其次**只认「拖拽」**这一投放区独有文案。
  //   ★ 放宽**不能**退到 `score >= 10`:「上传封面」单独命中也是 10 分,而它现在长在
  //     弹层左侧工具栏的按钮上,工具栏自己也可能带隐藏 file input(它的评分可能是
  //     10+5+2+1=18,比投放区的 10+5+2+1=18 还高) ⇒ 会喂错地方,而且**静默**
  //     (封面没换但流程照走)。`drag` 是布尔硬条件,不看分数。
  let qualified = scored.filter((o) => o.chainHit);
  const relaxed = qualified.length === 0;
  if (relaxed) {
    qualified = scored.filter((o) => o.drag);
  }
  qualified.sort((a, b) => b.score - a.score);
  if (qualified.length) {
    inputs[qualified[0].index].setAttribute("data-bfc-upload", "1");
  }
  return { total: inputs.length, selected: qualified.length ? qualified[0] : null,
           relaxed, scored };
})();
"""

# 2) 把「封面」区的两张缩略图标上 data-bfc-thumb="1",供元素级截图做像素指纹。
#    ★ 锚点是**标签文案**「竖封面3:4 / 横封面4:3」,不是 img[src*=...](上传生效后
#      封面 src 会换 CDN host,按 URL 匹配更不稳)。
_MARK_THUMBS_JS = r"""
(() => {
  const norm = (s) => (s || "").replace(/\s+/g, " ").trim();
  const LABELS = ["竖封面3:4", "横封面4:3"];
  document.querySelectorAll("[data-bfc-thumb]").forEach(
    (el) => el.removeAttribute("data-bfc-thumb"));
  const anchors = Array.from(document.querySelectorAll("div,span,p,label"))
    .filter((el) => el.children.length <= 2 && LABELS.includes(norm(el.textContent)));
  const marked = [];
  for (const anchor of anchors) {
    let node = anchor;
    let img = null;
    for (let depth = 0; depth < 5 && node; depth += 1, node = node.parentElement) {
      const cand = node.querySelector("img");
      if (cand) { img = cand; break; }
    }
    if (!img) continue;
    img.setAttribute("data-bfc-thumb", "1");
    const r = img.getBoundingClientRect();
    marked.push({ label: norm(anchor.textContent),
                  src: (img.currentSrc || img.src || "").slice(0, 130),
                  w: Math.round(r.width), h: Math.round(r.height) });
  }
  // 2026-09-29 #133: 上传成功后，改版发布页把「竖封面3:4 / 横封面4:3」
  // 占位标签整个换成两张实际封面图，只保留行标题「设置封面」。此时原锚点
  // 数量为 0；必须在该行近邻内找图，不能把已应用的封面误判为无法确认。
  if (!marked.length) {
    const labels = Array.from(document.querySelectorAll('div,span,p,label'))
      .filter((el) => el.children.length <= 2 && norm(el.textContent) === '设置封面');
    for (const label of labels) {
      const lr = label.getBoundingClientRect();
      let node = label.parentElement;
      for (let depth = 0; depth < 6 && node; depth += 1, node = node.parentElement) {
        const imgs = Array.from(node.querySelectorAll('img')).filter((img) => {
          const r = img.getBoundingClientRect();
          return r.width >= 70 && r.height >= 85
            && r.x >= lr.right + 15 && Math.abs(r.y - lr.y) <= 160;
        }).slice(0, 2);
        if (!imgs.length) continue;
        for (const img of imgs) {
          img.setAttribute('data-bfc-thumb', '1');
          const r = img.getBoundingClientRect();
          marked.push({ label: '设置封面',
            src: (img.currentSrc || img.src || '').slice(0, 130),
            w: Math.round(r.width), h: Math.round(r.height) });
        }
        break;
      }
      if (marked.length) break;
    }
  }
  return { anchors: anchors.length, marked };
})();
"""

# 3) 在「竖封面3:4」锚点所属容器内找「选择封面」/「编辑封面」并标出来。
#    抖音编辑页实测顺序:设置封面 / 选择封面 / 竖封面3:4 / 选择封面 / 横封面4:3,
#    所以**首个**「选择封面」是竖封面的;为稳妥仍按锚点容器收窄。
_MARK_VERTICAL_COVER_JS = r"""
(() => {
  const norm = (s) => (s || "").replace(/\s+/g, " ").trim();
  document.querySelectorAll('[data-chrc-vcover="1"]').forEach(
    (el) => el.removeAttribute("data-chrc-vcover"));
  const anchor = Array.from(document.querySelectorAll("div,span,p,label"))
    .find((el) => el.children.length <= 2 && norm(el.textContent).includes("竖封面3:4"));
  if (!anchor) return { ok: false, why: "no-anchor" };
  const want = ["选择封面", "编辑封面"];
  let node = anchor;
  for (let depth = 0; depth < 6 && node; depth += 1, node = node.parentElement) {
    const cands = Array.from(node.querySelectorAll("div,span,button,a"));
    for (const c of cands) {
      const t = norm(c.textContent);
      const hit = want.some((w) => t === w || (t.includes(w) && t.length <= w.length + 4));
      if (hit) {
        c.setAttribute("data-chrc-vcover", "1");
        return { ok: true, text: t };
      }
    }
  }
  return { ok: false, why: "no-button" };
})();
"""

# 3b) 失败出口的几何诊断(2026-09-26):封面入口文案在 innerText 里、标记 JS 也能
#     命中,但 Playwright 点不中 —— 必须拿到每个入口的 rect + computed style 才能判
#     是「零尺寸」「透明」「被隐藏」还是「父容器塌了」。只读,不点任何东西。
_OPEN_FAIL_DIAG_JS = r"""
(() => {
  const norm = (s) => (s || "").replace(/\s+/g, " ").trim();
  const want = ["选择封面", "编辑封面", "竖封面3:4", "设置封面", "横封面4:3"];
  const out = [];
  const all = Array.from(document.querySelectorAll("div,span,button,a,p,label"));
  for (const el of all) {
    if (el.children.length > 2) continue;
    const t = norm(el.textContent);
    if (!t || !want.includes(t)) continue;
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    const chain = [];
    let p = el.parentElement;
    for (let d = 0; d < 3 && p; d += 1, p = p.parentElement) {
      const pcs = getComputedStyle(p);
      chain.push({ tag: p.tagName, cls: String(p.className || "").slice(0, 60),
                   disp: pcs.display, vis: pcs.visibility, h: Math.round(p.getBoundingClientRect().height) });
    }
    out.push({ text: t, tag: el.tagName, cls: String(el.className || "").slice(0, 60),
               x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height),
               disp: cs.display, vis: cs.visibility, opa: cs.opacity, pe: cs.pointerEvents,
               marked: el.hasAttribute("data-chrc-vcover"), chain });
    if (out.length >= 12) break;
  }
    return { n: out.length, items: out };
})();
"""

# 3c) 新版内嵌封面选择器的「上传」入口原生点击(2026-09-26,#97 第三轮实测)。
#     编辑页灰度 new-layout 后,「选择封面」打开的是嵌在右侧预览框里的封面选择器
#     (横封面/竖封面页签 + 候选瓦片 + 底部上传入口),不再是老弹层。Playwright 命中
#     测试会被「发文助手」浮卡拦,所以一律 JS 原生 el.click();同时老弹层路径里同名
#     文案入口仍在,兼容两代 UI。★ 优先在「竖封面」页签所在的容器树里找上传入口
#     (页签=选择器根的可靠锚点),找不到才放宽到整页。精确等值匹配,「重新上传」
#     (视频重传按钮!)不会被 "上传" 命中。
_PICKER_UPLOAD_CLICK_JS = r"""
(() => {
  const norm = (s) => (s || "").replace(/[\u200b-\u200d\ufeff]/g, "")
      .replace(/\s+/g, " ").trim();
  const all = Array.from(document.querySelectorAll("div,span,button,a,label"));
  const tab = all.find((el) => el.children.length <= 2 && norm(el.textContent) === "竖封面");
  const roots = [];
  for (let p = tab, i = 0; p && i < 8; i += 1, p = p.parentElement) roots.push(p);
  const want = ["上传封面", "本地上传", "上传文件", "点击上传", "上传"];
  const grab = (root) => {
    const out = [];
    for (const el of root.querySelectorAll("button, div, span, a, label")) {
      if (el.children.length > 2) continue;
      const t = norm(el.textContent);
      if (want.includes(t)) out.push(el);
    }
    return out;
  };
  let cands = [];
  for (const r of roots) { cands = grab(r); if (cands.length) break; }
  if (!cands.length) cands = grab(document);
  cands.sort((a, b) => norm(b.textContent).length - norm(a.textContent).length);
  const meta = cands.slice(0, 5).map((el) => {
    const r = el.getBoundingClientRect();
    const chain = [];
    for (let p = el.parentElement, d = 0; p && d < 6; d += 1, p = p.parentElement) {
      chain.push(norm(p.textContent).slice(0, 30));
    }
    return { t: norm(el.textContent), x: Math.round(r.x), y: Math.round(r.y),
             w: Math.round(r.width), h: Math.round(r.height),
             vis: r.width > 0 && r.height > 0, chain };
  });
  const clicked = [];
  for (const el of cands.slice(0, 5)) { el.click(); clicked.push(norm(el.textContent)); }
  return { scope: roots.length ? "picker" : "doc", n: cands.length, clicked, meta };
})();
"""

# 3d) 封面选择器结构扫描(filechooser 未命中时用):把「竖封面」页签所在容器树里的
#     可见文案与全部像按钮的元素(文案/类名/矩形)报出来 —— 上传入口若不是文本按钮
#     (图标/canvas/非常规文案),靠它定位。只读。
_PICKER_SCAN_JS = r"""
(() => {
  const norm = (s) => (s || "").replace(/[\u200b-\u200d\ufeff]/g, "")
      .replace(/\s+/g, " ").trim();
  const all = Array.from(document.querySelectorAll("div,span,button,a,label"));
  const ups = all.filter((el) => el.children.length <= 2
        && norm(el.textContent) === "上传封面").slice(0, 2).map((el) => {
      const chain = [];
      for (let p = el.parentElement, d = 0; p && d < 6; d += 1, p = p.parentElement) {
        chain.push(norm(p.textContent).slice(0, 36));
      }
      const r = el.getBoundingClientRect();
      return { w: Math.round(r.width), h: Math.round(r.height),
               vis: r.width > 0 && r.height > 0, chain };
    });
  const tab = all.find((el) => el.children.length <= 2
      && ["竖封面", "横封面"].includes(norm(el.textContent)));
  if (!tab) return { hit: false, ups };
  let root = tab;
  for (let i = 0; i < 8 && root.parentElement; i += 1) root = root.parentElement;
  const txt = norm(root.innerText || "").slice(0, 500);
  const els = [];
  for (const el of root.querySelectorAll("button, a, label, [role='button'], div, span")) {
    if (el.children.length > 3) continue;
    const t = norm(el.textContent);
    if (!t || t.length > 12) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 8 || r.height < 8) continue;
    els.push({ t, tag: el.tagName, cls: String(el.className || "").slice(0, 50),
               w: Math.round(r.width), h: Math.round(r.height) });
    if (els.length >= 30) break;
  }
  return { hit: true, txt, els, ups,
           inputs: root.querySelectorAll("input[type='file']").length };
})();
"""


# 4) 封面弹层底部「完成」的候选枚举 + JS 原生点击(第 2 层兜底)。
#
# ★ 2026-09-21 14:00 事故(Task #68)实测:投喂成功、`_secure_click_finish` 也没抛异常
#   (抛了就走不到第 8b 步),但弹层始终没收起 —— 90s 后的整页取证
#   `data/debug/dy_publish_clickfail_20260921_140331.png` 里弹层仍开着,底部一行是
#   【封面检测 | 完成 | 设置横封面】(文本顺序 …上传封面/点击上传文件或拖拽文件到这里/
#   封面检测/完成/设置横封面/竖封面预览(3:4)),「完成」是**灰底**样式;残留遮罩随后
#   吃掉了「发布」的点击(靠 publish.py 的 JS 原生 `el.click()` 才发出去)。
#   姊妹文件 publish.py 的 `_JS_CLICK_PUBLISH` 已证明:**JS 原生 `el.click()` 由元素
#   自身派发事件、不经 Playwright 的命中测试,遮挡拦不住它** —— 这里给「完成」补同一层。
#
# ★ 文案判据必须**排除**同一排/同一弹层里长得像的近名元素:「封面检测」只比「完成」
#   多一个「检测」,是最危险的误点目标;其次是两个 tab「设置竖封面 / 设置横封面」、
#   发文助手的「重新检测」、提示条的「我知道了」。中文还常夹零宽字符/换行,
#   统一走 `norm`(= `(s||"").replace(/\s+/g," ").trim()`,JS 的 `\s` 含 NBSP/全角空格)。
_JS_FINISH_CANDS = r"""
(doClick) => {
  const norm = (s) => (s || "").replace(/\s+/g, " ").trim();
  const bad = /封面检测|设置横封面|设置竖封面|重新检测|我知道了|取消|关闭|检测/;
  const all = Array.from(document.querySelectorAll(
      'button, [role="button"], a, div, span'));
  const grab = (pred) => {
    const hit = [];
    all.forEach((el) => {
      // textContent 不像 innerText 那样强制布局,候选再多也不会卡;先按「元素子节点
      // 数」把大容器剪掉(「完成」按钮的子树最多几个 <span>,包住整排按钮的容器必然更多)。
      if (el.children.length > 4) return;
      const t = norm(el.textContent);
      if (!t || !pred(t) || bad.test(t)) return;
      const r = el.getBoundingClientRect();
      const cls = String(el.className || "");
      hit.push({
        el, text: t, tag: el.tagName, cls,
        native: el.tagName === "BUTTON" || el.getAttribute("role") === "button",
        disabled: el.disabled === true || el.getAttribute("aria-disabled") === "true",
        clsDisabled: /disabled/i.test(cls),
        w: Math.round(r.width), h: Math.round(r.height),
        visible: r.width >= 10 && r.height >= 10,
        html: String(el.outerHTML || "").slice(0, 120),
      });
    });
    return hit;
  };
  // 第 1 轮只认**精确等于**「完成」;一轮都没命中的才退到「以完成结尾的短文案」。
  let hit = grab((t) => t === "完成");
  const exact = hit.length;
  if (!hit.length) hit = grab((t) => t.endsWith("完成") && t.length <= 6);
  const report = hit.map((o) => ({
    text: o.text, tag: o.tag, disabled: o.disabled, native: o.native,
    clsDisabled: o.clsDisabled, w: o.w, h: o.h, visible: o.visible,
    cls: o.cls.slice(0, 80), html: o.html,
  }));
  if (!hit.length) return { ok: false, why: "no-match", exact: 0, cands: [] };
  // 跳过 disabled / aria-disabled="true" / 尺寸过小(宽或高 < 10)——
  // 但**如实报出来**,别静默(否则下一次还是只看到一句「点不中」)。
  const usable = hit.filter((o) => !o.disabled && o.visible);
  const skipped = report.filter((o) => o.disabled || !o.visible);
  if (!usable.length) {
    return { ok: false, why: "all-disabled-or-tiny", exact, n: hit.length,
             skipped, cands: report };
  }
  // 优先「像按钮」的那个(native / class 带 button):同分取面积小的,
  // 避免点到把整排按钮包在里面的外层容器。
  const score = (o) => (o.native ? 4 : 0) + (/btn|button/i.test(o.cls) ? 3 : 0);
  usable.sort((a, b) => (score(b) - score(a)) || (a.w * a.h - b.w * b.h));
  const pick = usable[0];
  if (doClick) {
    try { pick.el.scrollIntoView({ block: "center" }); } catch (e) {}
    pick.el.click();                 // 原生 click:不经命中测试,遮挡拦不住
  }
  return { ok: true, clicked: !!doClick, text: pick.text, tag: pick.tag,
           disabled: pick.disabled, clsDisabled: pick.clsDisabled,
           cls: pick.cls.slice(0, 80), n: hit.length, exact, skipped, cands: report };
};
"""


async def _force_show_hover(page) -> bool:
    """注入一段**带 id 的** CSS,把 ``[class*="hover-show"]`` 强制显示。

    ★ 抖音的「选择封面 / 编辑封面」挂在 ``hover-show-*`` 上,默认 ``display:none``,
      靠 CSS ``:hover`` 才显示;在最小化窗口里 ``page.mouse.move()`` 不生效
      (computed display 恒为 none),合成 ``mouseover/mouseenter`` 也无效。
    ★ 必须能**撤掉**:这段样式会把「编辑封面」黑框盖在封面缩略图上,污染像素指纹。
      所以不用 ``add_style_tag``(拿不到可辨识句柄),改成自己建带 id 的 ``<style>``。
    """
    try:
        await page.evaluate(
            """(id) => {
              let s = document.getElementById(id);
              if (!s) {
                s = document.createElement('style');
                s.id = id;
                document.head.appendChild(s);
              }
              s.textContent = '[class*="hover-show"]{display:block!important;}';
            }""",
            _HOVER_STYLE_ID,
        )
        return True
    except Exception as exc:                       # noqa: BLE001
        _log(f"注入 hover-show 样式失败: {exc!r}")
        return False


async def _clear_hover_show(page) -> None:
    """撤掉 :func:`_force_show_hover` 注入的样式,让封面缩略图恢复「干净」像素。"""
    try:
        await page.evaluate(
            "(id) => { const s = document.getElementById(id); if (s) s.remove(); }",
            _HOVER_STYLE_ID,
        )
    except Exception:                              # noqa: BLE001
        pass


async def _safe_click(page, labels, wait_ms: int = 2500) -> str:
    """按文案点第一个可见命中,返回命中的 label(空串=都没找到)。"""
    for label in labels:
        for frame in page.frames:
            for sel in (f'text="{label}"', f"text={label}"):
                try:
                    loc = frame.locator(sel)
                    if await loc.count() == 0:
                        continue
                    node = loc.first
                    if not await node.is_visible():
                        continue
                    await node.scroll_into_view_if_needed(timeout=3000)
                    await node.click(timeout=4000)
                    await page.wait_for_timeout(wait_ms)
                    return label
                except Exception:                  # noqa: BLE001
                    continue
    return ""


async def _scroll_text_into_view(page, text: str) -> bool:
    """把指定文案滚进视野(返回是否命中)。"""
    for frame in page.frames:
        try:
            node = frame.locator(f'text="{text}"').first
            if await node.count():
                await node.scroll_into_view_if_needed(timeout=5000)
                await page.wait_for_timeout(1200)
                return True
        except Exception:                          # noqa: BLE001
            continue
    return False


async def _nudge_overlay_closed(page, rounds: int = 2) -> None:
    """试着把封面弹层收起来 —— **不动** ``<style id="chrc-hover-show">``。

    ★ 拆出来单独一个函数(而不是并进 :func:`_close_overlay`)有两个原因:
      1. :func:`_ensure_overlay_closed` 需要在**流程中途**反复试收弹层,而
         :func:`_close_overlay` 是「失败出口」(会清掉强制显示样式)。清样式这件事
         在失败出口做是对的,在中途反复做会把「选择封面」按钮重新变回 display:none。
      2. 仓库里 `tests/test_douyin_cover_adversarial.py::test_08` 用静态启发式守着
         「``_close_overlay()`` 的调用点后 3 行内必须有 return」这条约定 —— 它是
         「失败出口」语义的回归护栏。中途尝试收弹层走这个不带 return 的入口,语义才对得上。

    ★ 千万别用「点空白处」收浮层:抖音左侧是导航栏,左上角 ``(3, 3)`` 就是
      **返回首页的 logo**,一点就被带走了(已踩)。
    ★ 2026-09-21 事故(Task #62):抖音这个封面弹层**不吃 Escape**(实测 Escape×2
      之后弹层仍在),残留的透明遮罩会把随后「发布」按钮的点击吃掉 ⇒ 先按文案点
      明确的关闭入口,再退回 Escape。
    ★ 按文案点的那几个按钮**必须**用 :func:`_cover_modal_present` 先确认弹层在,
      否则会在普通编辑页上按文案乱点(本函数被多条失败路径共用,那些路径的页面
      **未必**是弹层);同时**不 break** —— 弹层上可能同时存在多个入口,能点中的
      那个才管用。``我知道了`` 放最后:它常属于无关的提示条(toast),点了只是顺带
      清掉一层干扰,不是真正的弹层关闭入口。
    """
    if await _cover_modal_present(page):
        for label in ("取消", "关闭", "我知道了"):
            try:
                await _safe_click(page, [label], wait_ms=700)
            except Exception:                          # noqa: BLE001
                pass
    for _ in range(rounds):
        try:
            await page.keyboard.press("Escape")
        except Exception:                          # noqa: BLE001
            pass
        try:
            await page.wait_for_timeout(800)
        except Exception:                          # noqa: BLE001
            pass


async def _close_overlay(page, rounds: int = 2) -> None:
    """兜底收起封面弹层 —— **撤掉注入的 hover-show 样式** + 试收弹层。

    ★ 本函数是所有失败路径的「恢复现场」出口:``_open_cover_editor`` 是在点按钮
      **之前**就注入强制显示样式的,而只有成功路径(第 9 步)才显式清理;失败路径
      若只按 Escape 就 ``return``,泄漏的样式会把 ``[class*="hover-show"]`` 全部
      强制显示,污染同页后续布局与像素比对(违反 :func:`_force_show_hover` docstring
      「必须能撤掉」的约定)。在**入口**处统一清理,5 条失败 return 路径一处收敛,
      不必四处撒调用。对「本就没注入过」的页面是无害 no-op。

    ★ 它同时是 :func:`set_douyin_cover` 的失败出口 —— 调用点后 3 行内必须 return
      (``tests/test_douyin_cover_adversarial.py::test_08`` 守着这条)。中途想收弹层
      请用 :func:`_nudge_overlay_closed`。
    """
    await _clear_hover_show(page)
    await _nudge_overlay_closed(page, rounds=rounds)


_COVER_MODAL_JS = r"""
(() => {
  const norm = (s) => (s || "").replace(/\s+/g, " ").trim();
  const txt = norm(document.body.innerText || "");
  return txt.includes("设置竖封面")
      && (txt.includes("上传封面") || txt.includes("竖封面预览"));
})();
"""


async def _cover_modal_present(page) -> bool:
    """页面上是否还留着封面编辑器弹层。

    ★ 判据用「设置竖封面」+「上传封面/竖封面预览」两条文案**同时**出现 ——
      封面已经设好的正常编辑页里「设置竖封面」也在,所以必须加第二条限定,
      否则会把正常态误判成弹层未收。

    ★ 2026-09-21 复核「会不会永远为真」:**不会**。同一张编辑页的**关闭态**取证
      ``data/debug/dy_cover_live_before-cover_20260920_172828.txt`` 里这三串文案
      一个都没有(关闭态只有 设置封面 / 选择封面 / 竖封面3:4 / 选择封面 / 横封面4:3 /
      Ai智能推荐封面…),而**打开态**取证 ``dy_publish_clickfail_20260921_140331.txt``
      里 设置竖封面=1、上传封面=1、竖封面预览=1(全部落在弹层的 DOM 尾段里)。
      所以 14:00 轮打的 ``点击兜底: 封面弹层已收起=False`` 是**真的没收起**
      (同刻截图里弹层确实开着),不是误报。

    ★ 故意**不**把判据收紧成「``dy-creator-content-modal-wrap`` 容器可见」:那会多引
      一个抖音内部类名依赖,一旦改版改名本判据就永远为假 —— 这道防线会**静默失效**
      (比误报更危险)。关闭态下该容器的可见性已随第 8/8b 步的诊断快照一起落盘,
      下一轮真实发布可直接核对。
    """
    try:
        return bool(await page.evaluate(_COVER_MODAL_JS))
    except Exception:                              # noqa: BLE001
        return False


async def _ensure_overlay_closed(page, rounds: int = 3) -> bool:
    """确认封面弹层真的收起了,没收起就再收一次。返回 True = 已收起。

    ★ 2026-09-21 事故(Task #62):点完「完成」**不等于**弹层消失。抖音的封面弹层
      不吃 Escape,残留的透明遮罩会把随后「发布」按钮的点击吃掉。必须在离开封面
      步骤之前**显式确认**它没了。
    """
    for _ in range(max(1, rounds)):
        if not await _cover_modal_present(page):
            return True
        await _nudge_overlay_closed(page, rounds=1)
        try:
            await page.wait_for_timeout(700)
        except Exception:                          # noqa: BLE001
            pass
    return not await _cover_modal_present(page)


async def close_cover_overlay(page, rounds: int = 2) -> bool:
    """【对外入口】确认封面弹层已收起。返回 True = 已收起(或本来就不在)。

    ★ 2026-09-21 事故(Task #62):抖音的封面弹层若残留,其透明遮罩会**吃掉**
      「发布」按钮的点击 —— 表现为 `btn.click()` 与文本选择器两路都失败,
      整条本来能发的作品被判失败。publish.py 的「发布点击第三层兜底」必须先
      调本函数把弹层收干净,再退到 JS 原生 ``el.click()``。
    """
    return await _ensure_overlay_closed(page, rounds=rounds)


async def _mark_upload_input(page) -> dict:
    """把封面弹层里**真正的投放区** ``input[type=file]`` 标上 ``data-bfc-upload="1"``。"""
    try:
        return await page.evaluate(_MARK_UPLOAD_JS) or {}
    except Exception as exc:                       # noqa: BLE001
        return {"err": repr(exc)[:160]}


async def _cover_signature(page, tag: str) -> dict:
    """封面缩略图区的**像素指纹**(用于判断上传到底有没有生效)。

    ★ 不能只看 ``img.src``:上传没生效时 src 也会变(换 CDN 变体),像素才作数。
    ★ 不能按 CDN URL 找图,也不能自己算 clip 再截整页(编辑页会把封面区滚出视口,
      坐标变负就一张都截不到); ``locator.screenshot()`` 会自动把元素滚进视野。
    """
    await _scroll_text_into_view(page, "竖封面3:4")
    await page.wait_for_timeout(900)
    try:
        mark = await page.evaluate(_MARK_THUMBS_JS) or {}
    except Exception as exc:                       # noqa: BLE001
        return {"ok": False, "why": f"标记封面缩略图失败: {exc!r}"}
    if mark.get("err"):
        return {"ok": False, "why": f"标记封面缩略图失败: {mark['err']}"}
    marked = mark.get("marked") or []
    if not marked:
        return {"ok": False,
                "why": f"没找到封面缩略图(锚点命中 {mark.get('anchors')} 个,但近邻都没 img)"}
    loc = page.locator('[data-bfc-thumb="1"]')
    count = await loc.count()
    shots: list[bytes] = []
    for index in range(count):
        try:
            shots.append(await loc.nth(index).screenshot(timeout=10000))
        except Exception as exc:                   # noqa: BLE001
            _log(f"封面缩略图 #{index} 截图跳过: {exc!r}")
    if not shots:
        return {"ok": False, "why": f"封面缩略图 {count} 个都截不到"}

    saved: list[str] = []
    try:
        _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        for index, shot in enumerate(shots):
            path = _DEBUG_DIR / f"dy_cover_{tag}_{stamp}_{index}.png"
            path.write_bytes(shot)
            saved.append(str(path))
    except Exception:                              # noqa: BLE001
        saved = []

    first = b"|".join(shots)
    # 稳定性自检:同一组元素立刻再截一遍,字节不同说明页面还在动/图片还没加载完
    second: list[bytes] = []
    for index in range(count):
        try:
            second.append(await loc.nth(index).screenshot(timeout=10000))
        except Exception:                          # noqa: BLE001
            continue
    return {
        "ok": True,
        "digest": hashlib.sha1(first).hexdigest()[:16],
        "stable": b"|".join(second) == first,
        "count": len(shots),
        "labels": [o.get("label") for o in marked],
        "srcs": [o.get("src") for o in marked],
        "pngs": saved,
    }


async def _dump_stuck(page, tag: str) -> str:
    """把「卡住」那一刻的整页截图 + URL/正文快照落盘,返回截图路径。

    ★ 2026-09-21 14:00 事故(Task #68):第 8/8b 步失败时**只留一句中文原因串**,
      现场(弹层里「完成」到底 disabled 还是文案不同)全丢了,下一轮发布无法自证
      —— 只能靠人肉去翻 ``dy_publish_clickfail_*`` 才看出弹层还开着。
    ★ 不能借用 ``publish.py`` 里的 ``_dump``(那会形成循环依赖,见模块 docstring),
      这里按同样的约定自己落一份;文件名前缀仍用 ``dy_cover_``,与 ``dy_publish_*``
      的真机取证区分开。
    ★ 只在**失败路径**调用 —— 成功路径零开销。
    """
    try:
        _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = _DEBUG_DIR / f"dy_cover_{tag}_{stamp}"
        png = str(base.with_suffix(".png"))
        try:
            await page.screenshot(path=png, full_page=True)
        except Exception:                          # noqa: BLE001
            png = ""
        try:
            txt = await page.inner_text("body")
        except Exception:                          # noqa: BLE001
            txt = ""
        base.with_suffix(".txt").write_text(
            f"url: {page.url}\n\n{txt[:4000]}", encoding="utf-8")
        _log(f"已存诊断快照 tag={tag} url={page.url} png={png}")
        return png
    except Exception as exc:                       # noqa: BLE001
        _log(f"存快照失败: {exc!r}")
        return ""


async def _js_click_finish(page) -> dict:
    """【第 2 层兜底】用 JS 原生 ``el.click()`` 点封面编辑器的「完成」。

    ★ 2026-09-21 14:00 事故(Task #68):第 1 层(Playwright 点击)没抛异常 —— 说明
      它**确实**点中了某个可见元素(否则会走 ``except`` 分支、第 8 步重试 10 次后
      返回「一直点不中」,根本到不了第 8b 步),可弹层 90s 后仍开着。
      JS 原生 ``el.click()`` 由元素自身派发事件、**不经过命中测试**,所以残留遮罩
      拦不住它(14:00 轮「发布」按钮就是靠 publish.py 里同一招发出去的)。
    ★ 找不到候选就如实报 ``ok=False`` 并附候选清单,**绝不**"随便挑一个按钮"。
    """
    try:
        return dict(await page.evaluate(_JS_FINISH_CANDS, True) or {})
    except Exception as exc:                       # noqa: BLE001
        return {"ok": False, "why": repr(exc)}


async def _finish_candidates(page) -> dict:
    """只枚举不点击:把页面上所有像「完成」的候选连同 disabled/尺寸/HTML 报回来(诊断用)。"""
    try:
        return dict(await page.evaluate(_JS_FINISH_CANDS, False) or {})
    except Exception as exc:                       # noqa: BLE001
        return {"ok": False, "why": repr(exc)}


# ★ 真机(2026-09-21 15:21)探测到的「完成」定位器:真机「完成」是一个
#   ``button.semi-button-primary``(106×32, disabled=False),其祖先
#   ``DIV.buttons-BoCvr4``(842×64, 文案含「取消完成」)。退化的第二选择器按
#   「按钮条里最后一个 primary 按钮」兜底 —— 同页可能同时有「设置横封面/竖封面」两处
#   「完成」,弹层底部的那个才是要点的。
_FINISH_BTN_SELECTORS = (
    'button.semi-button-primary:has-text("完成")',
    '[class*="buttons-"] button.semi-button-primary',
)


async def _mouse_click_finish(page) -> dict:
    """用**真鼠标事件**(move→down→up)点封面弹层底部的「完成」。

    ★ 为什么不用 ``locator.click()``:它自带 actionability 等待,2026-09-21 14:00
      那条路就是它「没抛异常却没生效」—— 残留遮罩把命中测试骗过去了,它等到了
      「可点」的判定、点下去却没到达真正的按钮。这里改成按 ``bounding_box`` 的
      中心坐标手工发真实鼠标事件,绕过命中测试的等待语义。
    ★ 失败一律 **fail-open**:返回 ``{"ok": False, "why": ...}``,**绝不**抛出让调用方
      中断发布 —— 封面是 best-effort。
    """
    for sel in _FINISH_BTN_SELECTORS:
        try:
            loc = page.locator(sel)
            n = await loc.count()
            if not n:
                continue
            # 取最后一个:同页可能同时有「设置横封面/竖封面」两处「完成」。
            btn = loc.last if hasattr(loc, "last") else loc.nth(n - 1)
            try:
                await btn.scroll_into_view_if_needed(timeout=5000)
            except Exception:                      # noqa: BLE001
                pass
            box = await btn.bounding_box()
            if not box:
                continue
            cx = box["x"] + box["width"] / 2
            cy = box["y"] + box["height"] / 2
            await page.mouse.move(cx, cy)
            await page.mouse.down()
            await page.mouse.up()
            return {"ok": True, "sel": sel, "bbox": {
                "x": round(box["x"]), "y": round(box["y"]),
                "w": round(box["width"]), "h": round(box["height"])}}
        except Exception as exc:                   # noqa: BLE001
            return {"ok": False, "why": f"{sel}: {exc!r}"}
    return {"ok": False, "why": "没找到可点的「完成」按钮"}


async def _secure_click_finish(page) -> str:
    """点封面编辑器的「完成」(第 1 层:Playwright 点击;第 2 层:JS 原生点击)。

    第 1 层保持原样:遍历文案 完成/确定/保存 × 所有 frame × 选择器
    ``text="完成"``(Playwright 精确匹配)/ ``text=完成``,只取当前**可见**的
    ``.first``,``scroll_into_view_if_needed`` 后 ``click(timeout=5000)``;
    任一步抛异常就换下一个候选,全部失败返回空串。

    ★ 2026-09-21 14:00 事故(Task #68):第 8b 步证明「第 1 层点了」≠「弹层收了」。
      所以第 1 层落空时补第 2 层 —— 由 :func:`_js_click_finish` 用 JS 原生
      ``el.click()`` 再点一次「完成」,并把候选/跳过原因记进日志。
    """
    for label in ("完成", "确定", "保存"):
        for frame in page.frames:
            try:
                loc = frame.locator(f'text="{label}"')
                if await loc.count() == 0:
                    continue
                node = loc.first
                if not await node.is_visible():
                    continue
                await node.scroll_into_view_if_needed(timeout=3000)
                await node.click(timeout=5000)
                await page.wait_for_timeout(4000)
                return label
            except Exception:                      # noqa: BLE001
                continue
    js = await _js_click_finish(page)
    if js.get("ok"):
        _log(f"第 1 层没点中「完成」,JS 原生点击 -> {js}")
        await page.wait_for_timeout(4000)
        return str(js.get("text") or "完成")
    _log(f"「完成」两层都没点中 -> {js}")
    return ""


async def _click_vertical_cover_button(page) -> str:
    """在「竖封面3:4」锚点容器内点「选择封面」/「编辑封面」(返回命中文案)。"""
    try:
        info = await page.evaluate(_MARK_VERTICAL_COVER_JS) or {}
    except Exception as exc:                       # noqa: BLE001
        _log(f"竖封面按钮标记 JS 抛异常: {exc!r}")
        return ""
    if not info.get("ok"):
        _log(f"竖封面按钮标记失败: {info.get('why') or info}")
        return ""
    try:
        loc = page.locator('[data-chrc-vcover="1"]')
        if await loc.count() == 0:
            return ""
        node = loc.first
        await node.scroll_into_view_if_needed(timeout=3000)
        try:
            await node.click(timeout=4000)
        except Exception:
            # 2026-09-26 新版编辑页布局(chain 里有 new-layout-*):封面区被挪到右栏,
            # 与「发文助手」浮卡重叠,Playwright 命中测试被浮卡拦截 → 点击超时。
            # 走 JS 原生 el.click() 兜底(同 _JS_CLICK_PUBLISH/_js_click_finish 判例:
            # 由元素自身派发事件、不经命中测试,遮挡拦不住)。
            js = await page.evaluate(
                """() => {
                     const el = document.querySelector('[data-chrc-vcover="1"]');
                     if (!el) return { ok: false, why: "marked-node-gone" };
                     el.click();
                     return { ok: true, cls: String(el.className || "").slice(0, 60) };
                   }""")
            if not js.get("ok"):
                _log(f"竖封面原生点击兜底失败: {js}")
                return ""
            _log(f"Playwright 点击被遮挡,已用 JS 原生点击兜底 -> {js}")
        await page.wait_for_timeout(3000)
        return info.get("text") or "选择封面"
    except Exception:                              # noqa: BLE001
        return ""


async def _open_cover_editor(page) -> str:
    """点开**竖封面**的封面编辑器,返回命中文案(空串=没打开)。

    ★ 「设置封面」只是区块标题 DIV,点它什么都不发生(已实测)。
    ★ 优先在「竖封面3:4」锚点容器内点「选择封面」;找不到再退到页面首个可见的
      「选择封面」/「编辑封面」。
    ★ 按钮挂在 ``hover-show-*`` 上默认 ``display:none`` → 先注入 CSS 强制显示。
    """
    await _scroll_text_into_view(page, "竖封面3:4")
    await _force_show_hover(page)
    await page.wait_for_timeout(1200)
    hit = await _click_vertical_cover_button(page)
    if hit:
        return hit
    return await _safe_click(page, ["选择封面", "编辑封面"], wait_ms=5000)


# ── 生效确认 / 换路重试(2026-09-21)────────────────────────────────────────
# 确认环节的节奏与轮数,**只影响确认**、不影响发布流程。与同日视频号
# ``channels/publish.py::_COVER_CONFIRM_ROUNDS`` 取同一口径(那边是发布前置条件,
# 这边是 best-effort,但「确认不能自己变成新失败点」的原则一致)。
_COVER_CONFIRM_ROUNDS = 3
_COVER_SETTLE_MS = 2500      # 投喂后等裁切/上传完成再复读
_COVER_RETRY_MS = 1500       # 换路两轮之间的间隔
_COVER_RETRY_BUDGET_MS = 90000   # 整条重试阶梯的时间上限(见 _confirm_cover)


def _cover_verdict(before: dict, after: dict) -> tuple[str, str]:
    """比对投喂前后的封面区指纹,返回 ``(verdict, detail)``。**纯函数,便于离线单测。**

    verdict 三态(与 ``channels/publish.py::_cover_verdict`` 同名同义):
      * ``"changed"``   —— 明确**已生效**(像素 digest 与投喂前基线不同)
      * ``"unchanged"`` —— 明确**没生效**(指纹前后逐字节一致)→ 才值得换路重试
      * ``"unknown"``   —— **判不准**(基线/复检任一读不到,如选择器漂移)→ fail-open

    ★ 判据只用**像素**:``img.src`` 在上传没生效时也会变(换 CDN 变体),拿它当
      「已生效」证据会**静默**放过假成功。源串只记进 ``detail`` 供人判,不参与判定。
    ★ 本函数是**纯函数**:不碰页面、不抛异常、不落盘 —— 三态谁都不敢保证时给
      ``unknown``,由调用方 fail-open(当作已生效继续发布)。
    """
    if not isinstance(after, dict) or not after.get("ok"):
        return "unknown", f"投喂后取不到封面预览({(after or {}).get('why') or '未读到缩略图'})"
    if not isinstance(before, dict) or not before.get("ok"):
        return "unknown", (f"投喂前没取到基线({(before or {}).get('why') or '未读到缩略图'})")
    b_digest = before.get("digest") or ""
    a_digest = after.get("digest") or ""
    if b_digest and a_digest:
        if b_digest != a_digest:
            return "changed", f"像素 {b_digest}→{a_digest}"
        # ★ 文案里「像素前后一致」必须**连着**出现:既有回归用例
        #   ``tests/douyin_cover_fakes.py`` 的 7a 按这个子串判「假成功」被如实报出来。
        return "unchanged", f"像素前后一致({a_digest}),封面其实没换(典型假成功)"
    return "unknown", "像素指纹没取到(只能看 src,不作为判据)"


async def _reopen_and_feed(page, cover_path: str, attempt: int) -> str:
    """【换路】重新点开封面编辑器 + 重新用 ``set_input_files`` 投喂。返回 "" = 投喂没报错。

    ★ 为什么要**重开编辑器**、而不是只把文件再塞一次:第一次失败的是「弹层里那一次
      交互」,只重发文件等于在同一个可能已经半死的弹层上再赌一次;重开编辑器能拿到
      一份**全新的 DOM**(含新的投放区 input)与新的上传请求。
    ★ ``finally`` 里统一收弹层 + 撤掉注入的 hover-show 样式:它会把「编辑封面」黑框
      盖在缩略图上污染像素读数,而且残留强制显示样式会扰动同页后续布局(发布页同在
      这一页)。**成功失败两条路都要撤。**
    ★ 全程 fail-open:任何一步判不了都**返回原因串**给调用方,由调用方按「判不准」
      处理;本函数不 raise、更不当成发布失败。收弹层走 :func:`_ensure_overlay_closed`
      (**不带 return**),不用 :func:`_close_overlay` —— 后者是「失败出口」语义,
      ``tests/test_douyin_cover_adversarial.py::test_08`` 静态守着它后面必须紧跟 return。
    """
    err = ""
    try:
        opened = await _open_cover_editor(page)
        if not opened:
            err = "换路重试没能重新打开封面编辑器(「选择封面/编辑封面」没点中)"
        else:
            mark = await _mark_upload_input(page)
            if not (mark or {}).get("selected"):
                err = ("换路重试没找到投放区 input(祖先文案没有命中「拖拽」);"
                       f"页面上共 {mark.get('total')} 个 file input")
            else:
                try:
                    await page.locator('input[data-bfc-upload="1"]').set_input_files(
                        str(cover_path), timeout=30000)
                except Exception as exc:           # noqa: BLE001
                    err = f"换路重试投喂封面文件失败(投放区 input): {exc!r}"
                else:
                    await page.wait_for_timeout(5000)
                    finished = ""
                    for _ in range(4):
                        finished = await _secure_click_finish(page)
                        if finished:
                            break
                        await page.wait_for_timeout(2500)
                    _log(f"换路重试第 {attempt} 轮:已重新投喂,「完成」={finished or '未点中'}")
    except Exception as exc:                       # noqa: BLE001
        err = f"换路重试第 {attempt} 轮抛异常(按判不准处理): {exc!r}"
    finally:
        await _ensure_overlay_closed(page, rounds=2)
        await _clear_hover_show(page)
    return err


async def _confirm_cover(page, cover_path: str, base: dict, after: dict,
                         rounds: int = _COVER_CONFIRM_ROUNDS,
                         strict: bool = False) -> str:
    """【生效确认 + 换路重试】封面到底挂上没有?答不出就 fail-open。

    返回 ``""`` = 已生效 / 判不准(都按已生效继续,**绝不阻断发布**);非空串 = 明确
    没生效的原因(调用方只记日志)。与 ``channels/publish.py::_confirm_cover`` 同口径。

    首查**复用第 9 步刚读到的 ``after``**:它本身就是「投喂 + 收弹层」之后封面预览区的
    实测状态(元素个数 / 缩略图 src / 像素 digest),直接采信不再重读(省 2 张元素截图)。
    只有首查判 ``unchanged`` 才换路重试,每轮重投喂后再**复读**一次。

    ★ 时间预算 :data:`_COVER_RETRY_BUDGET_MS`:封面是 best-effort,**绝不允许它把发布
      窗口顶掉**。每轮 ≈ 20~25s,2 个重试轮最多 ~50s;真机上超预算就停止重试、如实
      回报(离线桩测试里 ``wait_for_timeout`` 是瞬时的,预算不会生效,3 轮都会跑满)。
    """
    verdict, detail = _cover_verdict(base, after)
    if verdict == "changed":
        _log(f"封面已确认生效: {cover_path} ({detail})")
        return ""
    if verdict == "unknown":
        if strict:
            return f"封面预览无法确认: {detail}"
        _log(f"封面生效无法确认({detail}),按 fail-open 当已生效继续,不阻断发布")
        return ""
    last = f"封面未确认生效(第 1/{max(1, rounds)} 轮未生效,{detail})"
    _log(f"首查{last},开始换路重试(重开编辑器 + 重新投喂)")
    started = time.monotonic()
    for attempt in range(2, max(1, rounds) + 1):
        elapsed_ms = (time.monotonic() - started) * 1000
        if elapsed_ms >= _COVER_RETRY_BUDGET_MS:
            _log(f"换路重试时间预算用尽({elapsed_ms:.0f}ms/{_COVER_RETRY_BUDGET_MS}ms),"
                 f"停止重试(封面 best-effort,不拖发布窗口)")
            break
        await page.wait_for_timeout(_COVER_RETRY_MS)
        feed_note = await _reopen_and_feed(page, cover_path, attempt)
        if feed_note:
            last = f"封面未确认生效(第 {attempt}/{max(1, rounds)} 轮未能换路重投喂,{feed_note})"
            _log(f"{last}")
            continue
        await page.wait_for_timeout(_COVER_SETTLE_MS)
        try:
            probed = await _cover_signature(page, f"retry{attempt}")
        except Exception as exc:                   # noqa: BLE001
            if strict:
                return f"封面复检异常: {exc!r}"
            _log(f"换路重试第 {attempt} 轮复读封面像素抛异常({exc!r}),"
                 f"按 fail-open 当已生效继续")
            return ""
        verdict, detail = _cover_verdict(base, probed)
        if verdict == "changed":
            _log(f"封面已确认生效: {cover_path} ({detail},换路重试第 {attempt} 轮)")
            return ""
        if verdict == "unknown":
            if strict:
                return f"封面复检无法确认: {detail}"
            # ★ fail-open:复读也判不了 ⇒ 当作已生效继续发布(不再浪费轮次重试)。
            _log(f"封面生效无法确认({detail}),按 fail-open 当已生效继续,不阻断发布")
            return ""
        last = f"封面未确认生效(第 {attempt}/{max(1, rounds)} 轮未生效,{detail})"
        _log(f"{last},换路重试")
    return (f"封面未确认生效({max(1, rounds)}轮重试后仍未生效): {cover_path};"
            f" 最后判据: {last}")


async def _feed_cover_via_filechooser(page, path) -> bool:
    """新版内嵌封面选择器投喂:原生点上传入口 + ``expect_file_chooser`` 接文件。

    ★ 2026-09-26(#97 第三/四轮实测):编辑页灰度 new-layout 后,「选择封面」打开
      的是嵌在右侧预览框里的封面选择器;老弹层的投放区 input 喂了不生效(假成功)。
      file chooser 事件是 **page 级**(任意 frame 触发都收得到),所以上传入口的
      原生点击要**遍历所有 frame**;点击报告在等待期间就落日志,别等超时。
    返回 ``True`` = chooser 已接到并 ``set_files`` 完成。
    """
    # 先尽量点「竖封面」页签(候选瓦片分横/竖两页,必须在竖页签下投喂)
    for frame in page.frames:
        try:
            tab = await frame.evaluate(
                r"""() => {
                      const norm = (s) => (s || "")
                          .replace(/[\u200b-\u200d\ufeff]/g, "")
                          .replace(/\s+/g, " ").trim();
                      const tab = Array.from(
                          document.querySelectorAll("div,span,button,a,label"))
                        .find((el) => el.children.length <= 2
                              && norm(el.textContent) === "竖封面");
                      if (tab) { tab.click(); return norm(tab.textContent); }
                      return "";
                    }""")
            if tab:
                _log(f"已点「竖封面」页签({tab}, frame={frame.url[:50]})")
                break
        except Exception:                      # noqa: BLE001
            continue
    await page.wait_for_timeout(800)
    js_all = []
    try:
        async with page.expect_file_chooser(timeout=8000) as fc_info:
            for frame in page.frames:
                try:
                    js = await frame.evaluate(_PICKER_UPLOAD_CLICK_JS)
                    if js:
                        _log(f"上传入口点击报告(frame={frame.url[:50]}): {js}")
                        js_all.append(js)
                except Exception:              # noqa: BLE001
                    continue
            # 真鼠标层:文案元素的原生 el.click() 若挂在父级委托上可能被无视,
            # 换 move→down→up 真鼠标事件打可见候选的中心(与 _mouse_click_finish 同款)。
            try:
                spots = await page.evaluate(
                    r"""() => {
                          const norm = (s) => (s || "")
                              .replace(/[\u200b-\u200d\ufeff]/g, "")
                              .replace(/\s+/g, " ").trim();
                          const want = ["上传封面", "本地上传", "上传文件", "点击上传"];
                          const out = [];
                          for (const el of document.querySelectorAll(
                              "button, div, span, a, label")) {
                            if (el.children.length > 2) continue;
                            const t = norm(el.textContent);
                            if (!want.includes(t)) continue;
                            const r = el.getBoundingClientRect();
                            if (r.width < 20 || r.height < 12) continue;
                            out.push({ t, x: r.x + r.width / 2, y: r.y + r.height / 2 });
                          }
                          return out.slice(0, 3);
                        }""")
                for s in spots:
                    _log(f"真鼠标点击上传入口({s['t']}) @ ({s['x']:.0f},{s['y']:.0f})")
                    await page.mouse.move(s["x"], s["y"])
                    await page.mouse.down()
                    await page.mouse.up()
                    await page.wait_for_timeout(600)
            except Exception as exc:           # noqa: BLE001
                _log(f"真鼠标层异常: {exc!r}")
        fc = await fc_info.value
        await fc.set_files(str(path))
        return True
    except Exception as exc:                   # noqa: BLE001
        _log(f"filechooser 投喂未命中: {exc!r}; 点击报告汇总: {js_all}")
        return False


async def set_douyin_cover(page, cover_path: str, *, strict: bool = False) -> str:
    """best-effort 给抖音编辑器/发布页设置竖封面。

    返回 ``""`` = 成功或无需处理;非空字符串 = 失败原因(调用方只记日志,不阻断发布)。
    """
    if not cover_path:
        _log("未指定封面,跳过")
        return ""
    path = Path(cover_path)
    if not path.is_file():
        return f"封面文件不存在: {cover_path}"

    # 3. 滚到封面区(必须等视频上传/转码就绪后封面区才渲染,调用方已保证时序)
    scrolled = False
    for anchor in ("竖封面3:4", "选择封面", "设置封面"):
        if await _scroll_text_into_view(page, anchor):
            scrolled = True
            break
    if not scrolled:
        return "编辑页没找到封面区(竖封面3:4/选择封面/设置封面 均未命中)"

    # 发布正文里的最后一个话题仍持有输入焦点时，抖音的话题建议浮层会盖住
    # 封面缩略图。元素级 screenshot 此时截到的是浮层文字；投喂前后字节
    # 相同，会把已经上传的指定封面误判成「封面其实没换」。2026-09-29
    # 任务 #130 的 base/after 缩略图均是「# 火星计划」建议列表。
    try:
        await page.keyboard.press("Escape")
        await page.evaluate("() => document.activeElement?.blur()")
        await page.locator('text="设置封面"').first.click(timeout=3000)
        await page.wait_for_timeout(400)
    except Exception as exc:  # noqa: BLE001
        _log(f"关闭话题建议浮层未完全命中，继续封面基线检查: {exc!r}")

    # 4. 上传前的像素基线(此时还没注入 hover-show 样式,缩略图是「干净」的)
    base = await _cover_signature(page, "base")
    _log(f"封面基线: digest={base.get('digest') or base.get('why')} stable={base.get('stable')}")

    # 5. 点开**竖封面**的封面编辑器
    opened = await _open_cover_editor(page)
    if not opened:
        # 2026-09-26 补:这条路径此前只回一句中文原因、零现场(#97/#99/#101/#103
        # 连续 4 单同因失败却无任何快照可查)。失败出口必须留整页截图+正文+URL。
        try:
            diag = await page.evaluate(_OPEN_FAIL_DIAG_JS)
            _log(f"封面入口几何诊断: {diag}")
        except Exception as exc:                   # noqa: BLE001
            _log(f"封面入口几何诊断抛异常: {exc!r}")
        try:
            await _dump_stuck(page, "open-fail")
        except Exception:                          # noqa: BLE001
            pass
        await _close_overlay(page)
        return "没能打开竖封面封面编辑器(「选择封面/编辑封面」没点中)"
    _log(f"已打开封面编辑器({opened})")

    # 6. 封面选择器里投喂本地文件。
    # ★ 2026-09-26(#97 第三轮实测):编辑页灰度 new-layout 后,「选择封面」打开的是
    #   嵌在右侧预览框里的封面选择器(横封面/竖封面页签 + 候选瓦片 + 底部上传入口),
    #   不再是老弹层;老弹层的投放区 input 喂进去不生效(像素三轮不变,假成功)。
    #   所以**先走 filechooser 拦截**(原生点真实上传入口),点不出 chooser 才回退
    #   老路径(_safe_click「上传封面」+ 投放区 input 直喂)。
    fed = await _feed_cover_via_filechooser(page, path)
    if not fed:
        # 上传入口没点出来 → 把选择器结构全量落日志(每个 frame 扫一遍;
        # hit:false 也要落 —— ups 里有「上传封面」的祖先链,同样是指纹)
        for frame in page.frames:
            try:
                scan = await frame.evaluate(_PICKER_SCAN_JS)
            except Exception:                  # noqa: BLE001
                continue
            if scan:
                _log(f"封面选择器结构(frame={frame.url[:50]}): {scan}")
                if scan.get("hit"):
                    break
    if fed:
        await page.wait_for_timeout(5000)
        _log("封面文件已投喂(filechooser),等待裁切预览/上传完成")
    if not fed:
        # —— 老弹层路径(2026-09-21 实测的 UI)——
        # ★ 新版弹层的「上传封面」被挪到了底部缩略图条附近,按文案 `_safe_click`
        #   点不中,但投放区文案与那个 `input[type=file]` 本来就在 DOM 里 —— 隐藏
        #   input 用 `set_input_files` 照样能喂进去。
        if not await _safe_click(page, ["上传封面"], wait_ms=3000):
            _log("没点中「上传封面」入口,直接尝试定位投放区 input(隐藏 input 也能投喂)")
        await page.wait_for_timeout(1500)

        # 7. 用 JS 标出**投放区** input 再投喂(宁可不标,绝不退化"随便挑一个 input")
        mark = await _mark_upload_input(page)
        selected = (mark or {}).get("selected")
        _log(f"上传输入框定位: total={mark.get('total')} selected={selected} "
             f"relaxed={mark.get('relaxed')} err={mark.get('err')}")
        if not selected:
            await _close_overlay(page)
            if mark.get("err"):
                return f"定位上传输入框出错: {mark['err']}"
            return ("封面弹层里没找到投放区 input(祖先文案没有命中「拖拽」);"
                    f"页面上共 {mark.get('total')} 个 file input")
        try:
            await page.locator('input[data-bfc-upload="1"]').set_input_files(
                str(path), timeout=30000)
        except Exception as exc:                   # noqa: BLE001
            await _close_overlay(page)
            return f"投喂封面文件失败(投放区 input): {exc!r}"
        await page.wait_for_timeout(5000)
        _log("封面文件已投喂,等待裁切预览/上传完成")

    # 8. 等图片处理,点「完成」(最多 10 次 × 2500ms)
    finished = ""
    for _ in range(10):
        finished = await _secure_click_finish(page)
        if finished:
            break
        await page.wait_for_timeout(2500)
    if not finished:
        # ★ 2026-09-26 补:新版内嵌选择器可能**没有**「完成」按钮(选完即生效)。
        #   「完成」点不中时先复读像素 —— 封面已变化就当作已生效,别把成功的上传
        #   误判成失败(#97 第三轮就是被「完成判据」卡住的假失败)。
        try:
            probed = await _cover_signature(page, "finish-check")
            verdict, detail = _cover_verdict(base, probed)
        except Exception as exc:                   # noqa: BLE001
            verdict, detail = "unknown", f"复读抛异常({exc!r})"
        if verdict == "changed":
            _log(f"「完成」没点中,但封面像素已变化,视为已生效({detail})")
            finished = "auto-applied"
        else:
            _log(f"「完成」没点中且像素未变化(verdict={verdict}, {detail})")
    if not finished:
        # ★ Task #68 取证:走到这里说明「完成」两层都没点中 —— 最可能就是它当时
        #   disabled(14:00 截图 dy_publish_clickfail_20260921_140331.png 里它是灰底)。
        #   把候选元素的 disabled/class/rect/HTML 逐个记下来,下次真实发布一眼可判。
        cands = await _finish_candidates(page)
        _log(f"「完成」候选诊断: {cands}")
        await _dump_stuck(page, "cover-finish-noclick")
        await _close_overlay(page)
        return "封面文件已投喂,但「完成」一直点不中(可能还在处理图片)"

    # 8b. ★ 2026-09-21:点完「完成」≠ 弹层收起。必须显式确认,否则残留遮罩会吃掉
    #     后面「发布」的点击(Task #62 就是这么丢掉一条本来能发的作品的)。
    if not await _ensure_overlay_closed(page):
        # ★ Task #68 取证:弹层没收起 = 残留遮罩随后会吃掉「发布」的点击。除了整页截图,
        #   再把**所有**像「完成」的候选(status/尺寸/HTML)报出来 —— 单看截图分不清
        #   「点了没生效」还是「压根点的是别人」,有了这份清单下一轮就能定论。
        cands = await _finish_candidates(page)
        _log(f"弹层未收起,「完成」候选诊断: {cands}")
        # ★ 这里才是 14:00 事故(Task #68)的**真实失败路径**:第 1 层点击**没抛异常**
        #   (返回了「完成」)但弹层没收起,于是落到 8b。所以「重试点击」必须放在**这个
        #   分支**里 —— :func:`_secure_click_finish` 内部那层 JS 兜底救不了这条路,因为
        #   它只在第 1 层**全落空**时才跑,而这里是第 1 层「点到了」却没生效。
        #   这一段是纯重试阶梯:目标是把弹层收掉、让流程**继续到第 9 步**,不是半路放弃。
        closed = False
        for attempt in range(1, 4):
            # (i) ★ 2026-09-21 修正:**真鼠标点击**「完成」优先(第一招)。
            #     定位器取自 15:21 真机探测:真机「完成」= ``button.semi-button-primary``
            #     (106×32, disabled=False),祖先 ``DIV.buttons-BoCvr4``(842×64, 文案含
            #     「取消完成」)。走 :func:`_mouse_click_finish`(move→down→up 真鼠标事件)。
            #     **故意不用** ``locator.click()`` —— 它带 actionability 等待,14:00 那条路
            #     就是它「没抛异常却没生效」。
            hit = await _mouse_click_finish(page)
            _log(f"弹层重试第 {attempt} 轮:真鼠标点击「完成」 -> {hit}")
            await page.wait_for_timeout(1500)
            if not await _cover_modal_present(page):
                b = hit.get("bbox") or {}
                _log(f"弹层重试第 {attempt} 轮收起成功(真鼠标点击「完成」"
                     f"bbox={b.get('x')},{b.get('y')},{b.get('w')},{b.get('h')})")
                closed = True
                break
            # (ii) 再点一次「完成」:走 :func:`_js_click_finish`(JS 原生 ``el.click()``,
            #      不经命中测试,能突破残留遮罩)—— 作为真鼠标点击失败后的**第二招**保留。
            js = await _js_click_finish(page)
            _log(f"弹层重试第 {attempt} 轮:JS 原生点击「完成」 -> {js}")
            await page.wait_for_timeout(1500)
            if not await _cover_modal_present(page):
                _log(f"弹层重试第 {attempt} 轮收起成功(JS 原生点击 "
                     f"{js.get('text') or js.get('why') or '?'})")
                closed = True
                break
            # (iii) ★ 最后一招 —— :func:`_nudge_overlay_closed`(**不带 return**,别用
            #       :func:`_close_overlay` —— 后者是「失败出口」语义,`test_08` 静态守着它
            #       后面必须紧跟 return)。**注意它第一件事就是点「取消」= 放弃封面**
            #       (见 app/platforms/douyin/cover.py:_nudge_overlay_closed),其次「关闭」/
            #       「我知道了」。2026-09-21 Task #68「真发出去了但没带封面」的机制就是
            #       把它当「收弹层成功」:封面被丢、代码却报成功。所以这里**降到最后一招**,
            #       且命中时日志必须明确警告、**不许再说「收起成功」**;真丢没丢封面交由
            #       第 10 步生效确认兜底。
            #       判定「收起」仍用 :func:`_cover_modal_present`(单次廉价 evaluate)。
            await _nudge_overlay_closed(page, rounds=1)
            await page.wait_for_timeout(1500)
            if not await _cover_modal_present(page):
                _log("弹层由 _nudge_overlay_closed 收起(⚠ 此处点的是「取消」,"
                     "封面可能已被丢弃,交由第 10 步生效确认兜底)")
                closed = True
                break
        if not closed:
            # 三轮全败、真正放弃时才落盘一次(重试期间不落盘,免得刷屏)。
            await _dump_stuck(page, "cover-finish-stuck")
            await _close_overlay(page)             # 失败出口:撤掉注入的 hover-show 样式
            return "封面已投喂但「设置竖封面」弹层收不起来(残留遮罩会挡住发布按钮)"
    # ← 到这里说明弹层已收起(首查通过 或 重试成功),继续第 9 步像素比对。

    # 9. 撤掉 hover-show 样式 → 比对**像素**(最多重试 4 次,每次 3500ms)
    await _clear_hover_show(page)
    after = None
    for _attempt in range(4):
        await page.wait_for_timeout(3500)
        cand = await _cover_signature(page, "after")
        if not cand.get("ok"):
            after = cand
            continue
        after = cand
        if not base.get("ok") or cand["digest"] != base["digest"]:
            break
    _log(f"封面上传后: digest={after.get('digest') or after.get('why')} "
         f"stable={(after or {}).get('stable')} srcs={(after or {}).get('srcs')}")

    # 10. ★ 2026-09-21(Task #70):**生效确认 + 失败换路重试** —— 前 9 步只证明「流程走完了」,
    #     没有一步证明封面真挂上去了。三态判定走 :func:`_cover_verdict`:
    #     changed=已生效 / unchanged=明确没变(才换路重试 _COVER_CONFIRM_ROUNDS 轮) /
    #     unknown=判不准 ⇒ fail-open 当已生效继续。本步骤**只加日志与重试**:不新增
    #     raise、不提前中断发布 —— 封面是 best-effort,绝不能因此丢掉一条本来能发的作品。
    note = await _confirm_cover(page, cover_path, base, after, strict=strict)
    if not note:
        return ""
    # 明确没生效、且换路重试也没救回来:先留现场(截图 + 正文),再撤掉注入样式,最后回报原因。
    _log(f"警告: {note}")
    await _dump_stuck(page, "cover-not-confirmed")
    await _close_overlay(page)
    return note
