#!/usr/bin/env python3
"""captcha_alert.py — multi-instance doubao captcha watchdog (v2).

Polls EVERY agent Chrome instance's CDP endpoint for a doubao captcha iframe.
When found on agent-N:
  - activates that tab (brings it to front on the agent's noVNC screen)
  - writes /tmp/CAPTCHA_ALERT_<N> (e.g. CAPTCHA_ALERT_1, CAPTCHA_ALERT_2)
  - logs loudly with the noVNC URL to open: http://localhost:608X
When clear, removes the marker for that instance.

Instance discovery (in priority order):
  1. AGENT_POOL_ENDPOINTS env (comma-separated CDP URLs, e.g. http://agent-1:19222,http://agent-2:19222)
  2. CHROME_EXTRA_SINGLE_CDP / CAPTCHA_CDP (single explicit endpoint, legacy)
  3. Default: http://agent-1:19222

noVNC port mapping: port = NOVNC_BASE_PORT + (index-1), index parsed from hostname
(agent-N -> N). If unparsable, defaults to NOVNC_BASE_PORT.

Runs in the API container (has python3 + websockets, can reach agent-N:19222 via
docker network). Started by docker-compose entrypoint (api service).
"""
import asyncio
import json
import os
import re
import time
import urllib.request

import websockets

CHECK_EVERY = float(os.environ.get("CAPTCHA_CHECK_EVERY", "5"))
NOVNC_BASE = int(os.environ.get("NOVNC_BASE_PORT", "6080"))
MARKER_PREFIX = "/tmp/CAPTCHA_ALERT"
# VLM 自动解验证码（默认关闭——本地 7B 推理慢且占 GPU，用户决定不启用；
# 需要时设 CAPTCHA_VLM_AUTO=1 开启）
VLM_AUTO = os.environ.get("CAPTCHA_VLM_AUTO", "0") == "1"
VLM_URL = os.environ.get("OLLAMA_URL", "http://host.docker.internal:11434")
VLM_MODEL = os.environ.get("VLM_MODEL", "qwen2.5vl:7b")

PROBE_JS = """(() => {
  const frames = [...document.querySelectorAll('iframe')]
    .map(f => (f.src || '') + ' ' + (f.srcdoc || ''));
  const bodyAttr = document.body ? document.body.getAttribute('data-captcha-test') || '' : '';
  const all = frames.concat([bodyAttr]);
  return JSON.stringify({
    captcha: all.some(s => s.includes('rmc.bytedance.com') || s.toLowerCase().includes('captcha')),
    frames: frames.length
  });
})()"""


def discover_endpoints() -> list[str]:
    """Return the ordered list of CDP endpoints to watch."""
    pool = os.environ.get("AGENT_POOL_ENDPOINTS", "").strip()
    if pool:
        eps = [e.strip() for e in pool.split(",") if e.strip()]
        if eps:
            return eps
    single = os.environ.get("CAPTCHA_CDP", "").strip()
    if single:
        return [single]
    return ["http://agent-1:19222"]


def endpoint_index(ep: str) -> int:
    """Parse agent-N out of an endpoint URL (http://agent-2:19222 -> 2)."""
    m = re.search(r"agent-(\d+)", ep)
    return int(m.group(1)) if m else 1


def novnc_port_for(ep: str) -> int:
    return NOVNC_BASE + endpoint_index(ep) - 1


def tabs(ep: str):
    with urllib.request.urlopen(f"{ep}/json", timeout=5) as r:
        return json.load(r)


async def probe(ws_url: str) -> dict:
    async with websockets.connect(ws_url, max_size=2 ** 26) as ws:
        await ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                                  "params": {"expression": PROBE_JS, "returnByValue": True}}))
        while True:
            m = json.loads(await ws.recv())
            if m.get("id") == 1:
                v = m.get("result", {}).get("result", {}).get("value", "{}")
                try:
                    return json.loads(v)
                except Exception:
                    return {"captcha": False, "frames": 0}


def activate(ep: str, tab_id: str) -> None:
    try:
        urllib.request.urlopen(f"{ep}/json/activate/{tab_id}", timeout=5)
    except Exception:
        pass


async def check_endpoint(ep: str) -> bool:
    """Return True if a captcha was found on this endpoint's doubao tab."""
    try:
        pages = tabs(ep)
        for p in pages:
            u = p.get("url") or ""
            if "doubao.com" in u or "rmc.bytedance.com" in u:
                try:
                    r = await probe(p["webSocketDebuggerUrl"])
                    if r.get("captcha"):
                        activate(ep, p.get("id"))
                        return True
                except Exception:
                    continue
    except Exception:
        pass
    return False


async def vlm_solve(ep: str) -> bool:
    """用本地 VLM（Ollama）自动解验证码：提取候选图 → 识别 → 拖拽。成功返回 True。"""

    # 1. 找 rmc iframe
    try:
        with urllib.request.urlopen(f"{ep}/json", timeout=5) as r:
            pages = json.loads(r.read())
    except Exception:
        return False
    iframe = None
    for p in pages:
        if p.get("type") == "iframe" and "rmc.bytedance" in (p.get("url") or ""):
            iframe = p
            break
    if not iframe:
        return False

    # 2. 提取提示 + 候选图（canvas → base64）
    expr = r"""
    (() => {
      const out = {prompt: '', images: [], drag_area: null, off: {x: 0, y: 0}};
      try { const r = window.frameElement ? window.frameElement.getBoundingClientRect() : null;
            if (r) out.off = {x: r.x, y: r.y}; } catch(e) {}
      const pel = document.querySelector(
        '.vc-captcha-verify-img-prompt, .tit, [class*="prompt"], [class*="title"]');
      if (pel && pel.innerText) out.prompt = pel.innerText.trim().slice(0, 100);
      const cvs = [...document.querySelectorAll('canvas')];
      for (const cv of cvs) {
        try {
          const r = cv.getBoundingClientRect();
          out.images.push({b64: cv.toDataURL('image/png').split(',')[1],
                           x: r.x, y: r.y, w: r.width, h: r.height});
        } catch(e) {}
      }
      const da = document.querySelector('.drag-area, .img-container, [class*="drop"]');
      if (da) { const r = da.getBoundingClientRect();
                out.drag_area = {x: r.x, y: r.y, w: r.width, h: r.height}; }
      return JSON.stringify(out);
    })()
    """
    ws_url = iframe["webSocketDebuggerUrl"]
    async with websockets.connect(ws_url, max_size=128 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                                  "params": {"expression": expr, "returnByValue": True}}))
        while True:
            m = json.loads(await ws.recv())
            if m.get("id") == 1:
                raw = m.get("result", {}).get("result", {}).get("value")
                break
    try:
        data = json.loads(raw)
    except Exception:
        return False
    prompt_text, images = data.get("prompt", ""), data.get("images", [])
    if not prompt_text or not images:
        return False

    # 3. 调 Ollama VLM
    n = len(images)
    user_content = (
        f"验证码提示：'{prompt_text}'\n下面有 {n} 张候选图（编号1~{n}）。"
        f"选出所有符合描述的图，只回复编号，格式如：[1,3]。"
    )
    body = {
        "model": VLM_MODEL,
        "messages": [{"role": "user", "content": user_content,
                      "images": [im["b64"] for im in images]}],
        "stream": False,
        "options": {"temperature": 0.1},
    }
    req = urllib.request.Request(
        f"{VLM_URL}/api/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            resp = json.loads(r.read()).get("message", {}).get("content", "")
    except Exception:
        return False
    # 解析 1-indexed 编号
    m = re.search(r"\[([\d,\s]+)\]", resp)
    if m:
        nums = [int(x) for x in re.findall(r"\d+", m.group(1))]
    else:
        nums = [int(x) for x in re.findall(r"\d+", resp)]
    selected = [i - 1 for i in nums if 0 <= i - 1 < n]
    if not selected:
        return False

    # 4. 拖拽/点击选中图（坐标 + iframe offset）
    ox, oy = data.get("off", {}).get("x", 0), data.get("off", {}).get("y", 0)
    async with websockets.connect(ws_url, max_size=128 * 1024 * 1024) as ws:
        mid = 0

        async def send(method, params):
            nonlocal mid
            mid += 1
            await ws.send(json.dumps({"id": mid, "method": method, "params": params}))
            while True:
                mm = json.loads(await ws.recv())
                if mm.get("id") == mid:
                    return mm

        if data.get("drag_area"):
            da = data["drag_area"]
            tx, ty = da["x"] + da["w"] / 2 + ox, da["y"] + da["h"] / 2 + oy
            for i in selected:
                im = images[i]
                sx, sy = im["x"] + im["w"] / 2 + ox, im["y"] + im["h"] / 2 + oy
                # 人类轨迹拖拽
                await send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": sx, "y": sy,
                                                        "button": "left", "clickCount": 1})
                steps = 20
                for s in range(1, steps + 1):
                    t = s / steps
                    eased = t * t * (3 - 2 * t)
                    cx = sx + (tx - sx) * eased
                    cy = sy + (ty - sy) * eased
                    await send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": cx, "y": cy,
                                                            "button": "left", "buttons": 1})
                    await asyncio.sleep(0.015)
                await send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": tx, "y": ty,
                                                        "button": "left", "clickCount": 1})
                await asyncio.sleep(0.4)
        else:
            for i in selected:
                im = images[i]
                cx, cy = im["x"] + im["w"] / 2 + ox, im["y"] + im["h"] / 2 + oy
                await send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": cx, "y": cy,
                                                        "button": "left", "clickCount": 1})
                await send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": cx, "y": cy,
                                                        "button": "left", "clickCount": 1})
                await asyncio.sleep(0.3)
    return True


async def loop() -> None:
    eps = discover_endpoints()
    print(
        f"[captcha-alert] starting; watching {len(eps)} endpoint(s): "
        f"{', '.join(eps)}",
        flush=True,
    )
    alerted: dict[str, bool] = {ep: False for ep in eps}
    while True:
        # re-discover periodically so new agents added via chrome-instances are picked up
        eps = discover_endpoints()
        for ep in alerted:
            if ep not in eps:
                del alerted[ep]
        for ep in eps:
            if ep not in alerted:
                alerted[ep] = False
            try:
                found = await check_endpoint(ep)
            except Exception:
                found = False
            idx = endpoint_index(ep)
            marker = f"{MARKER_PREFIX}_{idx}"
            if found and not alerted[ep]:
                port = novnc_port_for(ep)
                # VLM 自动解：先尝试本地视觉模型，成功则不打扰人工
                solved = False
                if VLM_AUTO:
                    try:
                        solved = await vlm_solve(ep)
                    except Exception as e:
                        print(
                            f"[captcha-alert] VLM attempt failed on {ep}: {str(e)[:100]}",
                            flush=True,
                        )
                if solved:
                    print(
                        f"[captcha-alert] {time.strftime('%H:%M:%S')} "
                        f"VLM auto-solved captcha on {ep} (agent-{idx})",
                        flush=True,
                    )
                    # 暂不写 marker（给 VLM 一点时间让验证码消失，下轮确认）
                    continue
                print(
                    f"[captcha-alert] {time.strftime('%H:%M:%S')} CAPTCHA on "
                    f"{ep} (agent-{idx}) — open http://localhost:{port} to solve",
                    flush=True,
                )
                try:
                    open(marker, "w").write("captcha")
                except OSError:
                    pass
                alerted[ep] = True
            elif not found and alerted[ep]:
                print(
                    f"[captcha-alert] {time.strftime('%H:%M:%S')} captcha "
                    f"cleared on {ep} (agent-{idx})",
                    flush=True,
                )
                try:
                    os.remove(marker)
                except FileNotFoundError:
                    pass
                alerted[ep] = False
        await asyncio.sleep(CHECK_EVERY)


if __name__ == "__main__":
    try:
        asyncio.run(loop())
    except KeyboardInterrupt:
        pass
