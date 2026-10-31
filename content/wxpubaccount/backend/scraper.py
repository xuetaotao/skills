"""用 Playwright 抓公众号后台：登录 → 发表记录（自动翻页）→ 用户分析 / 内容分析 → 单篇详情页。

- 登录态保存在 data/browser_profile/，会话没过期时不用重新扫码；需要扫码时二维码截图写到
  data/raw/qr/qr.png，网页上会显示出来（也可以选「显示浏览器窗口」直接在窗口里扫）。
- 页面快照用 Chrome 无障碍树（CDP Accessibility.getFullAXTree）生成，格式与旧的 agent-browser
  快照一致，snapshot.py 两种都能解析。
- 覆盖已有的原始快照前，旧文件先移到 data/raw/history/<时间>/，历史时点的数据不会丢。
"""

import json
import re
import shutil
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

from . import snapshot
from .config import (BROWSER_PROFILE, CONTENT_ANALYSIS_URL, DETAIL_MODES, DETAIL_RECENT_DAYS, DETAIL_URL, LOGIN_TIMEOUT,
                     MAX_PUBLISH_PAGES, MP_HOME, NAV_TIMEOUT, PAGE_SETTLE, PUBLISH_URL, QR_PATH, QR_REFRESH,
                     RAW_DIR, RAW_HISTORY_DIR, USER_AGENT, USER_ANALYSIS_URL, VIEWPORT)
from .dataset import BEIJING, detail_files

EXTRACT_JS = "\n".join(line for line in (Path(__file__).with_name("extract_pub.js")
                                          .read_text(encoding="utf-8").splitlines()) if not line.startswith("//"))
QR_SELECTORS = [".login__type__container__scan__qrcode", ".login__type__container__scan img",
                "img[src*='qrcode']", ".qrcode img", "img.qrcode"]
SKIP_ROLES = {"InlineTextBox", "none", "presentation", "RootWebArea", "LineBreak"}


class ScrapeError(Exception):
    """抓取失败，消息直接给用户看。"""


class Cancelled(Exception):
    pass


class Job:
    """抓取任务的状态，网页轮询 /api/scrape 读取。"""

    def __init__(self, echo=False):
        self.echo = echo
        self.cancel_requested = False
        self._lock = threading.Lock()
        self.state = dict(running=False, phase=None, message="", done=0, total=0, waiting_qr=False, qr_version=0,
                          qr_round=0, error=None, warnings=[], log=[], started=None, finished=None, result=None,
                          options=None)

    def update(self, **kw):
        with self._lock:
            self.state.update(kw)

    def log(self, msg, warn=False):
        stamp = datetime.now().strftime("%H:%M:%S")
        with self._lock:
            self.state["log"] = (self.state["log"] + [f"{stamp} {msg}"])[-200:]
            self.state["message"] = msg
            if warn:
                self.state["warnings"] = self.state["warnings"] + [msg]
        if self.echo:
            print(("⚠ " if warn else "  ") + msg, flush=True)

    def snapshot(self):
        with self._lock:
            return json.loads(json.dumps(self.state, default=str))

    def check(self):
        if self.cancel_requested:
            raise Cancelled()


# ---------------- 页面快照 ----------------

def ax_snapshot(page) -> str:
    """当前页面的无障碍树，缩进文本，一行一个节点：- 角色 "名称"。"""
    cdp = page.context.new_cdp_session(page)
    try:
        nodes = cdp.send("Accessibility.getFullAXTree")["nodes"]
    finally:
        cdp.detach()
    by_id = {n["nodeId"]: n for n in nodes}
    roots = [n for n in nodes if not n.get("parentId")]
    lines = []
    stack = [(r, 0) for r in reversed(roots)]
    while stack:
        node, depth = stack.pop()
        role = (node.get("role") or {}).get("value", "")
        name = str((node.get("name") or {}).get("value", "") or "")
        child_depth = depth
        if not node.get("ignored") and role not in SKIP_ROLES:
            name = " ".join(name.split()) if name.strip() else name
            label = f' "{name.replace(chr(34), chr(92) + chr(34))}"' if name else ""
            lines.append(f"{'  ' * depth}- {role}{label}")
            child_depth = depth + 1
        for cid in reversed(node.get("childIds", [])):
            child = by_id.get(cid)
            if child:
                stack.append((child, child_depth))
    return "\n".join(lines) + "\n"


def _archive(paths, stamp):
    """把即将被覆盖的旧快照移到 history/<stamp>/。"""
    moved = 0
    for p in paths:
        if p.exists():
            dest = RAW_HISTORY_DIR / stamp
            dest.mkdir(parents=True, exist_ok=True)
            shutil.move(str(p), str(dest / p.name))
            moved += 1
    return moved


def _save_raw(name, text, stamp):
    path = RAW_DIR / name
    _archive([path], stamp)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ---------------- 抓取 ----------------

class Scraper:
    def __init__(self, job: Job, show_browser=False):
        self.job = job
        self.show = show_browser
        self.stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.token = None
        self.page = None

    def _goto(self, url, settle=PAGE_SETTLE):
        self.job.check()
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
        except Exception as e:  # noqa: BLE001 - Playwright 的超时/网络错误都按打开失败处理
            raise ScrapeError(f"打开页面失败：{str(e).splitlines()[0]}") from None
        self.page.wait_for_timeout(settle)

    # ---- 登录 ----
    def _token_from_url(self):
        m = re.search(r"[?&]token=(\d+)", self.page.url)
        return m.group(1) if m else None

    def _save_qr(self):
        QR_PATH.parent.mkdir(parents=True, exist_ok=True)
        for sel in QR_SELECTORS:
            loc = self.page.locator(sel).first
            try:
                if loc.count() and loc.is_visible():
                    loc.screenshot(path=str(QR_PATH), timeout=3000)
                    return
            except Exception:  # noqa: BLE001 - 换下一个选择器
                continue
        self.page.screenshot(path=str(QR_PATH))

    def login(self):
        self.job.update(phase="login")
        self.job.log("打开公众号后台")
        self._goto(MP_HOME, settle=2500)
        token = self._token_from_url()
        if token:
            self.job.log("登录状态有效，免扫码")
        else:
            self.job.log("请用微信扫码登录" + ("（浏览器窗口里或本页的二维码都可以）" if self.show else "（扫描本页显示的二维码）"))
            start = loaded = time.time()
            shown = 0
            while not token:
                self.job.check()
                if time.time() - start > LOGIN_TIMEOUT:
                    raise ScrapeError(f"{LOGIN_TIMEOUT} 秒内没有完成扫码登录")
                if time.time() - loaded > QR_REFRESH:
                    self.job.log("二维码快过期了，已刷新")
                    self.page.reload(wait_until="domcontentloaded")
                    self.page.wait_for_timeout(2000)
                    loaded = time.time()
                    shown = 0
                    self.job.update(qr_round=self.job.snapshot()["qr_round"] + 1)
                if time.time() - shown > 3:
                    try:
                        self._save_qr()
                        st = self.job.snapshot()
                        self.job.update(waiting_qr=True, qr_version=st["qr_version"] + 1)
                    except Exception:  # noqa: BLE001 - 页面跳转中截不了图，下一轮再试
                        pass
                    shown = time.time()
                self.page.wait_for_timeout(1000)
                token = self._token_from_url()
            self.job.update(waiting_qr=False)
            self.job.log("登录成功")
            self.page.wait_for_timeout(2500)
        self.token = token

    def menu_links(self):
        try:
            links = self.page.evaluate("""() => [...document.querySelectorAll('a')]
                .map(a => [a.textContent.trim(), a.getAttribute('href') || ''])
                .filter(([t, h]) => h && /分析/.test(t))""")
        except Exception:  # noqa: BLE001 - 拿不到就用兜底地址
            links = []
        found = {}
        for text, href in links:
            for key in ("内容分析", "用户分析"):
                if key in text and key not in found:
                    found[key] = urljoin(MP_HOME, href)
        return (found.get("内容分析") or CONTENT_ANALYSIS_URL.format(token=self.token),
                found.get("用户分析") or USER_ANALYSIS_URL.format(token=self.token))

    # ---- 发表记录 ----
    def _extract_publish(self):
        try:
            self.page.wait_for_selector(".weui-desktop-mass-media", timeout=8000)
        except Exception:  # noqa: BLE001 - 空页就没有卡片
            pass
        cards = json.loads(self.page.evaluate(EXTRACT_JS) or "[]")
        if not cards:
            self.page.wait_for_timeout(3000)
            cards = json.loads(self.page.evaluate(EXTRACT_JS) or "[]")
        return cards

    def publish_list(self):
        self.job.update(phase="publish", done=0, total=0)
        pages, count = [], 0
        for i in range(MAX_PUBLISH_PAGES):
            self._goto(PUBLISH_URL.format(begin=i * 20, token=self.token), settle=1500)
            cards = self._extract_publish()
            if not cards:
                break
            pages.append(cards)
            count += len(cards)
            self.job.update(done=i + 1)
            self.job.log(f"发表记录第 {i + 1} 页：{len(cards)} 篇（累计 {count} 篇）")
        else:
            self.job.log(f"翻到 {MAX_PUBLISH_PAGES} 页还没到底，发表记录可能不完整", warn=True)
        if not pages:
            raise ScrapeError("发表记录页没有读到任何文章：可能登录失效，或后台页面结构变了")
        old = list(RAW_DIR.glob("publish_p*.txt"))
        _archive(old, self.stamp)
        for n, cards in enumerate(pages, 1):
            (RAW_DIR / f"publish_p{n}.txt").write_text(json.dumps(cards, ensure_ascii=False), encoding="utf-8")
        return [c for cards in pages for c in cards]

    # ---- 总览 ----
    def overviews(self):
        self.job.update(phase="overview")
        content_url, user_url = self.menu_links()
        self.job.log("抓取用户分析（累计关注、新增关注渠道）")
        self._goto(user_url)
        text = ax_snapshot(self.page)
        ua = snapshot.parse_user_analysis(text)
        if ua["fans"] is None:
            self.job.log("用户分析页没解析到「累计关注人数」，保留上次的快照", warn=True)
        else:
            _save_raw("user_analysis.txt", text, self.stamp)
            self.job.log(f"累计关注 {ua['fans']} 人，月增长 {ua['growth_month_pct']}%")
        self.job.log("抓取内容分析（流量来源、阅读总人数）")
        self._goto(content_url)
        text = ax_snapshot(self.page)
        ca = snapshot.parse_content_analysis(text)
        if not ca["traffic"]:
            self.job.log("内容分析页没解析到流量来源，保留上次的快照", warn=True)
        else:
            _save_raw("content_analysis.txt", text, self.stamp)
            self.job.log(f"阅读总人数 {ca['total_readers']}，推荐占 {ca['traffic'].get('推荐', 0):.1f}%")

    # ---- 单篇详情 ----
    @staticmethod
    def detail_targets(cards, mode):
        have = detail_files()
        today = date.today()
        targets, seen = [], set()
        for c in cards:
            aid, ts = c.get("appmsg_id"), c.get("send_time")
            if not aid or not ts or aid in seen:
                continue
            seen.add(aid)
            pub = datetime.fromtimestamp(int(ts), BEIJING).date()
            recent = (today - pub).days <= DETAIL_RECENT_DAYS
            missing = aid not in have
            if (mode == "all" or (mode == "recent" and recent) or (mode == "missing" and missing)
                    or (mode == "missing_recent" and (missing or recent))):
                title = (c.get("title") or "").replace("\u200b", "").strip()
                targets.append({"id": aid, "date": pub.isoformat(), "title": title})
        return sorted(targets, key=lambda t: t["date"], reverse=True)

    def details(self, targets):
        self.job.update(phase="details", done=0, total=len(targets))
        ok = failed = 0
        for i, t in enumerate(targets, 1):
            self.job.update(done=i - 1)
            self.job.log(f"详情页 {i}/{len(targets)}：{t['title'][:24]}（{t['date']}）")
            parsed = {}
            for attempt in range(2):
                self._goto(DETAIL_URL.format(msgid=t["id"], date=t["date"], token=self.token), settle=1500)
                try:
                    self.page.get_by_text("完读率").first.wait_for(timeout=15_000)
                except Exception:  # noqa: BLE001 - 没等到也先截一次看看
                    pass
                self.page.wait_for_timeout(PAGE_SETTLE if attempt else 2000)
                text = ax_snapshot(self.page)
                parsed = snapshot.parse_detail(text)
                if parsed.get("completion") is not None or parsed.get("reads_d2") is not None:
                    break
            if parsed.get("completion") is not None or parsed.get("reads_d2") is not None:
                _save_raw(f"d2_{t['id']}.txt", text, self.stamp)
                ok += 1
            else:
                failed += 1
                self.job.log(f"《{t['title'][:20]}》详情页没读到数据，跳过（旧快照保留）", warn=True)
        self.job.update(done=len(targets))
        return ok, failed


def run(job: Job, details="missing_recent", show_browser=False) -> dict:
    """完整抓取。返回统计；出错抛 ScrapeError / Cancelled。"""
    if details not in DETAIL_MODES:
        raise ScrapeError(f"详情页范围只能是：{', '.join(DETAIL_MODES)}")
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise ScrapeError("缺少 playwright：pip install -r requirements.txt，然后 python -m playwright install chromium") from None

    started = time.time()
    s = Scraper(job, show_browser)
    BROWSER_PROFILE.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        try:
            ctx = pw.chromium.launch_persistent_context(
                str(BROWSER_PROFILE), headless=not show_browser, viewport=VIEWPORT, locale="zh-CN",
                user_agent=USER_AGENT)
        except PlaywrightError as e:
            if "Executable doesn't exist" in str(e):
                raise ScrapeError("没有找到 Playwright 自带的 Chromium，请先运行：python -m playwright install chromium") from None
            if "user data directory is already in use" in str(e).lower() or "ProcessSingleton" in str(e):
                raise ScrapeError("登录用的浏览器已经开着（另一个抓取任务？），先关掉它再试") from None
            raise ScrapeError(f"启动浏览器失败：{str(e).splitlines()[0]}") from None
        try:
            s.page = ctx.pages[0] if ctx.pages else ctx.new_page()
            s.login()
            cards = s.publish_list()
            s.overviews()
            targets = s.detail_targets(cards, details) if details != "none" else []
            if targets:
                ok, failed = s.details(targets)
            else:
                ok = failed = 0
                job.log("没有需要抓的详情页" if details != "none" else "按设置跳过详情页")
        finally:
            ctx.close()
            try:
                QR_PATH.unlink()
            except OSError:
                pass
    archived = RAW_HISTORY_DIR / s.stamp
    return {"articles": len(cards), "details_ok": ok, "details_failed": failed, "seconds": round(time.time() - started),
            "archived": str(archived) if archived.exists() else None}


def run_in_thread(job: Job, details, show_browser, after=None):
    """网页用：后台线程跑完整抓取，结束后调用 after()（例如重新分析）。"""
    job.cancel_requested = False
    job.update(running=True, phase="start", message="准备启动浏览器", done=0, total=0, waiting_qr=False, error=None,
               warnings=[], log=[], started=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), finished=None, result=None,
               options={"details": details, "show_browser": show_browser})

    def work():
        try:
            result = run(job, details, show_browser)
            job.log(f"抓取完成：{result['articles']} 篇发表记录，详情页成功 {result['details_ok']} 篇"
                    + (f"、失败 {result['details_failed']} 篇" if result["details_failed"] else ""))
            if after:
                job.update(phase="analyze")
                job.log("重新分析并生成报告")
                try:
                    result["analysis"] = after()
                except ValueError as e:
                    job.log(f"数据已抓好，但没有重新分析：{e}", warn=True)
            job.update(result=result, phase="done")
        except Cancelled:
            job.update(error="已取消", phase="cancelled")
            job.log("已取消")
        except ScrapeError as e:
            job.update(error=str(e), phase="failed")
            job.log(str(e), warn=True)
        except Exception as e:  # noqa: BLE001 - 意外错误也要让网页知道
            job.update(error=f"{type(e).__name__}: {e}", phase="failed")
            job.log(f"出错：{e}", warn=True)
        finally:
            job.update(running=False, waiting_qr=False, finished=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    threading.Thread(target=work, daemon=True).start()


def status_summary() -> dict:
    """数据新鲜度：上次抓取时间、详情覆盖情况。"""
    pages = list(RAW_DIR.glob("publish_p*.txt"))
    last = max((p.stat().st_mtime for p in pages), default=None)
    return {
        "last_scrape": datetime.fromtimestamp(last).strftime("%Y-%m-%d %H:%M") if last else None,
        "days_since": (date.today() - datetime.fromtimestamp(last).date()).days if last else None,
        "detail_files": len(detail_files()),
        "logged_in_before": BROWSER_PROFILE.exists() and any(BROWSER_PROFILE.iterdir()),
        "recent_cutoff": (date.today() - timedelta(days=DETAIL_RECENT_DAYS)).isoformat(),
    }
