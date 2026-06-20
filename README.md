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
http://127.0.0.1:10000
```

## 配置

如需切换原服务地址，只设置一个变量：

```bash
export WAITCHECK_API_BASE_URL=https://your-original-cs-bot.example.com
```

新服务会调用：

- `GET /tool/wait_check`：从原服务抽取快捷关键词
- `GET /api/wait_check_stream?keyword=...`：转发闭环检测流式结果
