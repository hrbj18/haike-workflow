"""快手 Web 抓取(浏览器自动化 + 拦截 GraphQL 响应),对标 douyin/fetcher.py。

快手 PC 站把数据都打在 POST https://www.kuaishou.com/graphql 上,前端拦截响应即可:
  - 打开 /profile/{userId}      -> visionProfile(资料) + visionProfilePhotoList(作品)
  - 打开 /short-video/{photoId} -> visionVideoDetail + visionCommentList(评论)
登录态写在该账号专属持久 profile 里(www 与 cp 同顶域 .kuaishou.com 共享 Cookie)。

⚠️ 全部解析走「多候选键兜底」。快手 GraphQL operationName / 字段随版本变,
   若拿不到数据,优先核对 _dig_* 里的候选键与下面的页面 URL/选择器。
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Dict, List, Optional, Set, Tuple

from .identity import Identity
from .manager import BrowserManager

GRAPHQL_API = "/graphql"
# 评论现走 REST v2(实测):/rest/v/photo/comment/list 返回 rootCommentsV2
COMMENT_API = "/rest/v/photo/comment/"
# 作品列表现走 REST(实测 [ks_videos] 只见 /rest/v/profile/feed,无 graphql)
PROFILE_FEED_API = "/rest/v/profile/feed"
PROFILE_URL = "https://www.kuaishou.com/profile/{uid}"
PHOTO_URL = "https://www.kuaishou.com/short-video/{pid}"


def _rf(d: dict, *keys, default=""):
    for k in keys:
        v = (d or {}).get(k)
        if v not in (None, "", [], {}):
            return v
    return default


def _dig_rest_feeds(data: dict) -> list:
    """从 /rest/v/profile/feed 响应里挖出作品数组(feeds / list / data.feeds 兜底)。"""
    if not isinstance(data, dict):
        return []
    for key in ("feeds", "list", "photos"):
        v = data.get(key)
        if isinstance(v, list):
            return v
    d = data.get("data") or {}
    if isinstance(d, dict):
        for key in ("feeds", "list", "photos"):
            v = d.get(key)
            if isinstance(v, list):
                return v
    return []


def _dig_feeds(data: dict) -> list:
    """从 GraphQL 响应里挖出作品 feeds 数组(profile / search / 推荐都兜底)。"""
    d = (data or {}).get("data") or {}
    for key in ("visionProfilePhotoList", "visionSearchPhoto", "visionProfilePhotoListV2",
                "feeds", "brilliantTypeData"):
        v = d.get(key)
        if isinstance(v, dict) and isinstance(v.get("feeds"), list):
            return v["feeds"]
        if isinstance(v, list):
            return v
    return []


def _dig_profile(data: dict) -> Optional[dict]:
    """从 visionProfile 响应里挖出 userProfile。"""
    d = (data or {}).get("data") or {}
    vp = d.get("visionProfile") or {}
    up = vp.get("userProfile") if isinstance(vp, dict) else None
    return up if isinstance(up, dict) else None


def _dig_comments(data: dict) -> list:
    """从评论响应里挖出评论数组。兼容两套:
      - REST v2:顶层 rootCommentsV2 / subCommentsV2(现行)
      - 旧 GraphQL:data.visionCommentList.rootComments(兜底)"""
    if not isinstance(data, dict):
        return []
    for key in ("rootCommentsV2", "subCommentsV2", "rootComments"):
        v = data.get(key)
        if isinstance(v, list):
            return v
    d = data.get("data") or {}
    for key in ("visionCommentList", "commentListQuery"):
        v = d.get(key)
        if isinstance(v, dict):
            # 2026 详情页 commentListQuery 已切到 rootCommentsV2；旧解析只看
            # rootComments，导致页面明明显示评论却返回空列表。
            rc = (v.get("rootCommentsV2") or v.get("rootComments")
                  or v.get("commentList") or v.get("comments"))
            if isinstance(rc, list):
                return rc
    return []


async def fetch_ks_videos(mgr: BrowserManager, identity: Identity, user_id: str,
                          known_ids: Set[str], max_scrolls: int = 12,
                          settle_ms: int = 1800, block_media: bool = True,
                          open_url: str = ""
                          ) -> Tuple[List[dict], Optional[dict], str]:
    """打开创作者主页并下滑,拦截 GraphQL 收集作品 feeds。
    返回 (新作品 feed 列表, 作者 userProfile dict, error)。
    open_url 非空时直接打开它(如站内「我」入口解析出的自己主页链接)。"""
    collected: Dict[str, dict] = {}
    author: Optional[dict] = None
    error = ""
    api_seen: list = []          # 诊断:看到的 GraphQL operation + 其它响应路径
    feed_sample: list = []       # 标定:REST feed 首个作品项样本(字段核对用)
    page = await mgr.new_page(identity, block_media)

    async def on_response(resp):
        nonlocal author
        # 快手作品现走 REST /rest/v/profile/feed(实测项已含嵌套 photo,同 graphql 形状);
        # 直接透传给下游 _norm_ks_work(读 feed.photo),老账号仍走 graphql,两路都收
        if PROFILE_FEED_API in resp.url:
            try:
                data = await resp.json()
            except Exception:
                return
            items = _dig_rest_feeds(data)
            for it in items:
                photo = it.get("photo") if isinstance(it, dict) else None
                if not isinstance(photo, dict):
                    continue
                pid = str(_rf(photo, "id", "photoId", "photo_id", default=""))
                if not pid:
                    continue
                collected[pid] = it       # 整项带 photo,交 _norm_ks_work 统一归一
                if not feed_sample:
                    feed_sample.append("photo=" + str(photo)[:1100])   # 核对 photo 字段名
                if author is None and it.get("author"):
                    author = {"profile": it["author"]}
            return
        if GRAPHQL_API in resp.url:
            # GraphQL 都打到 /graphql,operationName 在请求体里 —— 取出来看到底发了哪些查询
            op = ""
            try:
                pd = resp.request.post_data or ""
                m = re.search(r'"operationName"\s*:\s*"([^"]+)"', pd)
                op = m.group(1) if m else ""
            except Exception:
                pass
            if len(api_seen) < 40:
                api_seen.append(f"{resp.status} gql:{op or '?'}")
        elif "kuaishou.com" in resp.url and resp.request.resource_type in ("xhr", "fetch"):
            if len(api_seen) < 40:
                p = resp.url.split("?")[0].split("kuaishou.com")[-1]
                api_seen.append(f"{resp.status} {p}")
        if GRAPHQL_API not in resp.url:
            return
        try:
            data = await resp.json()
        except Exception:
            return
        for feed in _dig_feeds(data):
            photo = (feed.get("photo") or {}) if isinstance(feed, dict) else {}
            pid = str(photo.get("id") or feed.get("id") or "")
            if pid:
                collected[pid] = feed
                if author is None and feed.get("author"):
                    author = {"profile": feed["author"]}
        up = _dig_profile(data)
        if up and author is None:
            author = up

    page.on("response", on_response)
    final_url = ""
    try:
        await page.goto(open_url or PROFILE_URL.format(uid=user_id),
                        wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(settle_ms)
        stagnant = 0
        for _ in range(max_scrolls):
            if known_ids & set(collected.keys()):     # 翻到旧内容了
                break
            before = len(collected)
            await page.mouse.wheel(0, 4000)
            await page.wait_for_timeout(settle_ms)
            if len(collected) == before:
                stagnant += 1
                if stagnant >= 2:
                    break
            else:
                stagnant = 0
        final_url = page.url
        if not collected:
            if "passport" in final_url or "/login" in final_url:
                error = "logged_out:登录态失效,请重新登录"
            else:
                error = "未拦截到作品数据(可能未登录/被风控/该用户无公开作品)"
    except Exception as e:
        error = f"打开主页失败: {e!r}"
    finally:
        try:
            await page.close()
        except Exception:
            pass

    if not collected:
        print(f"[ks_videos] user_id={user_id!r} open_url={open_url!r} "
              f"final_url={final_url} api_seen({len(api_seen)})={api_seen[:40]}")
    # REST feed 命中但可能字段没对齐:打样本便于核对 _rest_item_to_feed
    if feed_sample:
        print(f"[ks_videos] feed_sample={feed_sample[0]}")

    new_items = [feed for pid, feed in collected.items() if pid not in known_ids]
    return new_items, author, error


async def fetch_ks_comments(mgr: BrowserManager, identity: Identity, photo_id: str,
                            known_cids: Set[str], max_scrolls: int = 6,
                            settle_ms: int = 1600, block_media: bool = True
                            ) -> Tuple[List[dict], str]:
    """打开作品详情页,滚动评论区翻页,拦截评论 GraphQL 收集评论原始 JSON。
    返回 (新评论原始列表, error)。"""
    collected: Dict[str, dict] = {}
    error = ""
    page = await mgr.new_page(identity, block_media)

    async def on_response(resp):
        if COMMENT_API not in resp.url and GRAPHQL_API not in resp.url:
            return
        try:
            data = await resp.json()
        except Exception:
            return
        for c in _dig_comments(data):
            cid = str((c or {}).get("comment_id") or (c or {}).get("commentId")
                      or (c or {}).get("id") or "")
            if cid:
                collected[cid] = c

    page.on("response", on_response)
    final_url = ""
    try:
        await page.goto(PHOTO_URL.format(pid=photo_id),
                        wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(settle_ms)
        stagnant = 0
        for _ in range(max_scrolls):
            before = len(collected)
            try:
                # 新版详情页评论区是固定面板，滚 window 不会翻页；同时滚动所有
                # 真正可滚容器，旧版页面则继续由 window.scrollTo 兜底。
                await page.evaluate("""() => {
                  window.scrollTo(0, document.body.scrollHeight);
                  for (const el of document.querySelectorAll('*')) {
                    const style = getComputedStyle(el);
                    if ((style.overflowY === 'auto' || style.overflowY === 'scroll')
                        && el.scrollHeight > el.clientHeight + 20) {
                      el.scrollTop = el.scrollHeight;
                    }
                  }
                }""")
            except Exception:
                pass
            await page.wait_for_timeout(settle_ms)
            if len(collected) == before:
                stagnant += 1
                if stagnant >= 2:
                    break
            else:
                stagnant = 0
        final_url = page.url
    except Exception as e:
        error = f"打开作品页失败: {e!r}"
    finally:
        try:
            await page.close()
        except Exception:
            pass

    if not collected and not error:
        if "passport" in final_url or "/login" in final_url:
            error = "logged_out:登录态失效,请重新登录"
        else:
            error = "未拦截到评论(评论区未加载或作品暂无评论)"
    new = [c for cid, c in collected.items() if cid not in known_cids]
    return new, error


_SELF_LINK_RE = re.compile(r"/profile/([0-9a-zA-Z_\-]+)")

# 快手 visionProfile 查询(实测标定,字段与 _dig_profile/parse_self_user 对齐)
_VISION_PROFILE_QUERY = (
    "query visionProfile($userId: String) {\n"
    "  visionProfile(userId: $userId) {\n"
    "    result\n"
    "    hostName\n"
    "    userProfile {\n"
    "      ownerCount { fan photo follow photo_public __typename }\n"
    "      profile { gender user_name user_id headurl user_text __typename }\n"
    "      isFollowing\n"
    "      __typename\n"
    "    }\n"
    "    __typename\n"
    "  }\n"
    "}\n"
)

# 在已登录页面里直接 POST graphql(同源带 Cookie,快手 graphql 无需签名)。
# 传 {op, query, variables},返回解析后的 JSON。
_KS_GQL_JS = """
async (v) => {
  try {
    const r = await fetch("https://www.kuaishou.com/graphql", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({
        operationName: v.op,
        variables: v.variables,
        query: v.query,
      }),
    });
    return await r.json();
  } catch (e) { return { __err: String(e) }; }
}
"""

# 登录后取「本人」资料的 REST 接口(实测 hit:含本人 userId)。先 GET,失败再 POST。
_KS_REST_PROFILE_JS = """
async () => {
  const url = "https://www.kuaishou.com/rest/v/profile/get";
  for (const m of ["GET", "POST"]) {
    try {
      const opt = { method: m, credentials: "include" };
      if (m === "POST") { opt.headers = {"Content-Type":"application/json"}; opt.body = "{}"; }
      const r = await fetch(url, opt);
      const j = await r.json();
      if (j && (j.result === 1 || j.userProfile || j.profile || j.user || j.data)) {
        j.__method = m; return j;
      }
      j.__method = m; j.__nohit = true; return j;
    } catch (e) { /* try next method */ }
  }
  return { __err: "profile/get fetch failed" };
}
"""


def _extract_rest_profile(data: dict):
    """从 /rest/v/profile/get 响应里抽出 userProfile 结构(喂给 parse_self_user)。
    快手该接口字段未知,这里多形状兜底;并把扁平计数归并进 ownerCount。"""
    if not isinstance(data, dict):
        return None, []
    # 2026 /rest/v/profile/get 当前直接返回扁平字段：
    # {eid,userName,userId,userDefineId,userHead,fans,follows,...}。
    # eid 才是 /profile/{id} 可用的公开 id；数字 userId 不能直开主页。
    if data.get("result") in (1, "1") and (
            data.get("userName") or data.get("user_name")):
        public_id = (data.get("eid") or data.get("encryptedUserId")
                     or data.get("user_id") or "")
        display_id = (data.get("userDefineId") or data.get("kwaiId")
                      or data.get("userId") or "")
        profile = {
            "user_id": str(public_id or ""),
            "user_name": data.get("userName") or data.get("user_name") or "",
            "kwaiId": str(display_id or ""),
            "eid": str(public_id or ""),
            "gender": data.get("sex") or data.get("gender") or "",
            "headurl": (data.get("userHead") or data.get("headurl")
                        or data.get("headUrl") or ""),
        }
        counts = {
            "fan": data.get("fans", data.get("fan", 0)),
            "follow": data.get("follows", data.get("follow", 0)),
            "like": data.get("like", data.get("likes", 0)),
            "photo_public": data.get(
                "photo_public", data.get("photoCount", data.get("photo", 0))),
        }
        return {"profile": profile, "ownerCount": counts}, list(data.keys())
    # 1) 已是 graphql 形状
    up = data.get("userProfile")
    if isinstance(up, dict) and up.get("profile"):
        return up, list(up.keys())
    # 2) 找像 profile 的容器
    NAME_KEYS = ("user_name", "userName", "name", "nickName", "nickname")
    for key in ("profile", "user", "userInfo", "data", "owner"):
        c = data.get(key)
        if isinstance(c, dict) and any(k in c for k in NAME_KEYS):
            oc = (c.get("ownerCount") or data.get("ownerCount")
                  or data.get("counts") or {})
            # 扁平计数兜底
            flat = {k: c.get(k) or data.get(k) for k in
                    ("fan", "photo", "photo_public", "follow", "fanCount",
                     "photoCount", "follower", "fans", "follows")}
            merged = {**{k: v for k, v in flat.items() if v is not None}, **oc}
            return {"profile": c, "ownerCount": merged}, list(c.keys())
    # 3) 顶层就是扁平 profile
    if any(k in data for k in NAME_KEYS):
        return ({"profile": data, "ownerCount": data.get("ownerCount") or {}},
                list(data.keys()))
    return None, list(data.keys())


def _harvest_self(node, uid: str, out: list, depth: int = 0):
    """在任意 JSON 里找"含本人数字 userId 的那个对象",抽出 昵称/头像/真实 3x user_id。
    依据:uid(cookie 里的数字 userId)确凿是本人,谁的字段里带它,谁就是自己。"""
    if depth > 8 or out or not uid:
        return
    if isinstance(node, dict):
        # 本对象的标量值里是否出现本人 uid
        hit = any(str(v) == uid for v in node.values()
                  if isinstance(v, (str, int)))
        if hit:
            name = (node.get("user_name") or node.get("userName") or node.get("name")
                    or node.get("nickName") or node.get("nickname") or "")
            head = (node.get("headurl") or node.get("headerUrl") or node.get("avatar")
                    or node.get("headUrl") or "")
            if isinstance(head, list):
                head = (head[0].get("url") if head and isinstance(head[0], dict)
                        else (head[0] if head else "")) or ""
            u3 = (node.get("eid") or node.get("encryptedUserId") or "")
            uid_field = node.get("user_id") or node.get("userId") or node.get("id") or ""
            # user_id 形如 3x... 才是 web profile id;纯数字则不是
            if isinstance(uid_field, str) and uid_field.startswith("3x"):
                u3 = u3 or uid_field
            if name or head or u3:
                out.append({"profile": {"user_name": name, "headurl": head,
                                        "user_id": u3}})
                return
        for v in node.values():
            _harvest_self(v, uid, out, depth + 1)
    elif isinstance(node, list):
        for v in node:
            _harvest_self(v, uid, out, depth + 1)


async def _ks_login_entry_visible(page) -> Optional[bool]:
    """快手首页的登录入口当前是否可见(None=探测本身失败)。

    原生 SSR 骨架在 JS hydrate 完成前**也带着** ``.sidebar-login-button``,瞬时
    采样会把「页面还没初始化完」读成「未登录」。所以这里连续两轮确认,中间留
    一次机会让前端 SDK 读完本地登录态并把入口摘掉。返回 None 表示两轮都没
    给出结论,调用方必须按「证据不足」处理,不能当成 True。
    """
    for attempt in range(2):
        visible: Optional[bool] = None
        try:
            visible = await page.locator(
                '[role="button"].sidebar-login-button').first.is_visible(
                    timeout=1200)
        except Exception:
            try:
                visible = await page.get_by_text(
                    "登录", exact=True).first.is_visible(timeout=1200)
            except Exception:
                visible = None
        if visible is not True:
            return visible
        if attempt == 0:
            try:
                await page.wait_for_timeout(1500)
            except Exception:
                break
    return True


# ── 创作者中心(cp.kuaishou.com)判活通道 ──
# 快手的 web 首页会话(kuaishou.server.webday7_st,7 天)与创作者中心会话
# (kuaishou.web.cp.api_st,约 1 个月)是**两条独立的登录链**,而业务发布只走 cp。
_KS_CP_PUBLISH_URL = "https://cp.kuaishou.com/article/publish/video"
_KS_CP_HOME_URL = "https://cp.kuaishou.com/"
# 页面自然加载时会命中这两个之一;裸 fetch 会被拒(result=500002「请稍后重试」),
# 因为该接口要求前端签名,所以只能拦响应、不能自己发请求。
_KS_CP_INFO_MARKERS = ("/rest/cp/creator/pc/home/infoV2",
                       "/rest/cp/creator/pc/home/info")
# cp 已登录时发布页正文里才有的标志(实测已登录:「1 檬檬和雅雅 发布作品 首页
# 内容管理 互动管理 数据中心 成长中心…」)。**不要**放「上传视频」——未登录时
# cp 会落到营销页,正文里同样有「上传视频 电脑端上传60帧的…」,会误命中。
_KS_CP_LOGGED_IN_MARKERS = ("发布作品", "内容管理", "数据中心", "成长中心",
                            "互动管理")
_KS_CP_LOGGED_OUT_MARKER = "立即登录"
_KS_CP_LOGIN_URL_MARKERS = ("passport", "/login", "login.html")

_KS_CP_AVATAR_JS = """
(uid) => {
  const s = new Set();
  document.querySelectorAll("img").forEach(i => {
    const src = i.currentSrc || i.src || "";
    if (src && (src.includes("kwimgs") || src.includes("wsukwai"))) s.add(src);
  });
  const arr = Array.from(s);
  if (uid) {
    const hit = arr.find(x => x.includes(uid));
    if (hit) return hit;
  }
  return "";
}
"""


async def _ks_cp_self_profile(page) -> Tuple[dict, str]:
    """用创作者中心(cp.kuaishou.com)会话取本人资料。

    为什么必须判这一路:业务发布只走 cp,而 cp 会话比 web 首页会话长寿得多。
    2026-09-17 离线实证(scripts/_ks_scope_probe_offline.py):同一套 DB cookie
    下 web 首页显示未登录、cp 发布页却是「1 檬檬和雅雅 发布作品 首页 内容管理…」,
    账号完全可发布。旧探针只查首页 ⇒ 把可正常发布的账号判成 logged_out
    ⇒ status=invalid ⇒ 发布/评论全被挡 —— 这才是「快手账号总是掉登录」的真正机制。

    返回 (userProfile, err):
      - err == ""           成功,userProfile 形状与 web 路径一致
      - err == "logged_out" cp 侧**明确**未登录(看到「立即登录」且无任何已登录标志)
      - err == "unconfirmed" 拿不到结论(网络/风控),调用方**不得**据此判死
    """
    captured: dict = {}
    grabbed = {"done": False}

    async def on_resp(resp):
        if grabbed["done"]:
            return
        url = resp.url.split("?")[0]
        if not any(m in url for m in _KS_CP_INFO_MARKERS):
            return
        try:
            payload = await resp.json()
        except Exception:
            return
        data = (payload or {}).get("data")
        if isinstance(data, dict) and (data.get("userName") or data.get("user_name")):
            captured.update(data)
            grabbed["done"] = True

    page.on("response", on_resp)
    final_url = ""
    for url, wait_ms in ((_KS_CP_PUBLISH_URL, 9000), (_KS_CP_HOME_URL, 9000)):
        if captured:
            break
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(wait_ms)
            final_url = page.url or ""
        except Exception:
            continue

    try:
        body = (await page.inner_text("body"))[:800]
    except Exception:
        body = ""

    if not captured:
        # 「未登录」必须两条独立证据同时成立:落到登录域(或页面出现「立即登录」)
        # **且**找不到任何已登录标志。只有一条时不判死,交给上游按「未定案」处理。
        on_login_url = any(m in final_url for m in _KS_CP_LOGIN_URL_MARKERS)
        says_login = _KS_CP_LOGGED_OUT_MARKER in body
        logged_in_hint = any(m in body for m in _KS_CP_LOGGED_IN_MARKERS)
        if not logged_in_hint and (on_login_url or says_login):
            return {}, "logged_out"
        return {}, "unconfirmed"

    uid_digits = str(captured.get("userId") or "")
    try:
        avatar = await page.evaluate(_KS_CP_AVATAR_JS, uid_digits)
    except Exception:
        avatar = ""
    profile = {
        "user_name": str(captured.get("userName")
                         or captured.get("user_name") or ""),
        "headurl": avatar or "",
        # 刻意**不带** userId/eid:快手的 sec_uid 需要 3x 形式,cp 只给数字 uid,
        # 带上去会把库里正确的 3x sec_uid 覆盖成纯数字。
    }
    kwai_id = captured.get("userKwaiId") or captured.get("kwaiId")
    if kwai_id:
        profile["kwaiId"] = str(kwai_id)
    out = {
        "profile": profile,
        "ownerCount": {
            "fan": captured.get("fansCnt", 0),
            "follow": captured.get("followCnt", 0),
            "like": captured.get("likeCnt", 0),
        },
        # 标记数据来源:cp 兜底拿不到作品数/性别,调用方对缺失字段保留旧值,
        # 不要用 0 覆盖(web 路径则照旧用绝对值,见 main.py 的 kuaishou 分支)。
        "_source": "ks_creator",
    }
    return out, ""


async def fetch_ks_self_profile(mgr: BrowserManager, identity: Identity,
                                timeout_ms: int = 15000, block_media: bool = False
                                ) -> Tuple[dict, str]:
    """拿登录账号真实资料。难点:数字 userId 不被 visionProfile 接受,/profile 通配会 404,
    首页 DOM 链接多是推荐位(会抓成别人)。可靠做法:登录 cookie 里的数字 userId 确凿是本人,
    拦截首页所有响应,找出"正文里出现该 userId"的那个响应,从中抽出本人昵称/头像/真实 3x id,
    再用 3x id 调 visionProfile 拿完整粉丝/作品数。
    返回 (userProfile dict, error)。error == "logged_out" 表示登录态失效。"""
    result: dict = {}
    error = ""
    page = await mgr.new_page(identity, block_media)
    logged_out = False
    has_login_btn = None
    # 创作者中心(cp)侧的判活结论:True=已登录 / False=明确未登录 / None=未定案
    creator_verdict: Optional[bool] = None
    attempts: List[str] = []
    profile_seen = asyncio.Event()

    # 先取 cookie(在导航前就绪,这样响应监听里能用 uid 匹配)
    uid_cookie = ""
    has_pass_token = False
    try:
        cks0 = await page.context.cookies()
        names0 = {c["name"] for c in cks0}
        uid_cookie = next((c.get("value", "") for c in cks0 if c["name"] == "userId"), "")
        has_pass_token = "passToken" in names0
    except Exception:
        names0 = set()
    # 本地登录凭证,与下面的页面证据相互独立。两者冲突时以「不定案」收场:
    # 判错的代价是账号被冻结到人工介入,漏判只是多探一次。
    has_credential = bool(has_pass_token or uid_cookie)
    if not has_credential:
        logged_out = True

    hits: list = []          # 含本人 uid 的响应里抽出的 profile 候选
    hit_urls: list = []      # 命中响应的 URL(诊断用)

    async def on_response(resp):
        nonlocal result
        rt = resp.request.resource_type
        if rt not in ("xhr", "fetch", "document"):
            return
        # 首屏自己的 profile/get 请求由快手页面签过名；直接复用这个响应。
        # 在 page.evaluate 里另发同 URL 会被 result=50「签名验证失败」拒绝。
        if "/rest/v/profile/get" in resp.url:
            try:
                payload = await resp.json()
            except Exception:
                payload = None
            up, keys = _extract_rest_profile(payload or {})
            attempts.append(f"captured_rest:top_keys={keys[:14]}")
            if up and up.get("profile"):
                result = up
                profile_seen.set()
        if not uid_cookie or len(hits) >= 3:
            return
        try:
            txt = await resp.text()
        except Exception:
            return
        if uid_cookie not in txt:
            return
        hit_urls.append(resp.url.split("?")[0])
        try:
            _harvest_self(json.loads(txt), uid_cookie, hits)
        except Exception:
            pass

    page.on("response", on_response)

    async def _vp(uid: str):
        try:
            data = await page.evaluate(_KS_GQL_JS, {
                "op": "visionProfile", "query": _VISION_PROFILE_QUERY,
                "variables": {"userId": str(uid)}})
        except Exception as e:
            attempts.append(f"vp({uid}):eval_err({e!r})")
            return None
        up = _dig_profile(data)
        uname = ((up or {}).get("profile") or {}).get("user_name") or ""
        attempts.append(f"vp({uid}):name={uname or '-'}"
                        + (f",errors={data.get('errors')}" if (data or {}).get("errors") else ""))
        return up if (up and up.get("profile")) else None

    try:
        await page.goto("https://www.kuaishou.com/new-reco",
                        wait_until="domcontentloaded",
                        timeout=30000)
        try:
            await asyncio.wait_for(profile_seen.wait(), timeout=4.0)
        except asyncio.TimeoutError:
            await page.wait_for_timeout(500)
        has_login_btn = await _ks_login_entry_visible(page)

        # ① 主路径:使用页面首屏已经签名的 /rest/v/profile/get 响应。
        self3x = ""
        if result and result.get("profile"):
            pf = result["profile"]
            # 真实 web profile id 是 3x... 形式,可能落在 user_id / eid / kwaiId 任一字段,
            # 直接扫描所有字符串值找 3x 开头的那个
            self3x = next((str(v) for v in pf.values()
                           if isinstance(v, str) and v.startswith("3x")), "")
            attempts.append(f"captured_profile:name={pf.get('user_name') or pf.get('userName') or pf.get('name') or '-'},"
                            f"3x={self3x or '-'},pf_keys={list(pf.keys())[:14]}")

        # ② 用真实 3x id 调 visionProfile 拿权威资料(含正确头像 + 粉丝/作品数,字段对齐)
        if self3x:
            full = await _vp(self3x)
            if full and full.get("profile"):
                captured = (result or {}).get("profile") or {}
                captured_counts = (result or {}).get("ownerCount") or {}
                # visionProfile 当前不回显用户自定义快手号；保留首屏
                # profile/get 的快手号、性别、关注和获赞，避免补全资料时丢失。
                for key in ("kwaiId", "gender"):
                    if captured.get(key) and not full["profile"].get(key):
                        full["profile"][key] = captured[key]
                full_counts = full.setdefault("ownerCount", {})
                for key in ("follow", "like"):
                    if key in captured_counts and key not in full_counts:
                        full_counts[key] = captured_counts[key]
                result = full      # graphql 字段与 parse_self_user 完全对齐(头像=headurl)

        # ③ 兜底:用"含本人 uid 的响应"里 harvest 出的 3x id / 资料
        if not result and hits:
            best = next((h for h in hits
                         if (h["profile"].get("user_id") or "").startswith("3x")), hits[0])
            h3x = best["profile"].get("user_id") or ""
            attempts.append(f"harvest:name={best['profile'].get('user_name') or '-'},"
                            f"3x={h3x or '-'},urls={hit_urls[:4]}")
            if h3x:
                full = await _vp(h3x)
                if full:
                    result = full
            if not result and (best["profile"].get("user_name")
                               or best["profile"].get("headurl")):
                result = best
        # ④ 兜底:换业务真实入口(cp.kuaishou.com 创作者中心)再判一次。
        #    首页会话与 cp 会话是两条独立登录链,首页失效不代表不能发布。
        #    实证:2026-09-17 同一套 cookie 下首页未登录、cp 发布页完全登录。
        if not result:
            cp_data, cp_err = await _ks_cp_self_profile(page)
            if cp_data:
                result = cp_data
                creator_verdict = True
                attempts.append(
                    "cp_fallback:ok,name="
                    f"{cp_data['profile'].get('user_name') or '-'}")
            else:
                attempts.append(f"cp_fallback:{cp_err or '-'}")
                if cp_err == "logged_out":
                    creator_verdict = False

        if has_login_btn is True:
            # 页面上的登录入口是**弱证据**:原生 SSR 骨架在 hydrate 前也带着它,
            # 首页导流位也可能渲染精确文本「登录」。只有「本地确实没有登录凭证」
            # 时才能据此定案;一旦 cookie 里还有 passToken/userId,两条证据就互相
            # 冲突,此时必须收手 —— 置空 result 换不来准确,只会把健康账号钉成
            # invalid,而判错的代价是账号冻结到人工介入。
            # 实证:2026-09-16 10:34:40(本地)的探针在 cookie 刚被重新写入 16 秒
            # 后就以 login_btn=True 判死,该账号随后被冻结 25 小时以上。
            # login_state_conflict 不含任何 auth 标记,故不会被分类成 AUTH。
            if result:
                # 创作者中心已确证会话有效 ⇒ 首页那个「登录」入口必是 SSR 骨架
                # 或导流位,忽略它。
                attempts.append("login_btn_ignored:creator_session_ok")
            elif has_credential and creator_verdict is not False:
                error = "login_state_conflict"
            else:
                # 本地无凭证,或创作者中心也明确未登录 => 真未登录。不接受 REST、
                # GraphQL 或首页缓存中的旧资料。
                result = {}
                logged_out = True
    except Exception as e:
        error = f"{e!r}"
    finally:
        checkpoint = getattr(mgr, "snapshot_session", None)
        if callable(checkpoint) and getattr(page, "context", None) is not None:
            try:
                await checkpoint(identity, page.context)
            except Exception:
                pass
        try:
            await page.close()
        except Exception:
            pass

    if not result:
        if logged_out or creator_verdict is False:
            # creator_verdict is False = 创作者中心(业务入口)明确未登录。它与首页
            # 的弱证据不同,是足以定案的强证据,所以即使首页没显示登录也判失效。
            error = "logged_out"
        elif not error:
            error = "no_profile_data"
        print(f"[ks_self_profile] 未拿到资料; err={error}; login_btn={has_login_btn}; "
              f"creator_verdict={creator_verdict}; "
              f"credential={has_credential}; passToken={has_pass_token}; "
              f"uid_cookie={uid_cookie!r}; "
              f"hit_urls={hit_urls[:6]}; attempts={attempts}")
    return result, error


# ── 快手发评论(浏览器自动化)──
# 评论输入框 / 发送按钮选择器(快手改版时改这里)
_COMMENT_INPUT = [
    'textarea[placeholder*="评论"]',
    'div[contenteditable="true"][placeholder*="评论"]',
    '.comment-editor [contenteditable="true"]',
    'textarea.comment-input',
    'div[contenteditable="true"]',
    'textarea',
]
_COMMENT_SUBMIT = [
    'button:has-text("发送")',
    'button:has-text("发布")',
    '.submit-btn',
    'span:has-text("发送")',
]


async def post_ks_comment(mgr: BrowserManager, identity: Identity, photo_id: str,
                          content: str, reply_to_text: str = "", headed: bool = True,
                          settle_ms: int = 1800, timeout_ms: int = 12000
                          ) -> Tuple[bool, str]:
    """用账号持久 profile(已含登录态)打开作品页,在评论框输入并发送。
    headed=True:弹真实窗口(写操作有头更稳,且能手动过验证码)。
    返回 (ok, error)。⚠️ 选择器随快手改版可能失效,集中在 _COMMENT_INPUT/_COMMENT_SUBMIT。"""
    content = (content or "").strip()
    if not content:
        return False, "空文案"
    ctx = None
    if headed:
        ctx = await mgr.open_headed(identity)
        page = await ctx.new_page()
    else:
        page = await mgr.new_page(identity, block_media=False)
    # 拦截评论提交接口。快手评论读取走 REST v2(/rest/v/photo/comment/list),
    # 提交大概率是同族的 /rest/v/photo/comment/add(result==1 表示成功);
    # 同时兜底 graphql 的 visionAddComment mutation。⚠️ add 端点名需真机抓包确认。
    pub = {"seen": False, "ok": False, "msg": ""}

    async def on_response(resp):
        if pub["seen"]:
            return
        url = resp.url
        is_rest_add = "/rest/v/photo/comment/add" in url or "/comment/add" in url
        if not is_rest_add and GRAPHQL_API not in url:
            return
        try:
            data = await resp.json()
        except Exception:
            return
        if is_rest_add:           # REST v2:顶层 result==1 即成功
            pub["seen"] = True
            pub["ok"] = data.get("result") in (1, "1")
            pub["msg"] = data.get("error_msg") or data.get("errorMsg") or ""
            return
        d = (data or {}).get("data") or {}
        for key in ("visionAddComment", "addComment", "commentAdd"):
            if key in d:
                r = d[key] or {}
                pub["seen"] = True
                pub["ok"] = (r.get("result") in (1, "1", None)) and not r.get("errorMsg")
                pub["msg"] = r.get("errorMsg") or ""
                break

    page.on("response", on_response)
    try:
        await page.goto(PHOTO_URL.format(pid=photo_id),
                        wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(settle_ms)
        if "passport" in page.url or "/login" in page.url:
            return False, "logged_out:账号未登录,无法发评论"

        try:
            await page.evaluate("() => window.scrollBy(0, 600)")
            await page.wait_for_selector(",".join(_COMMENT_INPUT), timeout=8000,
                                         state="attached")
        except Exception:
            pass

        editor = None
        for sel in _COMMENT_INPUT:
            loc = page.locator(sel).first
            try:
                if await loc.count():
                    editor = loc
                    break
            except Exception:
                continue
        if editor is None:
            return False, "未找到评论输入框(评论区可能未加载/被关闭/页面改版)"

        await editor.click(timeout=timeout_ms)
        await page.wait_for_timeout(300)
        await page.keyboard.type(content, delay=40)
        await page.wait_for_timeout(600)

        sent = False
        for sel in _COMMENT_SUBMIT:
            try:
                btn = page.locator(sel).first
                if await btn.count() and await btn.is_enabled():
                    await btn.click(timeout=3000)
                    sent = True
                    break
            except Exception:
                continue
        if not sent:
            try:
                await page.keyboard.press("Enter")
                sent = True
            except Exception:
                pass
        if not sent:
            return False, "未找到发送按钮且回车提交失败"

        for _ in range(27):       # 等提交接口回包,最多 ~8s
            if pub["seen"]:
                break
            await page.wait_for_timeout(300)

        if pub["seen"]:
            if pub["ok"]:
                return True, ""
            return False, (f"快手拒绝评论({pub['msg'] or '未知原因'})—— 多为验证码/频控/风控,"
                           f"请降低频率或换号稍后再试")
        return False, "未捕获到快手提交接口响应,无法确认是否成功(请人工核对该作品评论区)"
    except Exception as e:
        return False, f"发评论异常: {e!r}"
    finally:
        try:
            if ctx is not None:
                try:
                    checkpoint = getattr(mgr, "snapshot_session", None)
                    if callable(checkpoint):
                        await checkpoint(identity, ctx)
                except Exception:
                    pass
                finally:
                    await ctx.close()
            else:
                await page.close()
        except Exception:
            pass
