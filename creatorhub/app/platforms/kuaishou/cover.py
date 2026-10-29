"""快手**发布时**顺带设置封面(任务级 ``cover_path``,best-effort)。

设计决策
--------
1. **任务级封面**:每条发布任务自带 ``cover_path``,由 ``PublishTask.cover_path``
   一路传到发布器(与抖音 ``douyin/cover.py`` 完全对齐的语义)。
2. **best-effort**:快手不设封面就是取视频首帧,发布照常成功 —— 所以这里失败
   **绝不阻断发布**,只把原因串回给调用方记日志。
3. **失败必须显式确认弹层收起**:本函数跑在「点发布」**之前**,而快手封面弹层
   (``ant-modal``「封面截取」)若残留,它的透明遮罩会把随后的「发布」点击吃掉
   —— 抖音 2026-09-21 事故(Task #62)就是这么丢掉一条本来能发的作品的。

选择器来源(★ 未在发布页验证)
-----------------------------
快手发布后补封面链路已实测打通(见 ``scripts/backfill_cover.py::_apply_kuaishou``),
走的是**编辑页** ``/article/edit/video``:

* 点开大封面 ``[class*="cover-full-editor"]``(``opacity:0`` 的悬浮层)→ ``ant-modal``
  「封面截取」;
* 切页签 ``[class*="_header-title-item"]:has-text("上传封面")``;
* 投放区 ``input[type=file]``(祖先文案含「拖拽图片到此 / 点击上传」)→ 投喂;
* 应用封面点「确认」(退化「去编辑」);
* 像素指纹取 ``[class*="default-cover"] img``。

发布页 ``/article/publish/video`` 与编辑页同属快手的统一发布/编辑组件,发布页在
上传视频后大概率复用同一套封面组件。选择器先按编辑页搬过来,并用
``scripts/_probe_ks_cover.py`` 做只读探测复核(该脚本只 dump 静态 DOM,不上传、不发布)。
**在发布页真机验证之前,上面这套选择器视为「未在发布页验证」。**

对外只暴露 :func:`set_kuaishou_cover`。本模块**自带** logger,刻意不 import
``publish.py`` 的 ``_log``(会形成循环导入)。
"""
from __future__ import annotations

import hashlib
import io
from datetime import datetime
from pathlib import Path

from .onboarding import dismiss_known_tour

__all__ = ["set_kuaishou_cover"]

_DEBUG_DIR = Path("./data/debug")


def _log(msg: str) -> None:
    """本模块专用 logger(不依赖 publish.py,避免循环导入)。"""
    print(f"[ks-cover] {msg}", flush=True)


# ── 内联的 JS 片段(运行时**不能**依赖 scripts/,必须自带)──────────────────
#
# 1) 标出「封面截取 → 上传封面」页签里**投放区**的 input[type=file]。
#    见 scripts/_mark_ks_upload.js:快手发布页上还有别的图片输入框(视频封面的后续
#    编辑区),按「第一个 accept 含 image」投喂会喂错地方。判据用「祖先链文案含
#    『拖拽图片到此』或『点击上传』」。
_MARK_UPLOAD_JS = r"""
(() => {
  const norm = (s) => (s || "").replace(/\s+/g, " ").trim();
  const rect = (el) => {
    const r = el.getBoundingClientRect();
    return [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)];
  };
  document.querySelectorAll('[data-bfc-upload]').forEach(
    (el) => el.removeAttribute("data-bfc-upload"));
  const inputs = Array.from(document.querySelectorAll('input[type="file"]'));
  const scored = inputs.map((el, index) => {
    let parent = el.parentElement;
    let chain = "";
    for (let depth = 0; depth < 8 && parent; depth += 1, parent = parent.parentElement) {
      chain += " " + norm(parent.textContent);
    }
    const accept = el.accept || "";
    let score = 0;
    if (chain.includes("拖拽图片到此")) score += 10;
    if (chain.includes("点击上传")) score += 5;
    if (accept.includes("image")) score += 3;
    return {
      index, score, accept: accept.slice(0, 60),
      cls: String(el.className || "").slice(0, 50),
      rect: rect(el),
      chainHit: chain.includes("拖拽图片到此") || chain.includes("点击上传"),
    };
  });
  const qualified = scored.filter((o) => o.chainHit);
  qualified.sort((a, b) => b.score - a.score);
  if (qualified.length) {
    inputs[qualified[0].index].setAttribute("data-bfc-upload", "1");
  }
  return { total: inputs.length, selected: qualified.length ? qualified[0] : null, scored };
})();
"""

# 2) 判断封面弹层是否**还开着** —— 一个可见的大号对话框(ant-modal / role=dialog),
#    文案里含「封面/上传」。用它当「弹层收起」的判据:`ant-modal` 关闭后
#    尺寸会归零或 display 变 none,不会继续命中。
_MODAL_JS = r"""
(() => {
  const norm = (s) => (s || "").replace(/\s+/g, " ").trim();
  const sel = '.ant-modal, [class*="ant-modal"], [role="dialog"]';
  for (const el of document.querySelectorAll(sel)) {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    if (r.width < 200 || r.height < 150) continue;
    if (cs.display === "none" || cs.visibility === "hidden" || cs.opacity === "0") continue;
    const t = norm(el.textContent);
    if (t.includes("封面") || t.includes("上传")) return true;
  }
  return false;
})();
"""

# 封面缩略图选择器(取像素指纹用)。首选编辑页实测命中的 ``default-cover``,
# 其余为发布页可能的等价类名兜底。
_THUMB_SELECTORS = (
    '[class*="default-cover"] img',
    '[class*="cover-editor"] img',
    '[class*="cover"] img',
)


async def _safe_click(page, labels, wait_ms: int = 2000) -> str:
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


async def _cover_sig(page, tag: str) -> dict:
    """快手封面缩略图的**像素指纹**(判断投喂到底有没有生效)。

    ★ 不能只看 ``img.src``:上传没生效时 src 也会变(换 CDN 变体),像素才作数。
    """
    try:
        loc = None
        used = ""
        for sel in _THUMB_SELECTORS:
            try:
                cand = page.locator(sel)
                if await cand.count() == 0:
                    continue
                loc = cand
                used = sel
                break
            except Exception:                      # noqa: BLE001
                continue
        if loc is None:
            return {"ok": False,
                    "why": "没找到封面缩略图(default-cover/cover img 均未命中)"}
        node = loc.first
        try:
            source = await node.evaluate("""el => {
              const img = el.tagName === 'IMG' ? el : el.querySelector('img');
              if (img) return img.currentSrc || img.src || '';
              const bg = getComputedStyle(el).backgroundImage;
              const match = bg.match(/^url\\([\"']?(.*?)[\"']?\\)$/);
              return match ? match[1] : '';
            }""")
        except Exception:
            source = ""
        if source and source.startswith(("https://", "http://")):
            try:
                from PIL import Image
                response = await page.context.request.get(source, timeout=12000)
                if response.ok:
                    raw = await response.body()
                    with Image.open(io.BytesIO(raw)) as picture:
                        picture = picture.convert("RGB").resize((64, 64))
                        pixels = picture.tobytes()
                        out = io.BytesIO()
                        picture.save(out, format="PNG")
                        shot = out.getvalue()
                    method = "image_pixels"
                else:
                    shot = await node.screenshot(timeout=12000)
                    pixels = shot
                    method = "screenshot"
            except Exception:
                shot = await node.screenshot(timeout=12000)
                pixels = shot
                method = "screenshot"
        else:
            shot = await node.screenshot(timeout=12000)
            pixels = shot
            method = "screenshot"
    except Exception as exc:                       # noqa: BLE001
        return {"ok": False, "why": f"封面缩略图截图失败: {exc!r}"}
    png = ""
    try:
        _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = _DEBUG_DIR / f"ks_cover_{tag}_{stamp}.png"
        path.write_bytes(shot)
        png = str(path)
    except Exception:                              # noqa: BLE001
        png = ""
    return {"ok": True, "digest": hashlib.sha1(pixels).hexdigest()[:16],
            "sel": used, "png": png, "method": method}


async def _open_cover_modal(page) -> bool:
    """点开大封面(``[class*="cover-full-editor"]``,``opacity:0`` 的悬浮层)打开弹层。"""
    try:
        # The tour can appear while the preceding thumbnail baseline is read,
        # after the publisher's earlier cleanup. Guard the actual click seam.
        if await dismiss_known_tour(page) is False:
            _log("新手引导遮罩未确认关闭，停止点击封面入口")
            return False
        loc = page.locator('[class*="cover-full-editor"]')
        if await loc.count() == 0:
            return False
        await loc.first.click(timeout=15000)
        return True
    except Exception as exc:                       # noqa: BLE001
        _log(f"点开封面弹层失败: {exc!r}")
        return False


async def _mark_upload(page) -> dict:
    """在「上传封面」页签里标出投放区的 file input。"""
    try:
        return await page.evaluate(_MARK_UPLOAD_JS) or {}
    except Exception as exc:                       # noqa: BLE001
        return {"err": repr(exc)[:160]}


async def _modal_present(page) -> bool:
    """封面弹层是否还开着。"""
    try:
        return bool(await page.evaluate(_MODAL_JS))
    except Exception:                              # noqa: BLE001
        return False


async def _nudge_modal_closed(page, rounds: int = 1) -> None:
    """试着把封面弹层收起来(纯键盘兜底,不点任意祖先)。"""
    for _ in range(max(1, rounds)):
        try:
            await page.keyboard.press("Escape")
        except Exception:                          # noqa: BLE001
            pass
        try:
            await page.wait_for_timeout(600)
        except Exception:                          # noqa: BLE001
            pass


async def _ensure_modal_closed(page, rounds: int = 3) -> bool:
    """确认封面弹层真的收起了,没收起就再点「确认」+ 按 Escape,最多 ``rounds`` 轮。

    返回 True = 已收起。★ 跑在「点发布」之前,弹层必须收干净,否则残留遮罩会
    吃掉随后的「发布」点击。
    """
    try:
        for _ in range(max(1, rounds)):
            if not await _modal_present(page):
                return True
            await _safe_click(page, ["确认", "去编辑"], wait_ms=1200)
            await _nudge_modal_closed(page)
            try:
                await page.wait_for_timeout(1200)
            except Exception:                      # noqa: BLE001
                pass
        return not await _modal_present(page)
    except Exception:                              # noqa: BLE001
        return False


async def set_kuaishou_cover(page, cover_path: str) -> str:
    """best-effort 给快手发布页/编辑页设置封面。

    返回 ``""`` = 成功或无需处理;非空字符串 = 失败原因(调用方只记日志,不阻断发布)。
    **绝不 raise。**
    """
    if not cover_path:
        _log("未指定封面,跳过")
        return ""
    path = Path(cover_path)
    if not path.is_file():
        return f"封面文件不存在: {cover_path}"
    # On the current Kuaishou editor, this JPEG produced a white CDN cover
    # after the crop/save step.  The equivalent RGB PNG was preserved.
    upload_path = path
    if path.suffix.lower() in (".jpg", ".jpeg"):
        try:
            from PIL import Image
            upload_path = path.with_name(path.stem + ".ks-upload.png")
            with Image.open(path) as image:
                image.convert("RGB").save(upload_path, format="PNG", optimize=True)
        except Exception as exc:  # noqa: BLE001
            return f"转换快手封面 PNG 失败: {exc!r}"

    try:
        # 1. 上传前的封面像素基线(此时缩略图是「干净」像素)。
        base = await _cover_sig(page, "base")
        _log(f"封面基线: digest={base.get('digest') or base.get('why')} "
             f"sel={base.get('sel')}")

        # 2. 点开封面弹层。
        if not await _open_cover_modal(page):
            return ("没能打开快手封面弹层(点不中 [class*=cover-full-editor];"
                    "发布页可能没有封面区,或选择器已改版)")
        await page.wait_for_timeout(4000)

        # 3. 切到「上传封面」页签(点不中也继续 —— 投放区 input 在 DOM 里就能投喂)。
        if not await _safe_click(
                page, ["上传封面"], wait_ms=2500):
            _log("没点中「上传封面」页签,直接尝试定位投放区 input")
        await page.wait_for_timeout(2000)

        # 4. 标出**投放区** input(宁可不标,绝不退化「随便挑一个 input」)。
        mark = await _mark_upload(page)
        selected = (mark or {}).get("selected")
        _log(f"上传输入框定位: total={mark.get('total')} selected={selected} "
             f"err={mark.get('err')}")
        if not selected:
            await _ensure_modal_closed(page, 2)
            if mark.get("err"):
                return f"定位上传输入框时出错: {mark['err']}"
            return (f"封面弹层里没找到投放区 input(祖先文案未命中「拖拽图片到此/点击上传」);"
                    f"页面上共 {mark.get('total')} 个 file input")

        # 5. 投喂封面文件。
        try:
            await page.locator('input[data-bfc-upload="1"]').set_input_files(
                str(upload_path), timeout=30000)
        except Exception as exc:                   # noqa: BLE001
            await _ensure_modal_closed(page, 2)
            return f"投喂封面文件失败(投放区 input): {exc!r}"
        await page.wait_for_timeout(6000)
        _log("封面文件已投喂,等待裁切预览/上传完成")

        # The current uploader's primary action opens a second "封面编辑"
        # modal.  Saving only the first modal leaves the original thumbnail.
        applied = await _safe_click(page, ["去编辑"], wait_ms=3000)
        if not applied:
            applied = await _safe_click(page, ["确认"], wait_ms=3000)
        if not applied:
            await _ensure_modal_closed(page, 2)
            return "封面文件投喂了,但弹层里没点中「确认」/「去编辑」"
        _log(f"封面弹层已「{applied}」")
        if applied == "去编辑":
            finished = ""
            for _ in range(40):
                if await page.get_by_text("封面编辑", exact=True).count():
                    finished = await _safe_click(page, ["完成"], wait_ms=3000)
                    if finished:
                        break
                await page.wait_for_timeout(3000)
            if not finished:
                return "上传图片后进入封面编辑器,但没能点中「完成」"
            _log("封面编辑器已点「完成」")
            for _ in range(30):
                if await page.locator('.ant-modal:visible').count() == 0:
                    break
                await page.wait_for_timeout(3000)

        # 7. ★ 点「确认」≠ 弹层收起。必须显式确认(最多 3 轮),否则残留遮罩会
        #    吃掉随后「发布」的点击。
        if not await _ensure_modal_closed(page, 3):
            return "封面已投喂但快手封面弹层收不起来(残留遮罩会挡住发布按钮)"

        # 8. 比对**像素**(最多重试 4 次)。
        after = None
        for _attempt in range(4):
            await page.wait_for_timeout(3000)
            cand = await _cover_sig(page, "after")
            after = cand
            if cand.get("ok"):
                if not base.get("ok") or cand["digest"] != base["digest"]:
                    break
        _log(f"封面上传后: digest={after.get('digest') if after else None} / "
             f"{after.get('why') if after else 'None'}")

        if not base.get("ok"):
            return (f"拿不到上传前的封面像素基线({base.get('why')}),"
                    f"无法断言封面是否真的换掉;按未生效处理")
        if not after or not after.get("ok"):
            return f"拿不到上传后的封面像素({after.get('why') if after else 'None'});按未生效处理"
        if after.get("method") != base.get("method"):
            return "封面前后使用了不同的像素采集方式;无法可靠比较,按未生效处理"
        if after["digest"] == base["digest"]:
            return ("封面文件投喂成功,但**像素前后一致**,封面其实没换(典型假成功);"
                    "按未生效处理")
        _log(f"封面像素已确认变化: {base['digest']} → {after['digest']}")
        return ""
    except Exception as exc:                       # noqa: BLE001
        return f"设置快手封面异常: {exc!r}"
