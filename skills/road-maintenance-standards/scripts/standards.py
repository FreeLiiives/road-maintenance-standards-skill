"""Road standards metadata monitor. Python 3.10+, standard library only."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 3_000_000
ALLOWED_HOSTS = {"xxgk.mot.gov.cn"}
CODE = re.compile(r"\b(?:JTG\s*/\s*T|JTG|JTJ|GB\s*/\s*T|GB)\s*[A-Z]?\s*\d+(?:[.\-]\d+)*\s*[—–-]\s*\d{4}\b", re.I)
TOPICS = ("养护", "路面", "病害", "公路技术状况", "公路工程行业标准", "废止", "修改单", "局部修订")


def read_json(path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def normalized(value):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()


def compact(value):
    return re.sub(r"[\s—–_-]+", "", normalized(value).casefold())


def safe_url(url):
    p = urllib.parse.urlsplit(url)
    if (p.scheme != "https" or p.hostname not in ALLOWED_HOSTS
            or p.username or p.password or p.port not in (None, 443)):
        raise ValueError("URL must use HTTPS on an explicitly allowed official host")
    return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, p.query, ""))


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, code, msg, headers, safe_url(newurl))


def fetch(url, timeout=20):
    """Keep TLS verification enabled; never forward credentials or follow off-host redirects."""
    url = safe_url(url)
    opener = urllib.request.build_opener(SafeRedirect())
    error = None
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "RoadStandardsSkill/1.0 (+https://github.com/FreeLiiives/road-maintenance-standards-skill)"})
            with opener.open(req, timeout=timeout) as response:
                safe_url(response.url)
                if "html" not in response.headers.get("Content-Type", "").lower():
                    raise ValueError("Expected an HTML announcement, not a PDF or download")
                raw = response.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise ValueError("HTML exceeds configured size limit")
                encoding = response.headers.get_content_charset()
                if not encoding:
                    match = re.search(br'charset\s*=\s*["\x27]?([\w-]+)', raw[:4096], re.I)
                    encoding = match.group(1).decode("ascii") if match else "utf-8"
                return raw.decode(encoding, errors="strict")
        except Exception as exc:
            error = exc
            if attempt == 0:
                time.sleep(1)
    raise error


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.texts = []
        self.links = []
        self.anchor = None
        self.in_title = False
        self.title_parts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style", "noscript"):
            self.skip += 1
        if self.skip:
            return
        if tag == "title":
            self.in_title = True
        if tag == "a":
            self.anchor = [attrs.get("href", ""), [], attrs.get("title", "")]

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.skip = max(0, self.skip - 1)
        if tag == "title":
            self.in_title = False
        if tag == "a" and self.anchor:
            href, parts, title = self.anchor
            self.links.append((href, normalized(title or " ".join(parts))))
            self.anchor = None

    def handle_data(self, data):
        if self.skip or not data.strip():
            return
        self.texts.append(data)
        if self.in_title:
            self.title_parts.append(data)
        if self.anchor:
            self.anchor[1].append(data)


def parse_page(raw):
    parser = PageParser()
    parser.feed(raw)
    return parser


def discover(raw, base_url):
    page = parse_page(raw)
    found = {}
    for href, title in page.links:
        if not title or not any(term in title for term in TOPICS):
            continue
        try:
            url = safe_url(urllib.parse.urljoin(base_url, href))
        except ValueError:
            continue
        if re.search(r"/t\d{8}_\d+\.html$", urllib.parse.urlsplit(url).path):
            found[url] = title
    if not found:
        raise ValueError("No relevant announcement links; page layout or access may have changed")
    return found


def fingerprint(raw):
    page = parse_page(raw)
    text = normalized(" ".join(page.texts))
    # MOT pages repeat metadata above the body. Anchor to the announcement paragraph.
    starts = [m.start() for m in re.finditer(r"现发布|各省、自治区|各有关单位", text)]
    body = text[min(starts):] if starts else text
    body = re.split(r"相关文档|联系我们", body, maxsplit=1)[0].strip()
    title = normalized(" ".join(page.title_parts))
    if not title or "交通运输部" not in text or len(body) < 40:
        raise ValueError("Announcement identity/body could not be verified")
    if not CODE.search(body):
        raise ValueError("No standard identifier found; manual review required")
    return {"title": title, "sha256": hashlib.sha256(body.encode()).hexdigest(),
            "detected_codes": sorted({normalized(m.group()) for m in CODE.finditer(body)}),
            "review_signals": [w for w in ("废止", "替代", "修订", "修改单", "征求意见", "计划") if w in body]}


def date_state(item, on=None):
    on = on or dt.date.today()
    if item.get("effective_date") and dt.date.fromisoformat(item["effective_date"]) > on:
        return "已发布，尚未到公告实施日"
    return "已到公告实施日；最新有效性仍需核验"


def search(catalog, query, mappings=None):
    tokens = [compact(x) for x in re.split(r"\s+", query) if x]
    whole = compact(query)
    if CODE.fullmatch(normalized(query)):
        return [item for item in catalog if whole in {compact(c) for c in [item['code'], *item.get('supersedes', [])]}]
    alias = next((v for k, v in (mappings or {}).items() if k.casefold() == query.casefold()), None)
    if alias:
        tokens.extend(compact(x) for x in alias["keywords"])
    rows = []
    for item in catalog:
        hay = compact(" ".join([item["code"], item["title"], *item["tags"], *item.get("supersedes", [])]))
        score = sum(1 for token in tokens if token and token in hay)
        if whole and whole in hay:
            score += 5
        if score:
            rows.append((score, item))
    return [row[1] for row in sorted(rows, key=lambda r: (-r[0], r[1]["code"]))]


def md_text(value):
    return html.escape(str(value)).replace("|", "&#124;").replace("\n", " ")


def sync(root=ROOT, fetcher=fetch, now=None, max_new=20, delay=0.5):
    stamp = now or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    data = root / "data"
    catalog = read_json(data / "catalog.json", [])
    sources = read_json(data / "sources.json", [])
    state = read_json(data / "observations.json", {"pages": {}, "candidates": {}})
    health, changes = [], []
    pending = {}
    for source in sources:
        try:
            links = discover(fetcher(source["url"]), source["url"])
            pending.update(links)
            health.append({"source": source["id"], "url": source["url"], "ok": True, "links": len(links)})
        except Exception as exc:
            health.append({"source": source["id"], "url": source["url"], "ok": False, "error": type(exc).__name__ + ": " + str(exc)[:240]})
    known = {item["source_url"] for item in catalog}
    for url, title in sorted(pending.items()):
        if url not in known and url not in state["candidates"]:
            state["candidates"][url] = {"title": title, "first_seen": stamp, "review_status": "unreviewed"}
            changes.append({"kind": "discovered", "url": url, "title": title})
    # Process never-fetched candidates first so a large feed eventually drains.
    candidates = sorted(state["candidates"], key=lambda u: (state["pages"].get(u, {}).get("last_attempt", ""), u))
    targets = sorted(known) + [u for u in candidates if u not in known][:max_new]
    for url in targets:
        old = state["pages"].get(url, {})
        try:
            info = fingerprint(fetcher(url))
            kind = "baseline" if not old.get("sha256") else ("changed" if info["sha256"] != old["sha256"] else "unchanged")
            if kind != "unchanged":
                changes.append({"kind": kind, "url": url, "title": info["title"], "previous_sha256": old.get("sha256"), "sha256": info["sha256"]})
            state["pages"][url] = {**info, "last_attempt": stamp, "last_success": stamp, "fetch_status": "ok"}
            health.append({"source": "announcement", "url": url, "ok": True})
        except Exception as exc:
            # Preserve the last good hash and date; a failed fetch is not a deletion.
            error = type(exc).__name__ + ": " + str(exc)[:240]
            state["pages"][url] = {**old, "last_attempt": stamp, "fetch_status": "error", "error": error}
            health.append({"source": "announcement", "url": url, "ok": False, "error": error})
        if delay:
            time.sleep(delay)
    state["last_run"] = stamp
    state["health"] = health
    write_json(data / "observations.json", state)
    failures = sum(not row["ok"] for row in health)
    result = {"checked_at": stamp, "failures": failures, "changes": changes, "health": health,
              "candidate_count": len(state["candidates"]), "pending_first_fetch": sum(u not in state["pages"] for u in state["candidates"])}
    reports = root / "reports"
    write_json(reports / "latest.json", result)
    lines = ["# 道路养护规范监测报告", "", f"检查时间（UTC）：{stamp}", "",
             f"访问失败：{failures}；本轮事件：{len(changes)}；待复核候选：{len(state['candidates'])}。", "",
             "访问失败或待抓取项目表示覆盖不完整；未发现变化也不等于所有规范均为现行。候选不会自动改写已核对目录。", "", "## 本轮事件", ""]
    labels = {"discovered": "发现候选", "baseline": "建立基线", "changed": "正文变化，待核验"}
    lines += [f"- {labels[c['kind']]}：{md_text(c['title'])} — {c['url']}" for c in changes] or ["本轮未记录变化。"]
    lines += ["", "## 数据源健康", "", "| 状态 | 地址 | 说明 |", "| --- | --- | --- |"]
    lines += [f"| {'正常' if h['ok'] else '失败'} | {h['url']} | {md_text(h.get('error', '已读取'))} |" for h in health]
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "latest.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Skill folder (data and reports live here)")
    subs = parser.add_subparsers(dest="command", required=True)
    s = subs.add_parser("search", help="Offline metadata search")
    s.add_argument("query")
    s.add_argument("--json", action="store_true")
    subs.add_parser("list", help="List reviewed publication metadata")
    subs.add_parser("graph", help="Export evidenced supersession edges and topic links as JSON")
    u = subs.add_parser("sync", help="Fetch official sources; exit 2 for partial or total failure")
    u.add_argument("--max-new", type=int, default=20)
    args = parser.parse_args()
    if args.command == "sync":
        if args.max_new < 0 or args.max_new > 100:
            parser.error("--max-new must be 0..100")
        result = sync(args.root, max_new=args.max_new)
        print(json.dumps({k: v for k, v in result.items() if k != "health"}, ensure_ascii=False, indent=2))
        return 2 if result["failures"] else 0
    catalog = read_json(args.root / "data/catalog.json", [])
    mappings = read_json(args.root / "data/yolo-labels.json", {})
    if args.command == "graph":
        edges = []
        for item in catalog:
            edges += [{"subject": item["code"], "relation": "supersedes_on", "object": old, "date": item["effective_date"], "source_url": item["source_url"]} for old in item.get("supersedes", [])]
            edges += [{"subject": item["code"], "relation": "retrieval_topic", "object": tag, "evidence": "project_index_not_normative_classification"} for tag in item["tags"]]
        print(json.dumps(edges, ensure_ascii=False, indent=2))
        return 0
    rows = catalog if args.command == "list" else search(catalog, args.query, mappings)
    if getattr(args, "json", False):
        print(json.dumps([{**r, "date_state": date_state(r)} for r in rows], ensure_ascii=False, indent=2))
    else:
        print("仅检索公告元数据；标准全文条款与最新有效状态须核验。")
        if args.command == "search" and args.query.casefold() in {k.casefold() for k in mappings}:
            print("YOLO 类别仅用于关联检索，不能据此认定规范病害等级、计算 PCI 或直接制定处置方案。")
        for r in rows:
            print(f"\n{r['code']}  {r['title']}\n  实施日期：{r['effective_date']}；{date_state(r)}\n  公告核对：{r['verified_on']}；最新状态：未作穷尽核验\n  来源：{r['source_url']}")
        if not rows:
            print("目录中未匹配到条目；这不代表不存在相关标准。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
