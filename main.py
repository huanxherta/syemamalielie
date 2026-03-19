import json
import os
from datetime import datetime
from aiohttp import web
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.event.filter import EventMessageType
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig


@register(
    "astrbot_plugin_profanity_monitor",
    "huanxherta",
    "使用LLM智能识别群聊中的脏话，数据持久化并提供HTTP API查询。",
    "1.0.0",
)
class ProfanityMonitor(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.data_dir = os.path.join("data", "profanity_monitor")
        self.data_file = os.path.join(self.data_dir, "records.json")
        self.records = []
        self.http_runner = None
        self.http_site = None
        self.provider_id = config.get("provider_id", "")
        self.enable_groups = config.get("enable_groups", [])
        self.ignore_groups = config.get("ignore_groups", [])
        self.enable_http = config.get("enable_http_api", False)
        self.host = config.get("http_host", "0.0.0.0")
        self.port = config.get("http_port", 10050)
        self.admin_password = config.get("admin_password", "m1234")

    async def initialize(self):
        os.makedirs(self.data_dir, exist_ok=True)
        self._load_records()
        if self.enable_http:
            await self._start_http_server()
        else:
            logger.info("HTTP API 未启用，可在插件配置中开启")

    def _load_records(self):
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    self.records = json.load(f)
            except Exception as e:
                logger.error(f"加载数据失败: {e}")
                self.records = []
        else:
            self.records = []

    def _save_records(self):
        try:
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(self.records, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存数据失败: {e}")

    async def _start_http_server(self):
        app = web.Application()
        app.router.add_get("/", self._handle_index)
        app.router.add_get("/records", self._handle_get_records)
        app.router.add_get("/stats", self._handle_get_stats)
        app.router.add_post("/clear", self._handle_clear_records)
        self.http_runner = web.AppRunner(app)
        await self.http_runner.setup()
        try:
            self.http_site = web.TCPSite(self.http_runner, self.host, self.port)
            await self.http_site.start()
            logger.info(f"HTTP API 已启动: http://{self.host}:{self.port}")
        except OSError as e:
            if e.errno == 98:
                logger.warning(
                    f"端口 {self.port} 已被占用，尝试使用端口 {self.port + 1}"
                )
                self.port += 1
                self.http_site = web.TCPSite(self.http_runner, self.host, self.port)
                await self.http_site.start()
                logger.info(f"HTTP API 已启动: http://{self.host}:{self.port}")
            else:
                raise

    async def _handle_index(self, request: web.Request) -> web.Response:
        html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>群聊脏话监控</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px; }
        .container { max-width: 800px; margin: 0 auto; }
        .card { background: white; border-radius: 16px; padding: 24px; margin-bottom: 20px; box-shadow: 0 10px 40px rgba(0,0,0,0.2); }
        h1 { color: white; text-align: center; margin-bottom: 30px; font-size: 28px; text-shadow: 0 2px 10px rgba(0,0,0,0.2); }
        .api-list { list-style: none; }
        .api-list li { padding: 16px; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; align-items: center; }
        .api-list li:last-child { border-bottom: none; }
        .api-path { font-family: monospace; background: #f0f0f0; padding: 6px 12px; border-radius: 6px; color: #333; }
        .api-desc { color: #666; }
        .btn { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; font-size: 14px; transition: transform 0.2s; }
        .btn:hover { transform: scale(1.05); }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin-top: 20px; }
        .stat-card { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 12px; text-align: center; }
        .stat-num { font-size: 32px; font-weight: bold; }
        .stat-label { font-size: 14px; opacity: 0.9; }
        #records { margin-top: 20px; }
        .record-item { background: #f8f9fa; padding: 16px; border-radius: 10px; margin-bottom: 10px; border-left: 4px solid #667eea; }
        .record-user { font-weight: bold; color: #333; }
        .record-msg { color: #666; margin: 8px 0; word-break: break-all; }
        .record-reason { color: #e74c3c; font-size: 13px; }
        .record-time { color: #999; font-size: 12px; margin-top: 8px; }
        .loading { text-align: center; padding: 40px; color: #666; }
        .danger-btn { background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%); }
        .danger-btn:hover { background: linear-gradient(135deg, #c0392b 0%, #a93226 100%); }
        .password-input { padding: 10px; border: 1px solid #ddd; border-radius: 8px; margin-right: 10px; width: 150px; }
        .btn-group { display: flex; gap: 10px; align-items: center; margin-top: 15px; flex-wrap: wrap; }
        .toast { position: fixed; top: 20px; right: 20px; padding: 15px 25px; border-radius: 10px; color: white; font-weight: bold; z-index: 1000; animation: slideIn 0.3s ease; }
        .toast-success { background: #27ae60; }
        .toast-error { background: #e74c3c; }
        @keyframes slideIn { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
    </style>
</head>
<body>
    <div class="container">
        <h1>群聊脏话监控</h1>
        <div class="card">
            <h2 style="margin-bottom: 15px; color: #333;">API 接口</h2>
            <ul class="api-list">
                <li><span class="api-path">GET /records</span><span class="api-desc">获取所有脏话记录</span></li>
                <li><span class="api-path">GET /stats</span><span class="api-desc">获取用户脏话统计</span></li>
            </ul>
        </div>
        <div class="card">
            <h2 style="margin-bottom: 15px; color: #333;">统计概览</h2>
            <div class="stats" id="stats">
                <div class="stat-card"><div class="stat-num" id="total">-</div><div class="stat-label">总记录数</div></div>
                <div class="stat-card"><div class="stat-num" id="users">-</div><div class="stat-label">涉及用户</div></div>
                <div class="stat-card"><div class="stat-num" id="groups">-</div><div class="stat-label">涉及群组</div></div>
            </div>
        </div>
        <div class="card">
            <h2 style="margin-bottom: 15px; color: #333;">最近记录</h2>
            <div class="btn-group">
                <button class="btn" onclick="loadRecords()">刷新数据</button>
                <input type="password" id="clearPassword" class="password-input" placeholder="输入管理密码">
                <button class="btn danger-btn" onclick="clearRecords()">清空所有记录</button>
            </div>
            <div id="records"><div class="loading">点击按钮加载数据</div></div>
        </div>
    </div>
    <script>
        async function loadRecords() {
            document.getElementById('records').innerHTML = '<div class="loading">加载中...</div>';
            try {
                const res = await fetch('/records');
                const data = await res.json();
                const records = data.data || [];
                document.getElementById('total').textContent = records.length;
                const users = new Set(records.map(r => r.user_id));
                const groups = new Set(records.map(r => r.group_id));
                document.getElementById('users').textContent = users.size;
                document.getElementById('groups').textContent = groups.size;
                const html = records.slice(-20).reverse().map(r => `
                    <div class="record-item">
                        <div class="record-user">${r.user_name}</div>
                        <div class="record-msg">${r.message}</div>
                        <div class="record-reason">${r.reason}</div>
                        <div class="record-time">${new Date(r.time).toLocaleString('zh-CN')}</div>
                    </div>
                `).join('');
                document.getElementById('records').innerHTML = html || '<div class="loading">暂无记录</div>';
            } catch(e) {
                document.getElementById('records').innerHTML = '<div class="loading">加载失败</div>';
            }
        }
        function showToast(msg, type) {
            const toast = document.createElement('div');
            toast.className = 'toast toast-' + type;
            toast.textContent = msg;
            document.body.appendChild(toast);
            setTimeout(() => toast.remove(), 3000);
        }
        async function clearRecords() {
            const password = document.getElementById('clearPassword').value;
            if (!password) {
                showToast('请输入管理密码', 'error');
                return;
            }
            if (!confirm('确定要清空所有记录吗？此操作不可恢复！')) {
                return;
            }
            try {
                const res = await fetch('/clear', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ password })
                });
                const data = await res.json();
                if (data.code === 0) {
                    showToast(data.msg, 'success');
                    loadRecords();
                } else {
                    showToast(data.msg, 'error');
                }
            } catch(e) {
                showToast('操作失败', 'error');
            }
        }
    </script>
</body>
</html>"""
        return web.Response(text=html, content_type="text/html")

    async def _handle_get_records(self, request: web.Request) -> web.Response:
        return web.json_response({"code": 0, "data": self.records})

    async def _handle_get_stats(self, request: web.Request) -> web.Response:
        # 按群统计
        group_stats = {}
        # 按人统计
        user_stats = {}
        for r in self.records:
            gid = r.get("group_id", "unknown")
            uid = r.get("user_id", "unknown")
            # 按群统计
            if gid not in group_stats:
                group_stats[gid] = {"count": 0, "users": {}}
            group_stats[gid]["count"] += 1
            # 按人统计（全局）
            if uid not in user_stats:
                user_stats[uid] = {
                    "user_name": r.get("user_name", ""),
                    "count": 0,
                    "groups": {},
                }
            user_stats[uid]["count"] += 1
            # 按人统计（分群）
            if gid not in user_stats[uid]["groups"]:
                user_stats[uid]["groups"][gid] = 0
            user_stats[uid]["groups"][gid] += 1
            # 按人统计（分群内）
            if uid not in group_stats[gid]["users"]:
                group_stats[gid]["users"][uid] = {
                    "user_name": r.get("user_name", ""),
                    "count": 0,
                }
            group_stats[gid]["users"][uid]["count"] += 1
        return web.json_response(
            {
                "code": 0,
                "data": {
                    "total": len(self.records),
                    "group_stats": group_stats,
                    "user_stats": user_stats,
                },
            }
        )

    async def _handle_clear_records(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            password = data.get("password", "")
            if password != self.admin_password:
                return web.json_response({"code": 1, "msg": "密码错误"})
            group_id = data.get("group_id")
            if group_id:
                self.records = [
                    r for r in self.records if r.get("group_id") != group_id
                ]
                msg = f"群组 {group_id} 的记录已清空"
            else:
                self.records = []
                msg = "所有记录已清空"
            self._save_records()
            logger.info(msg)
            return web.json_response({"code": 0, "msg": msg})
        except Exception as e:
            return web.json_response({"code": 1, "msg": str(e)})

    @filter.event_message_type(EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent):
        group_id = event.get_group_id()
        # 群聊过滤
        if self.ignore_groups and group_id in self.ignore_groups:
            return
        if self.enable_groups and group_id not in self.enable_groups:
            return
        message_str = event.message_str.strip()
        if not message_str:
            return
        try:
            prompt = (
                "请判断以下消息是否包含脏话、辱骂、侮辱性词汇。"
                '只回复一个JSON对象：{"is_profanity": true/false, "reason": "原因"}。\n'
                f"消息内容：{message_str}"
            )
            if self.provider_id:
                provider = self.context.get_provider_by_id(self.provider_id)
            else:
                provider = self.context.get_using_provider()
            if not provider:
                logger.error("未找到可用的LLM提供商")
                return
            llm_result = await provider.text_chat(prompt=prompt)
            response_text = llm_result.completion_text
            result = json.loads(response_text)
            if result.get("is_profanity"):
                record = {
                    "time": datetime.now().isoformat(),
                    "group_id": group_id,
                    "user_id": event.get_sender_id(),
                    "user_name": event.get_sender_name(),
                    "message": message_str,
                    "reason": result.get("reason", ""),
                }
                self.records.append(record)
                self._save_records()
                logger.info(f"检测到脏话: {event.get_sender_name()} - {message_str}")
        except Exception as e:
            logger.error(f"LLM分析失败: {e}")

    @filter.command("profanity_stats")
    async def query_stats(self, event: AstrMessageEvent):
        group_id = event.get_group_id()
        group_records = [r for r in self.records if r.get("group_id") == group_id]
        if not group_records:
            yield event.plain_result("本群暂无脏话记录。")
            return
        stats = {}
        for r in group_records:
            uid = r.get("user_id", "unknown")
            if uid not in stats:
                stats[uid] = {"name": r.get("user_name", ""), "count": 0}
            stats[uid]["count"] += 1
        lines = ["本群脏话统计："]
        for uid, info in sorted(
            stats.items(), key=lambda x: x[1]["count"], reverse=True
        ):
            lines.append(f"{info['name']}: {info['count']}次")
        yield event.plain_result("\n".join(lines))

    @filter.command("profanity_clear")
    async def clear_records(self, event: AstrMessageEvent):
        group_id = event.get_group_id()
        self.records = [r for r in self.records if r.get("group_id") != group_id]
        self._save_records()
        yield event.plain_result("本群脏话记录已清空。")

    async def terminate(self):
        self._save_records()
        if self.http_site:
            await self.http_site.stop()
        if self.http_runner:
            await self.http_runner.cleanup()
        logger.info("脏话监控插件已卸载。")
