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
        self.login_attempts = {}
        self.login_tokens = {}

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
        app.router.add_post("/login", self._handle_login)
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
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: url('https://imgbed.iqach.top/file/1773915308321_92650004_p0.jpg') no-repeat center center fixed; background-size: cover; min-height: 100vh; padding: 20px; }
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
        .ranking-item { display: flex; align-items: center; padding: 12px; border-bottom: 1px solid #eee; }
        .ranking-item:last-child { border-bottom: none; }
        .ranking-num { width: 30px; height: 30px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; margin-right: 15px; }
        .ranking-1 { background: #ffd700; color: #333; }
        .ranking-2 { background: #c0c0c0; color: #333; }
        .ranking-3 { background: #cd7f32; color: white; }
        .ranking-other { background: #f0f0f0; color: #666; }
        .ranking-info { flex: 1; }
        .ranking-name { font-weight: bold; color: #333; }
        .ranking-qq { font-size: 12px; color: #999; margin-top: 2px; }
        .ranking-group { font-size: 12px; color: #999; margin-top: 2px; }
        .ranking-count { font-size: 20px; font-weight: bold; color: #e74c3c; }
        .ranking-count span { font-size: 12px; color: #999; }
        .ranking-avatar { width: 40px; height: 40px; border-radius: 50%; margin-right: 12px; object-fit: cover; }
        .ranking-group { font-size: 12px; color: #999; margin-top: 2px; }
        .ranking-count { font-size: 20px; font-weight: bold; color: #e74c3c; }
        .ranking-count span { font-size: 12px; color: #999; }
        .tabs { display: flex; gap: 10px; margin-bottom: 15px; }
        .tab { padding: 8px 16px; border-radius: 6px; cursor: pointer; background: #f0f0f0; color: #666; transition: all 0.2s; }
        .tab.active { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; }
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
            <h2 style="margin-bottom: 15px; color: #333;">脏话排行榜</h2>
            <div class="tabs">
                <div class="tab active" onclick="switchTab('global')">总榜</div>
                <div class="tab" onclick="switchTab('group')">本群</div>
            </div>
            <div id="ranking"><div class="loading">加载数据后显示排行榜</div></div>
        </div>
        <div class="card">
            <h2 style="margin-bottom: 15px; color: #333;">管理操作</h2>
            <div id="loginSection">
                <div class="btn-group">
                    <input type="password" id="loginPassword" class="password-input" placeholder="输入管理密码">
                    <button class="btn" onclick="login()">登录</button>
                </div>
            </div>
            <div id="adminSection" style="display: none;">
                <div class="btn-group">
                    <button class="btn" onclick="loadRecords()">刷新数据</button>
                    <button class="btn danger-btn" onclick="clearRecords()">清空所有记录</button>
                    <button class="btn" onclick="logout()">退出登录</button>
                </div>
            </div>
        </div>
        <div class="card">
            <h2 style="margin-bottom: 15px; color: #333;">最近记录</h2>
            <div class="btn-group">
                <button class="btn" onclick="loadRecords()">刷新数据</button>
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
                window.records = records;
                document.getElementById('total').textContent = records.length;
                const users = new Set(records.map(r => r.user_id));
                const groups = new Set(records.map(r => r.group_id));
                document.getElementById('users').textContent = users.size;
                document.getElementById('groups').textContent = groups.size;
                const html = records.slice(-20).reverse().map(r => `
                    <div class="record-item">
                        <div style="display: flex; align-items: center; margin-bottom: 8px;">
                            <img src="${getAvatarUrl(r.user_id)}" style="width: 32px; height: 32px; border-radius: 50%; margin-right: 10px;" onerror="this.style.display='none'">
                            <div>
                                <div class="record-user">${r.user_name}</div>
                                <div style="font-size: 12px; color: #999;">QQ: ${maskQQ(r.user_id)}</div>
                            </div>
                        </div>
                        <div class="record-msg">${r.message}</div>
                        <div class="record-reason">${r.reason}</div>
                        <div class="record-time">${new Date(r.time).toLocaleString('zh-CN')}</div>
                    </div>
                `).join('');
                document.getElementById('records').innerHTML = html || '<div class="loading">暂无记录</div>';
                updateRanking('global');
            } catch(e) {
                document.getElementById('records').innerHTML = '<div class="loading">加载失败</div>';
            }
        }
        let currentTab = 'global';
        function switchTab(tab) {
            currentTab = tab;
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            event.target.classList.add('active');
            updateRanking(tab);
        }
        function maskQQ(qq) {
            const s = String(qq);
            if (s.length <= 4) return s;
            if (s.length <= 7) return s.slice(0, 2) + '***' + s.slice(-1);
            return s.slice(0, 3) + '***' + s.slice(-3);
        }
        function getAvatarUrl(qq) {
            return `https://q.qlogo.cn/headimg_dl?dst_uin=${qq}&spec=640`;
        }
        function updateRanking(type) {
            const records = window.records || [];
            let filtered = records;
            if (type === 'group') {
                const lastRecord = records[records.length - 1];
                if (lastRecord) {
                    filtered = records.filter(r => r.group_id === lastRecord.group_id);
                }
            }
            const userStats = {};
            filtered.forEach(r => {
                const key = r.user_id;  // 使用QQ号作为唯一标识
                if (!userStats[key]) {
                    userStats[key] = { qq: r.user_id, name: r.user_name, count: 0, groups: {} };
                }
                userStats[key].count++;
                if (!userStats[key].groups[r.group_id]) {
                    userStats[key].groups[r.group_id] = 0;
                }
                userStats[key].groups[r.group_id]++;
            });
            const sorted = Object.entries(userStats).sort((a, b) => b[1].count - a[1].count);
            if (sorted.length === 0) {
                document.getElementById('ranking').innerHTML = '<div class="loading">暂无数据</div>';
                return;
            }
            const html = sorted.slice(0, 10).map(([uid, info], index) => {
                const rankClass = index < 3 ? `ranking-${index + 1}` : 'ranking-other';
                const groupInfo = Object.keys(info.groups).length > 1 ? `${Object.keys(info.groups).length}个群` : '1个群';
                return `
                    <div class="ranking-item">
                        <div class="ranking-num ${rankClass}">${index + 1}</div>
                        <img class="ranking-avatar" src="${getAvatarUrl(info.qq)}" onerror="this.style.display='none'">
                        <div class="ranking-info">
                            <div class="ranking-name">${info.name}</div>
                            <div class="ranking-qq">QQ: ${maskQQ(info.qq)}</div>
                            <div class="ranking-group">涉及 ${groupInfo}</div>
                        </div>
                        <div class="ranking-count">${info.count}<span>次</span></div>
                    </div>
                `;
            }).join('');
            document.getElementById('ranking').innerHTML = html;
        }
        let adminToken = localStorage.getItem('adminToken') || '';
        function checkLogin() {
            if (adminToken) {
                document.getElementById('loginSection').style.display = 'none';
                document.getElementById('adminSection').style.display = 'block';
            } else {
                document.getElementById('loginSection').style.display = 'block';
                document.getElementById('adminSection').style.display = 'none';
            }
        }
        async function login() {
            const password = document.getElementById('loginPassword').value;
            if (!password) {
                showToast('请输入管理密码', 'error');
                return;
            }
            try {
                const res = await fetch('/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ password })
                });
                const data = await res.json();
                if (data.code === 0) {
                    adminToken = data.token;
                    localStorage.setItem('adminToken', adminToken);
                    checkLogin();
                    showToast('登录成功', 'success');
                    document.getElementById('loginPassword').value = '';
                } else {
                    showToast(data.msg, 'error');
                }
            } catch(e) {
                showToast('登录失败', 'error');
            }
        }
        function logout() {
            adminToken = '';
            localStorage.removeItem('adminToken');
            checkLogin();
            showToast('已退出登录', 'success');
        }
        function showToast(msg, type) {
            const toast = document.createElement('div');
            toast.className = 'toast toast-' + type;
            toast.textContent = msg;
            document.body.appendChild(toast);
            setTimeout(() => toast.remove(), 3000);
        }
        async function clearRecords() {
            if (!adminToken) {
                showToast('请先登录', 'error');
                return;
            }
            if (!confirm('确定要清空所有记录吗？此操作不可恢复！')) {
                return;
            }
            try {
                const res = await fetch('/clear', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ token: adminToken })
                });
                const data = await res.json();
                if (data.code === 0) {
                    showToast(data.msg, 'success');
                    loadRecords();
                } else {
                    showToast(data.msg, 'error');
                    if (data.msg.includes('登录')) {
                        logout();
                    }
                }
            } catch(e) {
                showToast('操作失败', 'error');
            }
        }
        checkLogin();
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

    async def _handle_login(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            password = data.get("password", "")
            client_ip = request.remote
            # 检查是否被锁定
            if client_ip in self.login_attempts:
                attempts, lock_time = self.login_attempts[client_ip]
                if attempts >= 5:
                    import time

                    if time.time() - lock_time < 1800:  # 锁定30分钟
                        return web.json_response(
                            {"code": 1, "msg": "登录失败次数过多，请30分钟后重试"}
                        )
                    else:
                        del self.login_attempts[client_ip]
            # 验证密码
            if password != self.admin_password:
                # 记录失败次数
                import time

                if client_ip not in self.login_attempts:
                    self.login_attempts[client_ip] = [1, time.time()]
                else:
                    self.login_attempts[client_ip][0] += 1
                    self.login_attempts[client_ip][1] = time.time()
                return web.json_response({"code": 1, "msg": "密码错误"})
            # 生成token
            import uuid
            import time

            token = str(uuid.uuid4())
            self.login_tokens[token] = {"ip": client_ip, "time": time.time()}
            # 清除失败记录
            if client_ip in self.login_attempts:
                del self.login_attempts[client_ip]
            return web.json_response({"code": 0, "token": token})
        except Exception as e:
            return web.json_response({"code": 1, "msg": str(e)})

    async def _handle_clear_records(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            token = data.get("token", "")
            # 验证token
            import time

            if token not in self.login_tokens:
                return web.json_response({"code": 1, "msg": "请先登录"})
            token_data = self.login_tokens[token]
            # token有效期30分钟
            if time.time() - token_data["time"] > 1800:
                del self.login_tokens[token]
                return web.json_response({"code": 1, "msg": "登录已过期，请重新登录"})
            # 刷新token时间
            self.login_tokens[token]["time"] = time.time()
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
                user_id = event.get_sender_id()
                user_name = event.get_sender_name()
                # 尝试获取真实昵称
                try:
                    client = event.bot
                    if hasattr(client, "get_stranger_info"):
                        info = await client.get_stranger_info(user_id=int(user_id))
                        if info and "nickname" in info:
                            user_name = info["nickname"]
                except:
                    pass
                record = {
                    "time": datetime.now().isoformat(),
                    "group_id": group_id,
                    "user_id": user_id,
                    "user_name": user_name,
                    "message": message_str,
                    "reason": result.get("reason", ""),
                }
                self.records.append(record)
                self._save_records()
                logger.info(f"检测到脏话: {user_name}({user_id}) - {message_str}")
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
