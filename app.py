import os
import re
import hmac
import secrets
from urllib.parse import quote, urljoin

import requests
from flask import Flask, Response, jsonify, redirect, render_template, render_template_string, request, session, stream_with_context


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
WAITCHECK_USERNAME = (os.environ.get("WAITCHECK_USERNAME") or "waitcheck").strip()
WAITCHECK_PASSWORD = os.environ.get("WAITCHECK_PASSWORD") or ""

app = Flask(__name__)
app.secret_key = (
    os.environ.get("WAITCHECK_SESSION_SECRET")
    or os.environ.get("SECRET_KEY")
    or os.environ.get("ZD_SESSION_SECRET")
    or secrets.token_hex(32)
)

LOGIN_HTML = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>登录</title>
  <style>
    *{box-sizing:border-box}
    body{margin:0;min-height:100vh;display:grid;place-items:center;background:#f3f5f7;color:#111827;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;padding:20px}
    .card{width:100%;max-width:360px;background:#fff;border:1px solid #d9dee7;border-radius:8px;padding:22px;box-shadow:0 12px 32px rgba(15,23,42,.08)}
    h1{font-size:20px;margin:0 0 6px;font-weight:800}
    .sub{font-size:13px;color:#667085;margin-bottom:18px;line-height:1.5}
    label{display:block;font-size:12px;color:#344054;font-weight:750;margin:12px 0 6px}
    input{width:100%;border:1px solid #cfd6e1;border-radius:6px;padding:10px 11px;font-size:14px;outline:none}
    input:focus{border-color:#155eef;box-shadow:0 0 0 3px rgba(21,94,239,.12)}
    button{width:100%;border:0;background:#155eef;color:#fff;border-radius:6px;padding:11px 13px;font-size:14px;font-weight:800;cursor:pointer;margin-top:16px}
    .error{background:#fff1f0;color:#b42318;border:1px solid #fecdca;border-radius:6px;padding:9px 10px;font-size:13px;margin-bottom:12px}
  </style>
</head>
<body>
  <form class="card" method="post" autocomplete="off">
    <h1>登录</h1>
    {% if error %}<div class="error">{{ error }}</div>{% endif %}
    <input type="hidden" name="next" value="{{ next_url }}">
    <label>用户名</label>
    <input name="username" value="{{ username }}" autofocus>
    <label>密码</label>
    <input name="password" type="password" autocomplete="current-password">
    <button type="submit">登录</button>
  </form>
</body>
</html>
"""


def upstream_url(path):
    return urljoin(f"{UPSTREAM_BASE_URL}/", path.lstrip("/"))


def waitcheck_auth_is_configured():
    return bool(WAITCHECK_USERNAME and WAITCHECK_PASSWORD)


def is_waitcheck_logged_in():
    return bool(session.get("waitcheck_authenticated"))


def login_redirect_url():
    next_url = request.path or "/"
    if request.query_string:
        next_url = f"{next_url}?{request.query_string.decode('utf-8', 'ignore')}"
    return "/login?next=" + quote(next_url, safe="")


@app.before_request
def require_waitcheck_login():
    if request.path in ("/login", "/healthz"):
        return None
    if is_waitcheck_logged_in():
        return None
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "请先登录", "login_required": True}), 401
    return redirect(login_redirect_url())


@app.route("/login", methods=["GET", "POST"])
def login_page():
    next_url = request.values.get("next") or "/"
    if not str(next_url).startswith("/"):
        next_url = "/"
    username = WAITCHECK_USERNAME
    error = ""
    if request.method == "POST":
        username = str(request.form.get("username") or "")
        password = str(request.form.get("password") or "")
        if not waitcheck_auth_is_configured():
            error = "服务未配置 WAITCHECK_PASSWORD，暂时无法登录。"
        elif hmac.compare_digest(username, WAITCHECK_USERNAME) and hmac.compare_digest(password, WAITCHECK_PASSWORD):
            session["waitcheck_authenticated"] = True
            session["waitcheck_username"] = username
            return redirect(next_url)
        else:
            error = "用户名或密码错误"
    return render_template_string(LOGIN_HTML, error=error, username=username, next_url=next_url)


@app.route("/logout")
def logout_page():
    session.pop("waitcheck_authenticated", None)
    session.pop("waitcheck_username", None)
    return redirect("/login")


@app.route("/healthz")
def healthz():
    return jsonify({"ok": True})


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
        "waitcheck_auth_configured": waitcheck_auth_is_configured(),
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
