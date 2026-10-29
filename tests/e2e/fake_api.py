"""A local HTTP server that imitates the Anthropic Messages API with scripted replies.

Claude Code is pointed at it with ``ANTHROPIC_BASE_URL``. Every request is recorded. A request belongs to a
conversation when its first user message contains a marker ``E2E-<NAME>`` (the prompt of ``claude -p`` or the
prompt the main conversation passes to a subagent); the reply is the step of the script for that marker whose
index is the number of assistant messages already in the conversation. Past the end of a script, or for
requests without a marker (titles, summaries), the reply is a plain ``ok`` text.

Standard library only; runs on Python 3.9+. No network access beyond 127.0.0.1.
"""

from __future__ import annotations

import http.server
import json
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Union

MARKER = re.compile(r"E2E-[A-Z0-9-]+")


@dataclass
class Error:
    """Answer the request with an HTTP error instead of a message."""

    status: int
    kind: str = "invalid_request_error"
    message: str = "scripted error"


# A step is a list of content blocks (text or tool_use), an Error, or a callable that builds one of them
# from the request body.
Step = Union[list[dict[str, Any]], Error, Callable[[dict[str, Any]], Union[list[dict[str, Any]], Error]]]


def text(value: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": value}]


def tool(name: str, tool_input: dict[str, Any]) -> list[dict[str, Any]]:
    """A tool_use block; its id is filled in per reply (Claude Code needs every id to be unique)."""
    return [{"type": "tool_use", "id": "", "name": name, "input": tool_input}]


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if isinstance(block.get("text"), str):
                    parts.append(block["text"])
                elif block.get("type") == "tool_result":
                    parts.append(_text_of(block.get("content")))
        return "\n".join(parts)
    return ""


def marker_of(body: dict[str, Any]) -> str | None:
    for message in body.get("messages", []):
        if message.get("role") == "user":
            found = MARKER.search(_text_of(message.get("content")))
            return found.group(0) if found else None
    return None


def tool_results(body: dict[str, Any]) -> list[dict[str, Any]]:
    """Every tool_result block of the conversation in ``body``, oldest first."""
    out = []
    for message in body.get("messages", []):
        content = message.get("content")
        if isinstance(content, list):
            out += [b for b in content if isinstance(b, dict) and b.get("type") == "tool_result"]
    return out


def result_text(block: dict[str, Any]) -> str:
    return _text_of(block.get("content"))


@dataclass
class Recorded:
    path: str
    body: dict[str, Any]
    marker: str | None
    turn: int


@dataclass
class FakeMessagesAPI:
    scripts: dict[str, list[Step]] = field(default_factory=dict)
    requests: list[Recorded] = field(default_factory=list)
    _server: http.server.ThreadingHTTPServer | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _counter: int = 0

    @property
    def url(self) -> str:
        assert self._server is not None
        host, port = self._server.server_address[:2]
        return f"http://{host!s}:{port}"

    def start(self) -> FakeMessagesAPI:
        api = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                pass

            def do_GET(self) -> None:
                self._send(404, {"type": "error", "error": {"type": "not_found_error", "message": "e2e"}})

            def do_POST(self) -> None:
                length = int(self.headers.get("content-length") or 0)
                try:
                    body = json.loads(self.rfile.read(length) or b"{}")
                except ValueError:
                    body = {}
                if not isinstance(body, dict):
                    body = {}
                if "count_tokens" in self.path:
                    self._send(200, {"input_tokens": 10})
                    return
                marker = marker_of(body)
                turn = sum(1 for m in body.get("messages", []) if m.get("role") == "assistant")
                with api._lock:
                    api.requests.append(Recorded(self.path, body, marker, turn))
                    script = api.scripts.get(marker or "", [])
                    api._counter += 1
                    serial = api._counter
                step: Step = script[turn] if turn < len(script) else text("ok")
                reply = step(body) if callable(step) else step
                if isinstance(reply, Error):
                    self._send(reply.status, {"type": "error", "error": {"type": reply.kind, "message": reply.message}})
                    return
                # Claude Code merges assistant messages that share an id, so every reply gets its own ids.
                reply = [
                    {**b, "id": f"toolu_e2e_{serial}_{i}"} if b.get("type") == "tool_use" else b
                    for i, b in enumerate(reply)
                ]
                self._message(body, reply, f"msg_e2e_{serial}")

            def _send(self, status: int, payload: dict[str, Any]) -> None:
                data = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _message(self, body: dict[str, Any], content: list[dict[str, Any]], message_id: str) -> None:
                stop = "tool_use" if any(b.get("type") == "tool_use" for b in content) else "end_turn"
                usage = {"input_tokens": 10, "output_tokens": 5}
                message = {
                    "id": message_id,
                    "type": "message",
                    "role": "assistant",
                    "model": body.get("model", "claude-e2e"),
                    "content": content,
                    "stop_reason": stop,
                    "stop_sequence": None,
                    "usage": usage,
                }
                if not body.get("stream"):
                    self._send(200, message)
                    return
                self.send_response(200)
                self.send_header("content-type", "text/event-stream")
                self.end_headers()

                def event(name: str, data: dict[str, Any]) -> None:
                    self.wfile.write(f"event: {name}\ndata: {json.dumps({'type': name, **data})}\n\n".encode())

                event("message_start", {"message": {**message, "content": [], "stop_reason": None}})
                for index, block in enumerate(content):
                    if block["type"] == "text":
                        event("content_block_start", {"index": index, "content_block": {"type": "text", "text": ""}})
                        delta = {"type": "text_delta", "text": block["text"]}
                    else:
                        event("content_block_start", {"index": index, "content_block": {**block, "input": {}}})
                        delta = {"type": "input_json_delta", "partial_json": json.dumps(block["input"])}
                    event("content_block_delta", {"index": index, "delta": delta})
                    event("content_block_stop", {"index": index})
                event("message_delta", {"delta": {"stop_reason": stop, "stop_sequence": None}, "usage": usage})
                event("message_stop", {})

        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()

    def conversation(self, marker: str) -> list[Recorded]:
        with self._lock:
            return [r for r in self.requests if r.marker == marker]

    def raw_bodies(self) -> str:
        with self._lock:
            return "\n".join(json.dumps(r.body) for r in self.requests)
