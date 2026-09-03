#!/usr/bin/env python3
"""deploy_userscripts.py — 批量把油猴脚本分发到所有 agent 的 Tampermonkey。

Run inside the API container (has python3 + websockets, can reach agent-N:19222).

流程（对每个 agent-N）：
  1. 确保 chrome://extensions 的 Allow User Scripts 开关已开（TM v5.5 MV3 必需）
  2. TM options.html Utilities -> Import from URL 填入脚本 URL
  3. 点 Install -> ask.html 确认页点安装
  4. Dashboard 验证已安装

脚本源：宿主机 chrome-extra/scripts/*.user.js（通过 docker network 用 http 服务暴露），
或直接读 /opt/scripts/*.user.js（若 api 容器也挂载了 scripts 目录）。

用法：
  python3 deploy_userscripts.py --cdp-list http://agent-1:19222,http://agent-2:19222
  python3 deploy_userscripts.py --all            # 从 AGENT_POOL_ENDPOINTS 发现
  python3 deploy_userscripts.py --agent 2        # 只装 agent-2
"""
import argparse
import asyncio
import json
import os
import re
import sys
import urllib.parse
import urllib.request

import websockets

TM_ID = "aoikodbkdkiloggabbnccakhjdjgmmip"


def discover_endpoints() -> list[str]:
    pool = os.environ.get("AGENT_POOL_ENDPOINTS", "").strip()
    if pool:
        eps = [e.strip() for e in pool.split(",") if e.strip()]
        if eps:
            return eps
    return ["http://agent-1:19222"]


def endpoint_index(ep: str) -> int:
    m = re.search(r"agent-(\d+)", ep)
    return int(m.group(1)) if m else 1


def get_tabs(cdp: str):
    with urllib.request.urlopen(f"{cdp}/json", timeout=5) as r:
        return json.load(r)


def new_tab(cdp: str, url: str):
    req = urllib.request.Request(
        f"{cdp}/json/new?" + urllib.parse.quote(url, safe=":/?#&=%"), method="PUT"
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


class TabSession:
    """One persistent CDP session per tab — NEVER reconnect mid-operation."""

    def __init__(self, ws_url: str):
        self.ws_url = ws_url

    async def __aenter__(self):
        self.ws = await websockets.connect(self.ws_url, max_size=2 ** 26)
        self._mid = 0
        await self.call("Runtime.enable")
        await self.call("DOM.enable")
        await self.call("Page.enable")
        return self

    async def __aexit__(self, *a):
        try:
            await self.ws.close()
        except Exception:
            pass

    async def call(self, method: str, params: dict | None = None):
        self._mid += 1
        mid = self._mid
        await self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get("id") == mid:
                return msg

    async def ev(self, expr: str):
        r = await self.call("Runtime.evaluate", {"expression": expr, "returnByValue": True})
        try:
            return r["result"]["result"]["value"]
        except Exception:
            return str(r)[:300]


async def enable_allow_user_scripts(cdp: str) -> str:
    t = new_tab(cdp, f"chrome://extensions/?id={TM_ID}")
    async with TabSession(t["webSocketDebuggerUrl"]) as s:
        await asyncio.sleep(7)
        r = await s.ev("""
        (() => {
          const found = [];
          function walk(root) {
            let nodes = [];
            try { nodes = [...root.querySelectorAll('*')]; } catch(e) {}
            for (const el of nodes) {
              if (el.id === 'allow-user-scripts' || el.id === 'allowUserScripts') found.push(el);
              if (el.shadowRoot) walk(el.shadowRoot);
            }
          }
          walk(document);
          if (!found.length) return 'NOT_FOUND';
          const row = found[0];
          const toggle = row.shadowRoot ? row.shadowRoot.querySelector('cr-toggle') : null;
          const btn = toggle || row.querySelector('cr-toggle') || row;
          try { btn.click(); } catch(e) { return 'CLICK_ERR:' + e.message; }
          return 'CLICKED';
        })()
        """)
        await asyncio.sleep(2)
    try:
        req = urllib.request.Request(f"{cdp}/json/close/{t['id']}", method="GET")
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass
    return str(r)


async def import_one(cdp: str, script_url: str) -> tuple[bool, str]:
    t = new_tab(cdp, f"chrome-extension://{TM_ID}/options.html")
    async with TabSession(t["webSocketDebuggerUrl"]) as s:
        await asyncio.sleep(4)
        await s.ev("""
        (() => { const tab = [...document.querySelectorAll('div.tv_tab')].find(d =>
          /^Utilities$/i.test((d.innerText||'').trim())); if (tab) tab.click(); return 1; })()
        """)
        await asyncio.sleep(3)
        r = await s.ev("""
        (() => {
          const inp = document.querySelector('input.updateurl_input')
            || document.querySelector('input[type=text]');
          const btns = [...document.querySelectorAll('input[type=button], button')];
          const btn = btns.find(b => /^Install$/i.test((b.value||b.innerText||'').trim()));
          if (!inp || !btn) return 'CTRL_MISSING inp=' + !!inp + ' btn=' + !!btn;
          const setter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value').set;
          setter.call(inp, '""" + script_url + """');
          inp.dispatchEvent(new Event('input', {bubbles:true}));
          inp.dispatchEvent(new Event('change', {bubbles:true}));
          btn.click();
          return 'INSTALL_CLICKED';
        })()
        """)
        await asyncio.sleep(8)

    installed = False
    for _ in range(3):
        for p in get_tabs(cdp):
            if "ask.html" not in (p.get("url") or ""):
                continue
            try:
                async with TabSession(p["webSocketDebuggerUrl"]) as s:
                    res = await s.ev("""
                    (() => {
                      const btns = [...document.querySelectorAll(
                        'input[type=button].install, button.install, .install')];
                      const hit = btns.find(
                        b => !/^Cancel$/i.test((b.value||b.innerText||'').trim()));
                      if (hit) { hit.click();
                        return 'CLICKED:' + (hit.value||hit.innerText||'').trim(); }
                      return 'NO_HIT';
                    })()
                    """)
                    if str(res).startswith("CLICKED"):
                        installed = True
            except Exception:
                pass  # tab navigated/closed after install
        if installed:
            break
        await asyncio.sleep(3)
    try:
        req = urllib.request.Request(f"{cdp}/json/close/{t['id']}", method="GET")
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass
    return installed, str(r)


async def verify_installed(cdp: str, names: list[str]) -> bool:
    t = new_tab(cdp, f"chrome-extension://{TM_ID}/options.html")
    async with TabSession(t["webSocketDebuggerUrl"]) as s:
        await asyncio.sleep(4)
        await s.ev("""
        (() => { const tab = [...document.querySelectorAll('div.tv_tab')].find(d =>
          /^Installed Userscripts$/i.test((d.innerText||'').trim()));
          if (tab) tab.click(); return 1; })()
        """)
        await asyncio.sleep(3)
        body = await s.ev("document.body ? document.body.innerText : ''") or ""
        return all(n in body for n in names)


def serve_scripts_dir() -> int:
    """Serve /opt/scripts (or /home/chrome/scripts) on an ephemeral port; return port."""
    import http.server
    import socketserver
    import threading

    for cand in ("/opt/scripts", "/home/chrome/scripts", "/tmp/scripts"):
        if os.path.isdir(cand):
            scripts_dir = cand
            break
    else:
        raise FileNotFoundError(
            "no scripts dir found (/opt/scripts, /home/chrome/scripts, /tmp/scripts)"
        )

    handler = http.server.SimpleHTTPRequestHandler
    os.chdir(scripts_dir)
    with socketserver.TCPServer(("0.0.0.0", 0), handler) as httpd:
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        return port


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--all", action="store_true",
        help="discover all endpoints from AGENT_POOL_ENDPOINTS",
    )
    ap.add_argument("--agent", type=int, help="only deploy to agent-N")
    ap.add_argument("--cdp-list", help="comma-separated CDP endpoints")
    ap.add_argument("--skip-toggle", action="store_true", help="skip Allow User Scripts toggle")
    args = ap.parse_args()

    if args.cdp_list:
        eps = [e.strip() for e in args.cdp_list.split(",") if e.strip()]
    elif args.agent:
        eps = [f"http://agent-{args.agent}:19222"]
    elif args.all:
        eps = discover_endpoints()
    else:
        ap.error("need --all, --agent N, or --cdp-list")

    # serve the scripts dir so TM can fetch .user.js by URL
    port = serve_scripts_dir()
    script_names = sorted(f for f in os.listdir("/opt/scripts") if f.endswith(".user.js")) \
        if os.path.isdir("/opt/scripts") else []
    if not script_names:
        for cand in ("/home/chrome/scripts", "/tmp/scripts"):
            if os.path.isdir(cand):
                script_names = sorted(f for f in os.listdir(cand) if f.endswith(".user.js"))
                break
    if not script_names:
        print("ERROR: no .user.js found in any scripts dir")
        sys.exit(1)

    print(f"scripts to deploy: {script_names}")
    print(f"endpoints: {eps}")

    for ep in eps:
        idx = endpoint_index(ep)
        print(f"\n=== agent-{idx} ({ep}) ===")
        if not args.skip_toggle:
            r = await enable_allow_user_scripts(ep)
            print(f"  allow-user-scripts toggle: {r}")
        ok_all = True
        for name in script_names:
            # CRITICAL: TM 的 Chrome 跑在 agent-N 容器，URL 必须用 docker 网络内
            # api 容器的主机名（api），不能用 localhost（localhost 对 agent-N 是它自己）
            url = f"http://api:{port}/{name}"
            print(f"  importing {name} from {url} ...")
            ok, detail = await import_one(ep, url)
            print(f"    -> installed={ok} ({detail})")
            ok_all = ok_all and ok
        verified = await verify_installed(ep, script_names)
        print(f"  dashboard verify: {verified}")
        if not (ok_all and verified):
            print(f"  agent-{idx}: FAILED")

    print("\nDONE")


if __name__ == "__main__":
    asyncio.run(main())
