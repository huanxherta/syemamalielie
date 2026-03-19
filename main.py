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
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>群聊脏话监控</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
        :root {
            --ios-bg: #F2F2F7;
            --ios-card: rgba(255,255,255,0.82);
            --ios-blue: #007AFF;
            --ios-red: #FF3B30;
            --ios-green: #34C759;
            --ios-orange: #FF9500;
            --ios-gray: #8E8E93;
            --ios-gray2: #AEAEB2;
            --ios-gray3: #C7C7CC;
            --ios-gray4: #D1D1D6;
            --ios-gray5: #E5E5EA;
            --ios-gray6: #F2F2F7;
            --ios-label: #000000;
            --ios-label2: #3C3C43;
            --ios-separator: rgba(60,60,67,0.12);
        }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'SF Pro Display', 'Helvetica Neue', 'PingFang SC', 'Noto Sans CJK SC', sans-serif;
            background: url('https://imgbed.iqach.top/file/1773915308321_92650004_p0.jpg') no-repeat center center fixed;
            background-size: cover;
            min-height: 100vh;
            padding: 20px 16px;
            -webkit-font-smoothing: antialiased;
        }
        body::before { content: ''; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(242,242,247,0.6); z-index: -1; }
        .container { max-width: 428px; margin: 0 auto; }
        .ios-header { text-align: center; margin-bottom: 20px; }
        .ios-header h1 { font-size: 34px; font-weight: 700; color: var(--ios-label); letter-spacing: -0.5px; }
        .ios-section { background: var(--ios-card); backdrop-filter: blur(40px); -webkit-backdrop-filter: blur(40px); border-radius: 13px; overflow: hidden; margin-bottom: 20px; }
        .ios-section-header { padding: 12px 16px 8px; font-size: 13px; font-weight: 400; color: var(--ios-gray); text-transform: uppercase; letter-spacing: -0.08px; }
        .ios-row { display: flex; align-items: center; padding: 12px 16px; background: var(--ios-card); position: relative; }
        .ios-row:not(:last-child)::after { content: ''; position: absolute; bottom: 0; left: 54px; right: 16px; height: 0.5px; background: var(--ios-separator); }
        .ios-row-content { flex: 1; }
        .ios-row-title { font-size: 17px; color: var(--ios-label); line-height: 1.2; }
        .ios-row-subtitle { font-size: 14px; color: var(--ios-gray); margin-top: 2px; }
        .ios-row-value { font-size: 17px; color: var(--ios-gray); }
        .ios-row-arrow { color: var(--ios-gray3); margin-left: 8px; font-size: 14px; }
        .ios-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px; background: var(--ios-separator); }
        .ios-stat { background: var(--ios-card); padding: 16px 8px; text-align: center; }
        .ios-stat-num { font-size: 28px; font-weight: 600; color: var(--ios-blue); font-variant-numeric: tabular-nums; }
        .ios-stat-label { font-size: 12px; color: var(--ios-gray); margin-top: 4px; }
        .ios-btn { display: inline-block; padding: 8px 16px; border-radius: 8px; font-size: 15px; font-weight: 400; border: none; cursor: pointer; transition: all 0.15s; }
        .ios-btn:active { transform: scale(0.97); opacity: 0.7; }
        .ios-btn-primary { background: var(--ios-blue); color: white; }
        .ios-btn-red { background: var(--ios-red); color: white; }
        .ios-btn-gray { background: var(--ios-gray5); color: var(--ios-label); }
        .ios-btn-text { background: transparent; color: var(--ios-blue); padding: 8px 12px; }
        .ios-input { width: 100%; padding: 10px 12px; border: none; border-radius: 8px; background: var(--ios-gray6); font-size: 17px; outline: none; }
        .ios-input::placeholder { color: var(--ios-gray2); }
        .ios-search { position: relative; margin: 0 16px 12px; }
        .ios-search input { padding-left: 36px; }
        .ios-search-icon { position: absolute; left: 10px; top: 50%; transform: translateY(-50%); color: var(--ios-gray); font-size: 16px; }
        .ios-tabs { display: flex; padding: 0 16px 12px; gap: 8px; }
        .ios-tab { padding: 6px 12px; border-radius: 16px; font-size: 13px; font-weight: 500; background: var(--ios-gray5); color: var(--ios-label2); cursor: pointer; transition: all 0.15s; border: none; }
        .ios-tab.active { background: var(--ios-blue); color: white; }
        .ios-select { padding: 6px 12px; border-radius: 16px; font-size: 13px; background: var(--ios-gray5); color: var(--ios-label2); border: none; cursor: pointer; outline: none; }
        .ranking-avatar { width: 44px; height: 44px; border-radius: 50%; margin-right: 12px; object-fit: cover; }
        .ranking-badge { width: 24px; height: 24px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600; margin-right: 12px; flex-shrink: 0; }
        .rank-1 { background: linear-gradient(135deg, #FFD700, #FFA500); color: white; }
        .rank-2 { background: linear-gradient(135deg, #C0C0C0, #A0A0A0); color: white; }
        .rank-3 { background: linear-gradient(135deg, #CD7F32, #8B4513); color: white; }
        .rank-other { background: var(--ios-gray5); color: var(--ios-gray); }
        .ranking-count { font-size: 20px; font-weight: 600; color: var(--ios-label); }
        .ranking-count span { font-size: 12px; color: var(--ios-gray); font-weight: 400; }
        .record-avatar { width: 40px; height: 40px; border-radius: 50%; margin-right: 12px; flex-shrink: 0; object-fit: cover; }
        .record-checkbox { width: 20px; height: 20px; margin-right: 12px; accent-color: var(--ios-blue); flex-shrink: 0; }
        .delete-text-btn { background: none; border: none; color: var(--ios-red); font-size: 15px; cursor: pointer; padding: 4px 0; }
        .ios-btns { display: flex; gap: 8px; padding: 0 16px 12px; flex-wrap: wrap; }
        .toast { position: fixed; bottom: 80px; left: 50%; transform: translateX(-50%); padding: 12px 24px; border-radius: 12px; font-size: 15px; z-index: 1000; animation: toastIn 0.3s ease; backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px); }
        .toast-success { background: rgba(52,199,89,0.9); color: white; }
        .toast-error { background: rgba(255,59,48,0.9); color: white; }
        @keyframes toastIn { from { transform: translate(-50%, 20px); opacity: 0; } to { transform: translate(-50%, 0); opacity: 1; } }
        .loading { text-align: center; padding: 40px; color: var(--ios-gray); font-size: 15px; }
        .ios-footer { text-align: center; padding: 16px; font-size: 13px; color: var(--ios-gray); }
        .ios-footer a { color: var(--ios-blue); text-decoration: none; }
        .ios-pw-group { display: flex; gap: 8px; padding: 0 16px 12px; }
        .ios-pw-group input { flex: 1; }
    </style>
</head>
<body>
    <div class="container">
        <div class="ios-header"><h1>监控</h1></div>
        <div class="ios-section">
            <div class="ios-stats">
                <div class="ios-stat"><div class="ios-stat-num" id="total">-</div><div class="ios-stat-label">总记录</div></div>
                <div class="ios-stat"><div class="ios-stat-num" id="users">-</div><div class="ios-stat-label">用户</div></div>
                <div class="ios-stat"><div class="ios-stat-num" id="groups">-</div><div class="ios-stat-label">群组</div></div>
            </div>
        </div>
        <div class="ios-section">
            <div class="ios-section-header">排行榜</div>
            <div class="ios-tabs">
                <button class="ios-tab active" onclick="switchTab('global')">总榜</button>
                <select class="ios-select" id="groupSelect" onchange="switchTab('group')"><option value="">选择群聊</option></select>
            </div>
            <div id="ranking"><div class="loading">加载中...</div></div>
        </div>
        <div class="ios-section">
            <div class="ios-section-header">记录</div>
            <div class="ios-search">
                <span class="ios-search-icon">&#128269;</span>
                <input class="ios-input" id="searchInput" placeholder="搜索..." oninput="filterRecords()">
            </div>
            <div class="ios-tabs">
                <button class="ios-tab active" onclick="switchRecordTab('all')">全部</button>
                <select class="ios-select" id="recordGroupSelect" onchange="switchRecordTab('group')"><option value="">选择群聊</option></select>
            </div>
            <div class="ios-btns">
                <button class="ios-btn ios-btn-gray" onclick="loadRecords()">刷新</button>
                <span id="adminBtns" style="display:none;">
                    <button class="ios-btn ios-btn-gray" onclick="selectAll()">全选</button>
                    <button class="ios-btn ios-btn-gray" onclick="selectNone()">取消</button>
                    <button class="ios-btn ios-btn-red" onclick="deleteSelected()" id="deleteSelectedBtn" style="display:none;">删除(<span id="selectedCount">0</span>)</button>
                </span>
            </div>
            <div id="records"><div class="loading">点击刷新</div></div>
        </div>
        <div class="ios-section">
            <div class="ios-section-header">管理</div>
            <div id="loginSection">
                <div class="ios-pw-group">
                    <input type="password" class="ios-input" id="loginPassword" placeholder="管理密码">
                    <button class="ios-btn ios-btn-primary" onclick="login()">登录</button>
                </div>
            </div>
            <div id="adminSection" style="display:none;">
                <div class="ios-btns">
                    <button class="ios-btn ios-btn-red" onclick="clearRecords()">清空全部</button>
                    <button class="ios-btn ios-btn-gray" onclick="logout()">退出</button>
                </div>
            </div>
        </div>
        <div class="ios-footer">
            <a href="/records">/records</a> · <a href="/stats">/stats</a> · <a href="https://github.com/huanxherta/syemamalielie">GitHub</a>
        </div>
    </div>
    <script>
        window.allRecords = [];
        window.currentRecordGroup = '';
        function getGroupName(r) {
            if (r.group_name && r.group_name.trim()) return r.group_name.trim();
            return '群' + r.group_id;
        }
        function switchRecordTab(type) {
            window.currentRecordGroup = type === 'all' ? '' : document.getElementById('recordGroupSelect').value;
            filterRecords();
        }
        function filterRecords() {
            const kw = document.getElementById('searchInput').value.toLowerCase();
            let records = window.allRecords || [];
            if (window.currentRecordGroup) records = records.filter(r => r.group_id === window.currentRecordGroup);
            if (kw) records = records.filter(r => 
                (r.message||'').toLowerCase().includes(kw) ||
                (r.user_name||'').toLowerCase().includes(kw) ||
                (r.user_id||'').toString().includes(kw) ||
                getGroupName(r).toLowerCase().includes(kw) ||
                (r.reason||'').toLowerCase().includes(kw)
            );
            renderRecords(records.slice(-50).reverse(), records.length);
        }
        function renderRecords(records, total) {
            const logged = !!window.adminToken;
            document.getElementById('records').innerHTML = records.length ? records.map((r,i) => `
                <div class="ios-row" id="record-${total-1-i}">
                    ${logged ? `<input type="checkbox" class="record-checkbox" data-index="${total-1-i}" onchange="toggleSelect(${total-1-i})">` : ''}
                    <img class="record-avatar" src="https://q.qlogo.cn/headimg_dl?dst_uin=${r.user_id}&spec=640" onerror="this.style.display='none'">
                    <div class="ios-row-content">
                        <div class="ios-row-title">${r.user_name}</div>
                        <div class="ios-row-subtitle">${getGroupName(r)} · ${new Date(r.time).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'})}</div>
                        <div style="font-size:15px;color:var(--ios-label);margin-top:6px;word-break:break-all;">${r.message}</div>
                        <div style="font-size:13px;color:var(--ios-orange);margin-top:4px;">${r.reason}</div>
                    </div>
                    ${logged ? `<button class="delete-text-btn" onclick="deleteSingle(${total-1-i})">删除</button>` : ''}
                </div>
            `).join('') : '<div class="loading">暂无记录</div>';
        }
        function updateRecordGroupSelect() {
            const map = {};
            (window.allRecords||[]).forEach(r => { if(!map[r.group_id]) map[r.group_id] = getGroupName(r); });
            const sel = document.getElementById('recordGroupSelect');
            sel.innerHTML = '<option value="">选择群聊</option>';
            Object.entries(map).forEach(([id,name]) => { sel.innerHTML += `<option value="${id}">${name}</option>`; });
        }
        async function loadRecords() {
            try {
                const {data} = await (await fetch('/records')).json();
                const nameMap = {};
                (data||[]).forEach(r => { if(r.group_name && r.group_name.trim()) nameMap[r.group_id] = r.group_name.trim(); });
                (data||[]).forEach(r => { if(!r.group_name && nameMap[r.group_id]) r.group_name = nameMap[r.group_id]; });
                window.allRecords = data || [];
                window.selectedIndices = new Set();
                document.getElementById('total').textContent = data.length;
                document.getElementById('users').textContent = new Set(data.map(r=>r.user_id)).size;
                document.getElementById('groups').textContent = new Set(data.map(r=>r.group_id)).size;
                updateRecordGroupSelect(); updateGroupSelect(); filterRecords(); updateDeleteBtn(); updateRanking('global');
            } catch(e) { document.getElementById('records').innerHTML = '<div class="loading">加载失败</div>'; }
        }
        function toggleSelect(i) { window.selectedIndices.has(i) ? window.selectedIndices.delete(i) : window.selectedIndices.add(i); updateDeleteBtn(); }
        function selectAll() { document.querySelectorAll('.record-checkbox').forEach(c=>{c.checked=true;window.selectedIndices.add(+c.dataset.index)}); updateDeleteBtn(); }
        function selectNone() { document.querySelectorAll('.record-checkbox').forEach(c=>c.checked=false); window.selectedIndices.clear(); updateDeleteBtn(); }
        function updateDeleteBtn() { const n=window.selectedIndices?.size||0; document.getElementById('selectedCount').textContent=n; document.getElementById('deleteSelectedBtn').style.display=n?'inline-block':'none'; }
        async function deleteSingle(i) { if(!window.adminToken) return showToast('请先登录','error'); if(!confirm('确定删除？')) return; await doDelete([i]); }
        async function deleteSelected() { if(!window.adminToken) return showToast('请先登录','error'); if(!window.selectedIndices.size) return showToast('请选择','error'); if(!confirm('删除'+window.selectedIndices.size+'条？')) return; await doDelete([...window.selectedIndices]); }
        async function doDelete(idx) { try{const{code,msg}=await(await fetch('/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:window.adminToken,indices:idx})})).json(); if(!code){showToast(msg,'success');loadRecords()}else{showToast(msg,'error');if(msg.includes('登录'))logout()}}catch(e){showToast('失败','error')} }
        function switchTab(t) { if(t==='global'){document.getElementById('groupSelect').value=''} updateRanking(t); }
        function maskQQ(q) { const s=String(q); return s.length<=4?s:s.slice(0,3)+'***'+s.slice(-3); }
        function updateRanking(type) {
            let recs = window.allRecords||[];
            if(type==='group'){const g=document.getElementById('groupSelect').value; recs=g?recs.filter(r=>r.group_id===g):[]}
            const stats={};
            recs.forEach(r=>{if(!stats[r.user_id]) stats[r.user_id]={qq:r.user_id,name:r.user_name,count:0,groups:{}}; stats[r.user_id].count++; stats[r.user_id].groups[r.group_id]=getGroupName(r)});
            const sorted=Object.entries(stats).sort((a,b)=>b[1].count-a[1].count).slice(0,10);
            document.getElementById('ranking').innerHTML=sorted.length?sorted.map(([uid,u],i)=>`
                <div class="ios-row">
                    <div class="ranking-badge rank-${i<3?i+1:'other'}">${i+1}</div>
                    <img class="ranking-avatar" src="https://q.qlogo.cn/headimg_dl?dst_uin=${u.qq}&spec=640" onerror="this.style.display='none'">
                    <div class="ios-row-content">
                        <div class="ios-row-title">${u.name}</div>
                        <div class="ios-row-subtitle">${maskQQ(u.qq)} · ${Object.keys(u.groups).length}个群</div>
                    </div>
                    <div class="ranking-count">${u.count}<span>次</span></div>
                </div>
            `).join(''):'<div class="loading">暂无数据</div>';
        }
        function updateGroupSelect() {
            const map={}; (window.allRecords||[]).forEach(r=>{if(!map[r.group_id])map[r.group_id]=getGroupName(r)});
            const s=document.getElementById('groupSelect'); s.innerHTML='<option value="">选择群聊</option>';
            Object.entries(map).forEach(([id,n])=>{s.innerHTML+=`<option value="${id}">${n}</option>`});
        }
        let adminToken=localStorage.getItem('adminToken')||'';
        window.adminToken=adminToken;
        function checkLogin() {
            adminToken=localStorage.getItem('adminToken')||''; window.adminToken=adminToken;
            document.getElementById('loginSection').style.display=adminToken?'none':'block';
            document.getElementById('adminSection').style.display=adminToken?'block':'none';
            document.getElementById('adminBtns').style.display=adminToken?'inline':'none';
            loadRecords();
        }
        async function login() {
            const pw=document.getElementById('loginPassword').value;
            if(!pw) return showToast('请输入密码','error');
            try{const{code,token,msg}=await(await fetch('/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:pw})})).json();
            if(!code){adminToken=token;localStorage.setItem('adminToken',token);checkLogin();showToast('登录成功','success');document.getElementById('loginPassword').value=''}
            else showToast(msg,'error')}catch(e){showToast('失败','error')}
        }
        function logout(){adminToken='';localStorage.removeItem('adminToken');checkLogin();showToast('已退出','success')}
        function showToast(msg,type){const t=document.createElement('div');t.className='toast toast-'+type;t.textContent=msg;document.body.appendChild(t);setTimeout(()=>t.remove(),2000)}
        async function clearRecords(){if(!confirm('清空全部？'))return;try{const{code,msg}=await(await fetch('/clear',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:adminToken})})).json();if(!code){showToast(msg,'success');loadRecords()}else{showToast(msg,'error');if(msg.includes('登录'))logout()}}catch(e){showToast('失败','error')}}
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
