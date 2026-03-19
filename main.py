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
        self.custom_prompt = config.get("custom_prompt", "") or (
            "请判断以下消息是否包含脏话、辱骂、侮辱性词汇，包括但不限于：\n"
            "1. 直接的脏话粗口 2. 谐音替代（如tm、卧槽、尼玛等）\n"
            "3. 拼音首字母缩写（如nmsl、wc等）4. 黑话暗语\n"
            "5. 网络流行梗中的侮辱性表达 6. 符号替代（如*、#等）\n\n"
            "注意以下情况不算脏话：\n"
            "- @某人的消息，如 '@用户名' 或 '@用户名(QQ号)'\n"
            "- 用户昵称、群名片中的文字\n"
            "- 正常的聊天内容\n\n"
            '只回复一个JSON对象：{"is_profanity": true/false, "reason": "原因"}。\n'
            "消息内容：{message}"
        )
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
        app.router.add_post("/delete", self._handle_delete_records)
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
        :root {
            --md-primary: #6750A4;
            --md-on-primary: #FFFFFF;
            --md-primary-container: #EADDFF;
            --md-on-primary-container: #21005D;
            --md-secondary: #625B71;
            --md-on-secondary: #FFFFFF;
            --md-secondary-container: #E8DEF8;
            --md-on-secondary-container: #1D192B;
            --md-tertiary: #7D5260;
            --md-on-tertiary: #FFFFFF;
            --md-tertiary-container: #FFD8E4;
            --md-surface: #FEF7FF;
            --md-surface-variant: #E7E0EC;
            --md-on-surface: #1C1B1F;
            --md-on-surface-variant: #49454F;
            --md-outline: #79747E;
            --md-outline-variant: #CAC4D0;
            --md-error: #B3261E;
            --md-shadow: 0 1px 3px 1px rgba(0,0,0,0.15), 0 1px 2px rgba(0,0,0,0.3);
            --md-shadow-lg: 0 4px 8px 3px rgba(0,0,0,0.15), 0 1px 3px rgba(0,0,0,0.3);
        }
        body { font-family: 'Google Sans', 'Roboto', 'Noto Sans SC', sans-serif; background: url('https://imgbed.iqach.top/file/1773915308321_92650004_p0.jpg') no-repeat center center fixed; background-size: cover; min-height: 100vh; padding: 16px; }
        .container { max-width: 840px; margin: 0 auto; }
        .card { background: rgba(254, 247, 255, 0.92); backdrop-filter: blur(20px); border-radius: 28px; padding: 24px; margin-bottom: 16px; box-shadow: var(--md-shadow); }
        h1 { color: var(--md-primary); text-align: center; margin-bottom: 24px; font-size: 28px; font-weight: 400; letter-spacing: 0.5px; }
        h2 { color: var(--md-on-surface) !important; font-size: 16px !important; font-weight: 500 !important; letter-spacing: 0.15px; }
        .btn { background: var(--md-primary); color: var(--md-on-primary); border: none; padding: 10px 24px; border-radius: 20px; cursor: pointer; font-size: 14px; font-weight: 500; transition: all 0.2s; box-shadow: var(--md-shadow); letter-spacing: 0.1px; }
        .btn:hover { box-shadow: var(--md-shadow-lg); filter: brightness(1.08); }
        .btn:active { transform: scale(0.98); }
        .btn-outlined { background: transparent; color: var(--md-primary); border: 1px solid var(--md-outline); box-shadow: none; }
        .btn-outlined:hover { background: rgba(103, 80, 164, 0.08); box-shadow: none; }
        .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
        .stat-card { background: var(--md-primary-container); color: var(--md-on-primary-container); padding: 20px 16px; border-radius: 16px; text-align: center; }
        .stat-num { font-size: 36px; font-weight: 400; line-height: 1; }
        .stat-label { font-size: 12px; margin-top: 8px; opacity: 0.8; letter-spacing: 0.4px; }
        #records { margin-top: 16px; }
        .record-item { background: var(--md-surface-variant); padding: 16px; border-radius: 16px; margin-bottom: 8px; display: flex; gap: 12px; }
        .record-user { font-weight: 500; color: var(--md-on-surface); font-size: 14px; }
        .record-msg { color: var(--md-on-surface-variant); margin: 8px 0; word-break: break-all; font-size: 14px; line-height: 1.5; }
        .record-reason { color: var(--md-tertiary); font-size: 12px; }
        .record-time { color: var(--md-outline); font-size: 11px; margin-top: 6px; }
        .loading { text-align: center; padding: 40px; color: var(--md-outline); font-size: 14px; }
        .danger-btn { background: var(--md-error); }
        .danger-btn:hover { background: #9a2018; }
        .password-input, .search-input { padding: 12px 16px; border: none; border-radius: 20px; background: var(--md-surface-variant); color: var(--md-on-surface); font-size: 14px; outline: none; transition: all 0.2s; }
        .password-input:focus, .search-input:focus { box-shadow: 0 0 0 2px var(--md-primary); }
        .search-input { width: 100%; padding-left: 44px; }
        .search-wrapper { position: relative; margin-bottom: 16px; }
        .search-icon { position: absolute; left: 16px; top: 50%; transform: translateY(-50%); color: var(--md-outline); }
        .btn-group { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
        .toast { position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%); padding: 14px 24px; border-radius: 8px; color: var(--md-on-surface); font-size: 14px; z-index: 1000; animation: slideUp 0.3s ease; box-shadow: var(--md-shadow-lg); }
        .toast-success { background: #C4EED0; }
        .toast-error { background: #FFEDEA; }
        @keyframes slideUp { from { transform: translate(-50%, 100%); opacity: 0; } to { transform: translate(-50%, 0); opacity: 1; } }
        .ranking-item { display: flex; align-items: center; padding: 12px 8px; border-radius: 16px; margin-bottom: 4px; }
        .ranking-item:hover { background: var(--md-surface-variant); }
        .ranking-num { width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 500; margin-right: 12px; }
        .ranking-1 { background: #FFD8E4; color: var(--md-tertiary); }
        .ranking-2 { background: var(--md-surface-variant); color: var(--md-on-surface-variant); }
        .ranking-3 { background: #FFE0B2; color: #E65100; }
        .ranking-other { background: transparent; color: var(--md-outline); border: 1px solid var(--md-outline-variant); }
        .ranking-info { flex: 1; margin-left: 8px; }
        .ranking-name { font-weight: 500; color: var(--md-on-surface); font-size: 14px; }
        .ranking-qq { font-size: 12px; color: var(--md-outline); margin-top: 2px; }
        .ranking-group { font-size: 11px; color: var(--md-outline); }
        .ranking-count { font-size: 18px; font-weight: 500; color: var(--md-primary); }
        .ranking-count span { font-size: 11px; color: var(--md-outline); }
        .ranking-avatar { width: 40px; height: 40px; border-radius: 50%; margin-left: 8px; object-fit: cover; }
        .tabs { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
        .tab { padding: 8px 16px; border-radius: 8px; cursor: pointer; background: transparent; color: var(--md-on-surface-variant); font-size: 14px; font-weight: 500; transition: all 0.2s; border: none; }
        .tab:hover { background: rgba(103, 80, 164, 0.08); }
        .tab.active { background: var(--md-secondary-container); color: var(--md-on-secondary-container); }
        .record-checkbox { width: 20px; height: 20px; accent-color: var(--md-primary); cursor: pointer; flex-shrink: 0; margin-top: 2px; }
        select { padding: 8px 16px; border-radius: 8px; border: none; background: var(--md-surface-variant); color: var(--md-on-surface); font-size: 14px; cursor: pointer; outline: none; }
        select:focus { box-shadow: 0 0 0 2px var(--md-primary); }
        .record-content { flex: 1; }
        .record-header { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
        .record-avatar { width: 36px; height: 36px; border-radius: 50%; object-fit: cover; }
        .record-actions { display: flex; align-items: flex-start; gap: 8px; }
        .delete-btn { background: transparent; color: var(--md-error); border: none; padding: 6px 12px; border-radius: 8px; cursor: pointer; font-size: 12px; font-weight: 500; transition: all 0.2s; }
        .delete-btn:hover { background: rgba(179, 38, 30, 0.08); }
        .highlight { background: #FFF59D; border-radius: 2px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>群聊脏话监控</h1>
        <div class="card">
            <div class="stats">
                <div class="stat-card"><div class="stat-num" id="total">-</div><div class="stat-label">总记录数</div></div>
                <div class="stat-card"><div class="stat-num" id="users">-</div><div class="stat-label">涉及用户</div></div>
                <div class="stat-card"><div class="stat-num" id="groups">-</div><div class="stat-label">涉及群组</div></div>
            </div>
        </div>
        <div class="card">
            <h2 style="margin-bottom: 12px;">脏话排行榜</h2>
            <div class="tabs">
                <div class="tab active" onclick="switchTab('global')">总榜</div>
                <select id="groupSelect" onchange="switchTab('group')">
                    <option value="">选择群聊</option>
                </select>
            </div>
            <div id="ranking"><div class="loading">加载数据后显示排行榜</div></div>
        </div>
        <div class="card">
            <h2 style="margin-bottom: 12px;">最近记录</h2>
            <div class="search-wrapper">
                <span class="search-icon">&#128269;</span>
                <input type="text" class="search-input" id="searchInput" placeholder="搜索关键词、用户、群聊..." oninput="filterRecords()">
            </div>
            <div class="tabs">
                <div class="tab active" onclick="switchRecordTab('all')">全部</div>
                <select id="recordGroupSelect" onchange="switchRecordTab('group')">
                    <option value="">选择群聊</option>
                </select>
            </div>
            <div class="btn-group">
                <button class="btn btn-outlined" onclick="loadRecords()">刷新</button>
                <span id="adminBtns" style="display: none; gap: 8px; display: none;">
                    <button class="btn btn-outlined" onclick="selectAll()">全选</button>
                    <button class="btn btn-outlined" onclick="selectNone()">取消</button>
                    <button class="btn danger-btn" onclick="deleteSelected()" id="deleteSelectedBtn" style="display: none;">删除 (<span id="selectedCount">0</span>)</button>
                </span>
            </div>
            <div id="records"><div class="loading">点击刷新加载数据</div></div>
        </div>
        <div class="card" style="text-align: center; padding: 16px;">
            <span style="color: var(--md-outline); font-size: 13px;">
                <a href="/records" target="_blank" style="color: var(--md-primary); text-decoration: none;">/records</a> · 
                <a href="/stats" target="_blank" style="color: var(--md-primary); text-decoration: none;">/stats</a> · 
                <a href="https://github.com/huanxherta/syemamalielie" target="_blank" style="color: var(--md-primary); text-decoration: none;">GitHub</a>
            </span>
        </div>
        <div class="card">
            <h2 style="margin-bottom: 12px;">管理</h2>
            <div id="loginSection">
                <div class="btn-group">
                    <input type="password" id="loginPassword" class="password-input" placeholder="管理密码">
                    <button class="btn" onclick="login()">登录</button>
                </div>
            </div>
            <div id="adminSection" style="display: none;">
                <div class="btn-group">
                    <button class="btn" onclick="clearRecords()">清空全部</button>
                    <button class="btn btn-outlined" onclick="logout()">退出</button>
                </div>
            </div>
        </div>
    </div>
    <script>
        window.allRecords = [];
        window.currentRecordGroup = '';
        function getGroupName(r) {
            return (r.group_name && r.group_name.trim()) || `群${r.group_id}`;
        }
        function switchRecordTab(type) {
            if (type === 'all') {
                window.currentRecordGroup = '';
                document.getElementById('recordGroupSelect').value = '';
            } else {
                window.currentRecordGroup = document.getElementById('recordGroupSelect').value;
            }
            filterRecords();
        }
        function filterRecords() {
            const keyword = document.getElementById('searchInput').value.toLowerCase();
            const records = window.allRecords || [];
            const isLoggedIn = !!window.adminToken;
            let filtered = records;
            if (window.currentRecordGroup) {
                filtered = filtered.filter(r => r.group_id === window.currentRecordGroup);
            }
            if (keyword) {
                filtered = filtered.filter(r => 
                    (r.message && r.message.toLowerCase().includes(keyword)) ||
                    (r.user_name && r.user_name.toLowerCase().includes(keyword)) ||
                    (r.user_id && r.user_id.toString().includes(keyword)) ||
                    (getGroupName(r).toLowerCase().includes(keyword)) ||
                    (r.group_id && r.group_id.toString().includes(keyword)) ||
                    (r.reason && r.reason.toLowerCase().includes(keyword))
                );
            }
            renderRecords(filtered.slice(-50).reverse(), filtered.length, isLoggedIn);
        }
        function renderRecords(records, total, isLoggedIn) {
            const html = records.map((r, displayIdx) => {
                const realIdx = total - 1 - displayIdx;
                return `
                <div class="record-item" id="record-${realIdx}">
                    ${isLoggedIn ? `<input type="checkbox" class="record-checkbox" data-index="${realIdx}" onchange="toggleSelect(${realIdx})">` : ''}
                    <div class="record-content">
                        <div class="record-header">
                            <img class="record-avatar" src="${getAvatarUrl(r.user_id)}" onerror="this.style.display='none'">
                            <div>
                                <div class="record-user">${r.user_name}</div>
                                <div style="font-size: 11px; color: var(--md-outline);">${getGroupName(r)}</div>
                            </div>
                        </div>
                        <div class="record-msg">${r.message}</div>
                        <div class="record-reason">${r.reason}</div>
                        <div class="record-time">${new Date(r.time).toLocaleString('zh-CN')}</div>
                    </div>
                    ${isLoggedIn ? `<button class="delete-btn" onclick="deleteSingle(${realIdx})">删除</button>` : ''}
                </div>
            `}).join('');
            document.getElementById('records').innerHTML = html || '<div class="loading">暂无记录</div>';
        }
        function updateRecordGroupSelect() {
            const records = window.allRecords || [];
            const groupMap = {};
            records.forEach(r => {
                if (!groupMap[r.group_id]) {
                    groupMap[r.group_id] = getGroupName(r);
                }
            });
            const select = document.getElementById('recordGroupSelect');
            const currentVal = select.value;
            select.innerHTML = '<option value="">选择群聊</option>';
            Object.entries(groupMap).forEach(([gid, gname]) => {
                const option = document.createElement('option');
                option.value = gid;
                option.textContent = gname;
                if (gid === currentVal) option.selected = true;
                select.appendChild(option);
            });
        }
        async function loadRecords() {
            document.getElementById('records').innerHTML = '<div class="loading">加载中...</div>';
            try {
                const res = await fetch('/records');
                const data = await res.json();
                const records = data.data || [];
                // 更新群名：用新记录的群名覆盖旧记录
                const groupNameMap = {};
                records.forEach(r => {
                    if (r.group_name && r.group_name.trim()) {
                        groupNameMap[r.group_id] = r.group_name;
                    }
                });
                records.forEach(r => {
                    if ((!r.group_name || !r.group_name.trim()) && groupNameMap[r.group_id]) {
                        r.group_name = groupNameMap[r.group_id];
                    }
                });
                window.records = records;
                window.allRecords = records;
                window.selectedIndices = new Set();
                document.getElementById('total').textContent = records.length;
                const users = new Set(records.map(r => r.user_id));
                const groups = new Set(records.map(r => r.group_id));
                document.getElementById('users').textContent = users.size;
                document.getElementById('groups').textContent = groups.size;
                updateRecordGroupSelect();
                filterRecords();
                updateDeleteBtn();
                updateGroupSelect();
                updateRanking('global');
            } catch(e) {
                document.getElementById('records').innerHTML = '<div class="loading">加载失败</div>';
            }
        }
        function toggleSelect(idx) {
            if (window.selectedIndices.has(idx)) {
                window.selectedIndices.delete(idx);
            } else {
                window.selectedIndices.add(idx);
            }
            updateDeleteBtn();
        }
        function selectAll() {
            document.querySelectorAll('.record-checkbox').forEach(cb => {
                cb.checked = true;
                window.selectedIndices.add(parseInt(cb.dataset.index));
            });
            updateDeleteBtn();
        }
        function selectNone() {
            document.querySelectorAll('.record-checkbox').forEach(cb => {
                cb.checked = false;
            });
            window.selectedIndices.clear();
            updateDeleteBtn();
        }
        function updateDeleteBtn() {
            const count = window.selectedIndices ? window.selectedIndices.size : 0;
            document.getElementById('selectedCount').textContent = count;
            document.getElementById('deleteSelectedBtn').style.display = count > 0 ? 'inline-block' : 'none';
        }
        async function deleteSingle(idx) {
            if (!window.adminToken) {
                showToast('请先登录', 'error');
                return;
            }
            if (!confirm('确定要删除这条记录吗？')) {
                return;
            }
            await doDelete([idx]);
        }
        async function deleteSelected() {
            if (!window.adminToken) {
                showToast('请先登录', 'error');
                return;
            }
            if (window.selectedIndices.size === 0) {
                showToast('请先选择要删除的记录', 'error');
                return;
            }
            if (!confirm(`确定要删除选中的 ${window.selectedIndices.size} 条记录吗？`)) {
                return;
            }
            await doDelete(Array.from(window.selectedIndices));
        }
        async function doDelete(indices) {
            try {
                const res = await fetch('/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ token: window.adminToken, indices })
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
        let currentTab = 'global';
        function switchTab(tab) {
            currentTab = tab;
            if (tab === 'global') {
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                event.target.classList.add('active');
                document.getElementById('groupSelect').value = '';
            }
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
            let selectedGroupId = '';
            if (type === 'group') {
                selectedGroupId = document.getElementById('groupSelect').value;
                if (selectedGroupId) {
                    filtered = records.filter(r => r.group_id === selectedGroupId);
                } else {
                    filtered = [];
                }
            }
            const userStats = {};
            filtered.forEach(r => {
                const key = r.user_id;  // 使用QQ号作为唯一标识
                const groupName = getGroupName(r);
                if (!userStats[key]) {
                    userStats[key] = { qq: r.user_id, name: r.user_name, count: 0, groups: {} };
                }
                userStats[key].count++;
                if (!userStats[key].groups[r.group_id]) {
                    userStats[key].groups[r.group_id] = { name: groupName, count: 0 };
                }
                userStats[key].groups[r.group_id].count++;
            });
            const sorted = Object.entries(userStats).sort((a, b) => b[1].count - a[1].count);
            if (sorted.length === 0) {
                document.getElementById('ranking').innerHTML = '<div class="loading">暂无数据</div>';
                return;
            }
            const html = sorted.slice(0, 10).map(([uid, info], index) => {
                const rankClass = index < 3 ? `ranking-${index + 1}` : 'ranking-other';
                const groupCount = Object.keys(info.groups).length;
                const groupInfo = groupCount > 1 ? `${groupCount}个群` : Object.values(info.groups)[0]?.name || '1个群';
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
        function updateGroupSelect() {
            const records = window.records || [];
            const groupMap = {};
            records.forEach(r => {
                if (!groupMap[r.group_id]) {
                    groupMap[r.group_id] = getGroupName(r);
                }
            });
            const select = document.getElementById('groupSelect');
            select.innerHTML = '<option value="">选择群聊</option>';
            Object.entries(groupMap).forEach(([gid, gname]) => {
                const option = document.createElement('option');
                option.value = gid;
                option.textContent = gname;
                select.appendChild(option);
            });
        }
        let adminToken = localStorage.getItem('adminToken') || '';
        window.adminToken = adminToken;
        function checkLogin() {
            adminToken = localStorage.getItem('adminToken') || '';
            window.adminToken = adminToken;
            if (adminToken) {
                document.getElementById('loginSection').style.display = 'none';
                document.getElementById('adminSection').style.display = 'block';
                document.getElementById('adminBtns').style.display = 'inline';
            } else {
                document.getElementById('loginSection').style.display = 'block';
                document.getElementById('adminSection').style.display = 'none';
                document.getElementById('adminBtns').style.display = 'none';
            }
            loadRecords();
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

    async def _handle_delete_records(self, request: web.Request) -> web.Response:
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
            # 获取要删除的记录索引列表
            indices = data.get("indices", [])
            if not indices:
                return web.json_response({"code": 1, "msg": "请选择要删除的记录"})
            # 按索引从大到小排序删除
            indices.sort(reverse=True)
            deleted_count = 0
            for idx in indices:
                if 0 <= idx < len(self.records):
                    self.records.pop(idx)
                    deleted_count += 1
            self._save_records()
            logger.info(f"删除了 {deleted_count} 条记录")
            return web.json_response(
                {"code": 0, "msg": f"成功删除 {deleted_count} 条记录"}
            )
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
            if self.custom_prompt:
                prompt = self.custom_prompt.replace("{message}", message_str)
            else:
                prompt = (
                    "请判断以下消息是否包含脏话、辱骂、侮辱性词汇，包括但不限于：\n"
                    "1. 直接的脏话粗口 2. 谐音替代（如tm、卧槽、尼玛等）\n"
                    "3. 拼音首字母缩写（如nmsl、wc等）4. 黑话暗语\n"
                    "5. 网络流行梗中的侮辱性表达 6. 符号替代（如*、#等）\n\n"
                    "注意以下情况不算脏话：\n"
                    "- @某人的消息，如 '@用户名' 或 '@用户名(QQ号)'\n"
                    "- 用户昵称、群名片中的文字\n"
                    "- 正常的聊天内容\n\n"
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
                group_name = ""
                # 尝试获取真实昵称和群名
                try:
                    # 尝试获取群名
                    if hasattr(event, "get_group_name"):
                        group_name = event.get_group_name() or ""
                    # 尝试获取真实昵称
                    client = event.bot
                    if hasattr(client, "get_stranger_info"):
                        info = await client.get_stranger_info(user_id=int(user_id))
                        if info and "nickname" in info:
                            user_name = info["nickname"]
                except:
                    pass
                # 如果获取到群名，更新同一群号的所有旧记录
                if group_name:
                    for r in self.records:
                        if r.get("group_id") == group_id and not r.get("group_name"):
                            r["group_name"] = group_name
                record = {
                    "time": datetime.now().isoformat(),
                    "group_id": group_id,
                    "group_name": group_name,
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
