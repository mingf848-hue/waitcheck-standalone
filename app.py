import os
import re
from urllib.parse import urljoin

import requests
from flask import Flask, Response, jsonify, render_template, request, stream_with_context


DEFAULT_UPSTREAM_BASE_URL = "https://yyhelp.zeabur.app"
UPSTREAM_BASE_URL = (os.environ.get("WAITCHECK_API_BASE_URL") or DEFAULT_UPSTREAM_BASE_URL).strip().rstrip("/")
REQUEST_TIMEOUT = int(os.environ.get("WAITCHECK_REQUEST_TIMEOUT", "30") or "30")
UPSTREAM_USERNAME = (
    os.environ.get("WAITCHECK_UPSTREAM_USERNAME")
    or os.environ.get("ZD_ADMIN_USERNAME")
    or "changshan"
).strip()
UPSTREAM_PASSWORD = (
    os.environ.get("WAITCHECK_UPSTREAM_PASSWORD")
    or os.environ.get("ZD_ADMIN_PASSWORD")
    or ""
)

app = Flask(__name__)


def upstream_url(path):
    return urljoin(f"{UPSTREAM_BASE_URL}/", path.lstrip("/"))


def upstream_auth_is_configured():
    return bool(UPSTREAM_USERNAME and UPSTREAM_PASSWORD)


def upstream_requires_login(response):
    if response.status_code in (401, 403):
        return True
    if response.status_code in (301, 302, 303, 307, 308):
        location = response.headers.get("location", "")
        return "/zd/login" in location
    return False


def login_upstream(session):
    if not upstream_auth_is_configured():
        raise RuntimeError(
            "上游 yyhelp 已启用登录保护，请配置 WAITCHECK_UPSTREAM_PASSWORD 或 ZD_ADMIN_PASSWORD"
        )
    response = session.post(
        upstream_url("/api/zd_auth/login"),
        json={"username": UPSTREAM_USERNAME, "password": UPSTREAM_PASSWORD},
        timeout=REQUEST_TIMEOUT,
        allow_redirects=False,
    )
    if response.status_code != 200:
        raise RuntimeError(f"上游登录失败，状态码 {response.status_code}")
    data = response.json()
    if data.get("code") not in (0, "0", None):
        raise RuntimeError(data.get("message") or "上游登录失败")


def fetch_upstream(path, **kwargs):
    session = requests.Session()
    try:
        response = session.get(
            upstream_url(path),
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
            **kwargs,
        )
        if upstream_requires_login(response):
            response.close()
            login_upstream(session)
            response = session.get(
                upstream_url(path),
                timeout=REQUEST_TIMEOUT,
                allow_redirects=False,
                **kwargs,
            )
        return response
    finally:
        session.close()


def open_upstream_stream(path, **kwargs):
    session = requests.Session()
    response = session.get(
        upstream_url(path),
        stream=True,
        timeout=(10, None),
        allow_redirects=False,
        **kwargs,
    )
    if upstream_requires_login(response):
        response.close()
        login_upstream(session)
        response = session.get(
            upstream_url(path),
            stream=True,
            timeout=(10, None),
            allow_redirects=False,
            **kwargs,
        )
    return session, response


def extract_keywords(html):
    keywords = []
    for keyword in re.findall(r"fillKeyword\('([^']+)'\)", html or ""):
        if keyword not in keywords:
            keywords.append(keyword)
    return keywords


@app.route("/")
@app.route("/tool/wait_check")
def wait_check_ui():
    try:
        response = fetch_upstream("/tool/wait_check")
        response.raise_for_status()
        proxied = Response(response.text, mimetype="text/html; charset=utf-8")
        proxied.headers["Cache-Control"] = "no-cache"
        return proxied
    except Exception:
        app.logger.exception("Failed to load upstream Waitcheck page")
        return render_template("waitcheck.html")


@app.route("/api/config")
def api_config():
    return jsonify({
        "ok": True,
        "upstream_base_url": UPSTREAM_BASE_URL,
        "upstream_auth_configured": upstream_auth_is_configured(),
    })


@app.route("/api/keywords")
def api_keywords():
    fallback = ["早班全体", "中班全体", "晚班全体", "同意遗漏"]
    try:
        response = fetch_upstream("/tool/wait_check")
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
        session = None
        response = None
        try:
            session, response = open_upstream_stream(
                "/api/wait_check_stream",
                params={"keyword": keyword},
            )
            if response.status_code != 200:
                yield response.text or f'{{"type":"progress","percent":0,"msg":"原接口返回 {response.status_code}"}}\n'
                return
            for chunk in response.iter_content(chunk_size=None):
                if chunk:
                    yield chunk
        except Exception as exc:
            yield f'{{"type":"progress","percent":0,"msg":"原接口连接失败: {str(exc)}"}}\n'
        finally:
            if response is not None:
                response.close()
            if session is not None:
                session.close()

    proxied = Response(stream_with_context(generate()), mimetype="text/plain; charset=utf-8")
    proxied.headers["X-Accel-Buffering"] = "no"
    proxied.headers["Cache-Control"] = "no-cache"
    proxied.headers["Access-Control-Allow-Origin"] = "*"
    return proxied


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080") or "8080")
    app.run(host="0.0.0.0", port=port, threaded=True)
