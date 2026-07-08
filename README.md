# Waitcheck Standalone

独立版 Waitcheck 页面，只做 UI 和接口转发，不连接 Telegram，也不维护客服群、Session、关键词等原始配置。

默认调用原 `cs-bot` 服务：

```text
https://yyhelp.zeabur.app
```

## 本地运行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

打开：

```text
http://127.0.0.1:8080
```

## 配置

独立 Waitcheck 自己的页面访问密码：

```bash
export WAITCHECK_USERNAME=waitcheck
export WAITCHECK_PASSWORD=你的独立Waitcheck密码
export WAITCHECK_SESSION_SECRET=随机长字符串
```

`WAITCHECK_SESSION_SECRET` 用来签登录 Cookie；不配置也能运行，但服务重启后需要重新登录。

如需切换原服务地址，设置：

```bash
export WAITCHECK_API_BASE_URL=https://your-original-cs-bot.example.com
```

原 `cs-bot` 已启用 ZD 登录保护时，standalone 后端也要配置上游 ZD 登录账号密码，才能代理受保护接口：

```bash
export WAITCHECK_UPSTREAM_USERNAME=changshan
export WAITCHECK_UPSTREAM_PASSWORD=你的ZD登录密码
```

这组是原 `cs-bot` 的 ZD 账号密码，不是独立 Waitcheck 的页面密码。

也可以直接使用同名 ZD 变量：

```bash
export ZD_ADMIN_USERNAME=changshan
export ZD_ADMIN_PASSWORD=你的ZD登录密码
```

新服务会调用：

- `GET /tool/wait_check`：从原服务抽取快捷关键词
- `GET /api/wait_check_stream?keyword=...`：转发闭环检测流式结果
