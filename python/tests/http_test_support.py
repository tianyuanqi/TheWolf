"""共享合成ASGI测试工具；不读历史附件或真实金融数据。"""
import asyncio
import hashlib
import json
from pmi.api import create_app
from pmi.service_config import ServiceConfig

def disk(root):
    """只比较合成根的内容、大小、模式、mtime；不声称OS全写观测。"""
    return {str(p.relative_to(root)): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_size,
                                    p.stat().st_mode, p.stat().st_mtime_ns)
            for p in root.rglob("*") if p.is_file()}


class Reply:
    def __init__(self, messages):
        start = next(m for m in messages if m["type"] == "http.response.start")
        self.status = start["status"]
        self.headers = {k.decode().lower(): v.decode() for k, v in start["headers"]}
        self.body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")

    def json(self):
        return json.loads(self.body)


class ReadClient:
    """直接ASGI消费者，显式携带真实装配上下文；不补齐负例请求。"""
    def __init__(self, root):
        self.config = ServiceConfig(root, 18080, ("http://127.0.0.1:18081",))
        self.app = create_app(self.config)
        self.headers = {"host": "127.0.0.1:18080", "origin": "http://127.0.0.1:18081", "x-wolf-client": "1",
                        "x-wolf-expected-instance": self.app.state.boundary.instance,
                        "x-wolf-expected-config": self.config.config_id, "x-wolf-request-id": "synthetic-read-test"}

    def request(self, path, method="GET", *, headers=None, body=b"", replace_headers=False):
        selected = [] if replace_headers else list(self.headers.items())
        if isinstance(headers, dict):
            selected = [(k, v) for k, v in selected if k.lower() not in {n.lower() for n in headers}]
            selected.extend(headers.items())
        elif headers:
            selected.extend(headers)
        return asyncio.run(self._send(path, method, selected, body))

    async def _send(self, url, method, headers, body):
        path, _, query = url.partition("?")
        messages = []
        scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"}, "http_version": "1.1",
                 "method": method, "scheme": "http", "path": path, "raw_path": path.encode(),
                 "query_string": query.encode(), "root_path": "", "client": ("127.0.0.1", 50000),
                 "server": ("127.0.0.1", 18080), "headers": [(k.lower().encode(), v.encode()) for k, v in headers]}
        sent = False
        async def receive():
            nonlocal sent
            if sent:
                await asyncio.Event().wait()
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        async def send(message):
            messages.append(message)
        await self.app(scope, receive, send)
        return Reply(messages)

import http.client
http_receipts = None
import socket
def port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def request(number, path, method='GET', headers=None):
    """保存本次合成请求的状态及未折叠响应头，断言失败也可定位。"""
    client = http.client.HTTPConnection('127.0.0.1', number, timeout=2)
    try:
        client.request(method, path, headers=headers or {})
        response = client.getresponse()
        raw_headers = response.getheaders()
        body = response.read()
        if http_receipts is not None:
            record = {'port': number, 'path': path, 'method': method,
                      'request_headers': headers or {}, 'status': response.status,
                      'reason': response.reason, 'http_version': response.version,
                      'raw_headers': raw_headers, 'body_bytes': len(body),
                      'body_sha256': hashlib.sha256(body).hexdigest()}
            with http_receipts.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(record) + '\n')
        return response.status, dict(raw_headers), body
    finally:
        client.close()


