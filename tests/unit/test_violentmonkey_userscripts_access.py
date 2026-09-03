import asyncio
import json
import re
from pathlib import Path

import websockets
from websockets.datastructures import Headers
from websockets.http11 import Response

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "ensure-violentmonkey-userscripts-access.mjs"
EXTENSION_ID = "abcdefghijklmnopabcdefghijklmnop"


class FakeChromiumCdp:
    def __init__(
        self,
        *,
        access_enabled: bool,
        access_active: bool,
        update_succeeds: bool = True,
        probe_executes: bool = True,
    ):
        self.access_enabled = access_enabled
        self.access_active = access_active
        self.update_succeeds = update_succeeds
        self.probe_executes = probe_executes
        self.update_attempts = 0
        self.probe_marker = None
        self.probe_url = None
        self.cleanup_commands = []
        self.targets = {
            "violentmonkey-worker": {
                "id": "violentmonkey-worker",
                "type": "service_worker",
                "url": f"chrome-extension://{EXTENSION_ID}/sw.js",
                "webSocketDebuggerUrl": "",
            }
        }

    async def __aenter__(self):
        self.server = await websockets.serve(
            self.handle_websocket,
            "127.0.0.1",
            0,
            process_request=self.handle_http,
        )
        self.port = self.server.sockets[0].getsockname()[1]
        self.targets["violentmonkey-worker"]["webSocketDebuggerUrl"] = self.websocket_url(
            "violentmonkey-worker"
        )
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        self.server.close()
        await self.server.wait_closed()

    @property
    def endpoint(self):
        return f"http://127.0.0.1:{self.port}"

    def websocket_url(self, target_id):
        if target_id == "browser":
            return f"ws://127.0.0.1:{self.port}/devtools/browser"
        return f"ws://127.0.0.1:{self.port}/devtools/page/{target_id}"

    def cdp_targets(self):
        return list(self.targets.values())

    async def handle_http(self, connection, request):
        if request.path == "/json/version":
            payload = {"webSocketDebuggerUrl": self.websocket_url("browser")}
        elif request.path == "/json/list":
            payload = self.cdp_targets()
        else:
            return None
        body = json.dumps(payload).encode()
        return Response(
            200,
            "OK",
            Headers(
                [
                    ("Content-Type", "application/json"),
                    ("Content-Length", str(len(body))),
                ]
            ),
            body,
        )

    def response(self, message_id, value=None):
        result = {"type": "undefined"}
        if value is not None:
            result = {"type": "object", "value": value}
        return {"id": message_id, "result": {"result": result}}

    @staticmethod
    def cdp_response(message_id, result):
        return {"id": message_id, "result": result}

    def exception(self, message_id, text):
        return {"id": message_id, "result": {"exceptionDetails": {"text": text}}}

    def create_target(self, url):
        if url == "chrome://extensions/":
            target_id = "extensions"
        elif url.startswith(f"chrome-extension://{EXTENSION_ID}/options/"):
            target_id = "options"
        elif url == f"{self.endpoint}/json/version":
            target_id = "probe"
            self.probe_url = url
        else:
            raise AssertionError(f"unexpected target URL: {url}")
        self.targets[target_id] = {
            "id": target_id,
            "type": "page",
            "url": url,
            "webSocketDebuggerUrl": self.websocket_url(target_id),
        }
        return target_id

    async def handle_websocket(self, connection):
        path = connection.request.path
        async for raw_message in connection:
            message = json.loads(raw_message)
            message_id = message["id"]
            method = message["method"]
            if method == "Target.createTarget":
                result = self.cdp_response(
                    message_id, {"targetId": self.create_target(message["params"]["url"])}
                )
            elif method == "Target.closeTarget":
                self.targets.pop(message["params"]["targetId"], None)
                result = self.cdp_response(message_id, {"success": True})
            elif method != "Runtime.evaluate":
                result = self.exception(message_id, f"unexpected CDP method: {method}")
            else:
                result = self.evaluate(path, message_id, message["params"]["expression"])
            await connection.send(json.dumps(result))

    def evaluate(self, path, message_id, expression):
        if path.endswith("violentmonkey-worker"):
            return self.response(
                message_id,
                {"id": EXTENSION_ID, "name": "Violentmonkey", "version": "2.48.0"},
            )
        if path.endswith("extensions"):
            if not self.access_active:
                self.update_attempts += 1
                if self.update_succeeds and self.access_enabled:
                    self.access_active = True
            if not self.access_active:
                return self.exception(message_id, "Violentmonkey userScriptsAccess is not active")
            return self.response(
                message_id,
                {"isEnabled": self.access_enabled, "isActive": self.access_active},
            )
        if path.endswith("options"):
            if "typeof globalThis.chrome?.runtime?.sendMessage" in expression:
                return self.response(message_id, "function")
            if '"ParseScript"' in expression:
                self.probe_marker = re.search(r"novnc-vm-[0-9a-f-]{36}", expression).group(0)
                return self.response(message_id, {"where": {"id": 1}})
            if '"UpdateScriptInfo"' in expression:
                self.cleanup_commands.append("UpdateScriptInfo")
                return self.response(message_id)
            if '"RemoveScripts"' in expression:
                self.cleanup_commands.append("RemoveScripts")
                return self.response(message_id)
        if path.endswith("probe"):
            marker = self.probe_marker if self.probe_executes else None
            return self.response(message_id, marker)
        return self.exception(message_id, f"unexpected evaluation target: {path}")


async def run_checker(cdp):
    process = await asyncio.create_subprocess_exec(
        "node",
        str(CHECKER),
        cdp.endpoint,
        "2.48.0",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return process.returncode, json.loads(stdout or b"{}"), stderr.decode()


def test_new_profile_enables_userscripts_access_and_executes_a_real_probe():
    async def scenario():
        async with FakeChromiumCdp(access_enabled=True, access_active=False) as cdp:
            returncode, report, stderr = await run_checker(cdp)
            assert returncode == 0, stderr
            assert report["ok"] is True
            assert report["extension"] == {"id": EXTENSION_ID, "version": "2.48.0"}
            assert report["userScriptsAccess"] == {"isEnabled": True, "isActive": True}
            assert report["probe"] == {"executed": True}
            assert cdp.update_attempts == 1
            assert cdp.cleanup_commands == ["UpdateScriptInfo", "RemoveScripts"]
            assert cdp.probe_url == f"{cdp.endpoint}/json/version"

    asyncio.run(scenario())


def test_existing_userscripts_access_is_checked_without_reconfiguring_it():
    async def scenario():
        async with FakeChromiumCdp(access_enabled=True, access_active=True) as cdp:
            returncode, report, stderr = await run_checker(cdp)
            assert returncode == 0, stderr
            assert report["ok"] is True
            assert cdp.update_attempts == 0
            assert cdp.cleanup_commands == ["UpdateScriptInfo", "RemoveScripts"]

    asyncio.run(scenario())


def test_inactive_userscripts_access_fails_closed_before_a_probe_script_is_installed():
    async def scenario():
        async with FakeChromiumCdp(
            access_enabled=True, access_active=False, update_succeeds=False
        ) as cdp:
            returncode, report, stderr = await run_checker(cdp)
            assert returncode == 1
            assert report == {}
            assert "userScriptsAccess is not active" in stderr
            assert cdp.update_attempts == 1
            assert cdp.probe_marker is None
            assert cdp.cleanup_commands == []

    asyncio.run(scenario())
