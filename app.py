import os
import re
from urllib.parse import urljoin

import requests
from flask import Flask, Response, jsonify, render_template, request, stream_with_context


DEFAULT_UPSTREAM_BASE_URL = "https://yyhelp.zeabur.app"
UPSTREAM_BASE_URL = (os.environ.get("WAITCHECK_API_BASE_URL") or DEFAULT_UPSTREAM_BASE_URL).strip().rstrip("/")
REQUEST_TIMEOUT = int(os.environ.get("WAITCHECK_REQUEST_TIMEOUT", "30") or "30")

app = Flask(__name__)


def upstream_url(path):
    return urljoin(f"{UPSTREAM_BASE_URL}/", path.lstrip("/"))


def extract_keywords(html):
    keywords = []
    for keyword in re.findall(r"fillKeyword\('([^']+)'\)", html or ""):
        if keyword not in keywords:
            keywords.append(keyword)
    return keywords


@app.route("/")
@app.route("/tool/wait_check")
def wait_check_ui():
    return render_template("waitcheck.html", upstream_base_url=UPSTREAM_BASE_URL)


@app.route("/api/config")
def api_config():
    return jsonify({"ok": True, "upstream_base_url": UPSTREAM_BASE_URL})


@app.route("/api/keywords")
def api_keywords():
    fallback = ["早班全体", "中班全体", "晚班全体", "同意遗漏"]
    try:
        response = requests.get(upstream_url("/tool/wait_check"), timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        keywords = extract_keywords(response.text)
        return jsonify({"ok": True, "keywords": keywords or fallback, "source": "upstream"})
    except Exception as exc:
        return jsonify({"ok": False, "keywords": fallback, "source": "fallback", "error": str(exc)}), 200


@app.route("/api/wait_check_stream")
def api_wait_check_stream():
    keyword = (request.args.get("keyword") or "").strip()
    if not keyword:
        return jsonify({"ok": False, "error": "Keyword required"}), 400

    def generate():
        try:
            with requests.get(
                upstream_url("/api/wait_check_stream"),
                params={"keyword": keyword},
                stream=True,
                timeout=(10, None),
            ) as response:
                if response.status_code != 200:
                    yield response.text or f'{{"type":"progress","percent":0,"msg":"原接口返回 {response.status_code}"}}\n'
                    return
                for chunk in response.iter_content(chunk_size=None):
                    if chunk:
                        yield chunk
        except Exception as exc:
            yield f'{{"type":"progress","percent":0,"msg":"原接口连接失败: {str(exc)}"}}\n'

    proxied = Response(stream_with_context(generate()), mimetype="text/plain; charset=utf-8")
    proxied.headers["X-Accel-Buffering"] = "no"
    proxied.headers["Cache-Control"] = "no-cache"
    proxied.headers["Access-Control-Allow-Origin"] = "*"
    return proxied


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080") or "8080")
    app.run(host="0.0.0.0", port=port, threaded=True)
