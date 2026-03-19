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
            "你是一个内容审核助手，请判断以下消息是否属于不当言论。\n"
            "不当言论包括：粗俗用语、人身攻击、侮辱性称呼、恶意诅咒等。\n"
            "注意区分：1) @功能提及用户 2) 用户昵称本身 3) 正常玩笑或网络用语\n\n"
            '请仅返回JSON格式：{"is_profanity": true/false, "reason": "简短原因"}\n\n'
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
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>群聊脏话监控</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
:root{--bg:#F2F2F7;--card:rgba(255,255,255,.82);--blue:#007AFF;--red:#FF3B30;--green:#34C759;--orange:#FF9500;--gray:#8E8E93;--gray2:#AEAEB2;--gray5:#E5E5EA;--gray6:#F2F2F7;--label:#000;--label2:#3C3C43;--sep:rgba(60,60,67,.12)}
@media(prefers-color-scheme:dark){:root{--bg:#000;--card:rgba(44,44,46,.82);--blue:#0A84FF;--red:#FF453A;--green:#30D158;--orange:#FF9F0A;--gray5:#38383A;--gray6:#1C1C1E;--label:#fff;--label2:#EBEBF5;--sep:rgba(84,84,88,.65)}}
body{font-family:-apple-system,BlinkMacSystemFont,'SF Pro Text','PingFang SC',sans-serif;background:var(--bg);min-height:100vh;padding:0 0 80px;-webkit-font-smoothing:antialiased}
.c{max-width:428px;margin:0 auto;padding:20px 16px}
.hdr{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}
.hdr h1{font-size:34px;font-weight:700;color:var(--label)}
.sec{background:var(--card);backdrop-filter:blur(40px);border-radius:13px;overflow:hidden;margin-bottom:16px}
.sec-h{padding:12px 16px 8px;font-size:13px;color:var(--gray);text-transform:uppercase}
.row{display:flex;align-items:center;padding:12px 16px;position:relative}
.row:not(:last-child)::after{content:'';position:absolute;bottom:0;left:54px;right:16px;height:.5px;background:var(--sep)}
.row-c{flex:1}
.row-t{font-size:17px;color:var(--label)}
.row-s{font-size:14px;color:var(--gray);margin-top:2px}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--sep)}
.stat{background:var(--card);padding:16px 8px;text-align:center}
.stat-n{font-size:28px;font-weight:600;color:var(--blue)}
.stat-l{font-size:12px;color:var(--gray);margin-top:4px}
.btn{display:inline-block;padding:8px 16px;border-radius:8px;font-size:15px;border:none;cursor:pointer;transition:all .15s}
.btn:active{transform:scale(.97);opacity:.7}
.btn-p{background:var(--blue);color:#fff}
.btn-r{background:var(--red);color:#fff}
.btn-g{background:var(--gray5);color:var(--label)}
.input{width:100%;padding:10px 12px;border:none;border-radius:8px;background:var(--gray6);font-size:17px;outline:none;color:var(--label)}
.input::placeholder{color:var(--gray2)}
.search{position:relative;margin:0 16px 12px}
.search input{padding-left:36px}
.search-i{position:absolute;left:10px;top:50%;transform:translateY(-50%);color:var(--gray)}
.tabs{display:flex;padding:0 16px 12px;gap:8px;flex-wrap:wrap}
.tab{padding:6px 12px;border-radius:16px;font-size:13px;font-weight:500;background:var(--gray5);color:var(--label2);cursor:pointer;border:none}
.tab.on{background:var(--blue);color:#fff}
.sel{padding:6px 12px;border-radius:16px;font-size:13px;background:var(--gray5);color:var(--label2);border:none;cursor:pointer;outline:none}
.av{width:44px;height:44px;border-radius:50%;margin-right:12px;object-fit:cover}
.badge{width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:600;margin-right:12px}
.r1{background:linear-gradient(135deg,#FFD700,#FFA500);color:#fff}
.r2{background:linear-gradient(135deg,#C0C0C0,#A0A0A0);color:#fff}
.r3{background:linear-gradient(135deg,#CD7F32,#8B4513);color:#fff}
.ro{background:var(--gray5);color:var(--gray)}
.cnt{font-size:20px;font-weight:600;color:var(--label)}
.cnt span{font-size:12px;color:var(--gray)}
.r-av{width:40px;height:40px;border-radius:50%;margin-right:12px;flex-shrink:0;object-fit:cover}
.cb{width:20px;height:20px;margin-right:12px;accent-color:var(--blue);flex-shrink:0}
.del{background:none;border:none;color:var(--red);font-size:15px;cursor:pointer}
.btns{display:flex;gap:8px;padding:0 16px 12px;flex-wrap:wrap}
.toast{position:fixed;bottom:80px;left:50%;transform:translateX(-50%);padding:12px 24px;border-radius:12px;font-size:15px;z-index:1000;animation:tIn .3s;backdrop-filter:blur(20px)}
.toast-s{background:rgba(52,199,89,.9);color:#fff}
.toast-e{background:rgba(255,59,48,.9);color:#fff}
@keyframes tIn{from{transform:translate(-50%,20px);opacity:0}to{transform:translate(-50%,0);opacity:1}}
.ld{text-align:center;padding:40px;color:var(--gray)}
.pw{display:flex;gap:8px;padding:0 16px 12px}
.pw input{flex:1}
.tabbar{position:fixed;bottom:0;left:0;right:0;background:var(--card);backdrop-filter:blur(20px);border-top:.5px solid var(--sep);display:flex;justify-content:space-around;padding:8px 0 env(safe-area-inset-bottom)}
.tabbar-i{display:flex;flex-direction:column;align-items:center;gap:2px;background:none;border:none;cursor:pointer;padding:4px 16px;color:var(--gray)}
.tabbar-i.on{color:var(--blue)}
.tabbar-ic{font-size:22px}
.tabbar-l{font-size:10px;font-weight:500}
.page{display:none}.page.on{display:block}
</style>
</head>
<body>
<div class="c">
<div id="p-home" class="page on">
<div class="hdr"><h1>监控</h1></div>
<div class="sec"><div class="stats"><div class="stat"><div class="stat-n" id="total">-</div><div class="stat-l">总记录</div></div><div class="stat"><div class="stat-n" id="users">-</div><div class="stat-l">用户</div></div><div class="stat"><div class="stat-n" id="groups">-</div><div class="stat-l">群组</div></div></div></div>
<div class="sec"><div class="sec-h">排行榜</div><div class="tabs"><button class="tab on" onclick="switchTab('global',this)">总榜</button><select class="sel" id="groupSelect" onchange="switchTab('group')"><option value="">选择群聊</option></select></div><div id="ranking"><div class="ld">加载中...</div></div></div>
</div>
<div id="p-record" class="page">
<div class="hdr"><h1>记录</h1></div>
<div class="sec"><div class="search"><span class="search-i">&#128269;</span><input class="input" id="searchInput" placeholder="搜索..." oninput="filterRecords()"></div><div class="tabs"><button class="tab on" onclick="switchRT('all',this)">全部</button><select class="sel" id="recordGroupSelect" onchange="switchRT('group')"><option value="">选择群聊</option></select></div><div class="btns"><button class="btn btn-g" onclick="loadRecords()">刷新</button><span id="adminBtns" style="display:none"><button class="btn btn-g" onclick="selectAll()">全选</button><button class="btn btn-g" onclick="selectNone()">取消</button><button class="btn btn-r" onclick="deleteSelected()" id="deleteSelectedBtn" style="display:none">删除(<span id="selectedCount">0</span>)</button></span></div><div id="records"><div class="ld">点击刷新</div></div></div>
</div>
<div id="p-setting" class="page">
<div class="hdr"><h1>设置</h1></div>
<div class="sec"><div class="sec-h">管理</div><div id="loginSection"><div class="pw"><input type="password" class="input" id="loginPassword" placeholder="管理密码"><button class="btn btn-p" onclick="login()">登录</button></div></div><div id="adminSection" style="display:none"><div class="btns"><button class="btn btn-r" onclick="clearRecords()">清空全部</button><button class="btn btn-g" onclick="logout()">退出</button></div></div></div>
<div class="sec"><div class="sec-h">API</div><div class="row" onclick="location.href='/records'"><div class="row-c"><div class="row-t">/records</div><div class="row-s">获取记录</div></div></div><div class="row" onclick="location.href='/stats'"><div class="row-c"><div class="row-t">/stats</div><div class="row-s">获取统计</div></div></div></div>
</div>
</div>
<div class="tabbar"><button class="tabbar-i on" onclick="switchPage('home',this)"><span class="tabbar-ic">&#128200;</span><span class="tabbar-l">概览</span></button><button class="tabbar-i" onclick="switchPage('record',this)"><span class="tabbar-ic">&#128196;</span><span class="tabbar-l">记录</span></button><button class="tabbar-i" onclick="switchPage('setting',this)"><span class="tabbar-ic">&#9881;</span><span class="tabbar-l">设置</span></button></div>
<script>
function switchPage(p,el){document.querySelectorAll('.page').forEach(x=>x.classList.remove('on'));document.querySelectorAll('.tabbar-i').forEach(x=>x.classList.remove('on'));document.getElementById('p-'+p).classList.add('on');el.classList.add('on')}
window.allRecords=[];window.crg='';
function switchRT(t,el){window.crg=t==='all'?'':document.getElementById('recordGroupSelect').value;if(el){document.querySelectorAll('#p-record .tab').forEach(x=>x.classList.remove('on'));el.classList.add('on')}filterRecords()}
function filterRecords(){const kw=document.getElementById('searchInput').value.toLowerCase();let rs=window.allRecords||[];if(window.crg)rs=rs.filter(r=>r.group_id===window.crg);if(kw)rs=rs.filter(r=>(r.message||'').toLowerCase().includes(kw)||(r.user_name||'').toLowerCase().includes(kw)||r.group_id.toString().includes(kw)||(r.reason||'').toLowerCase().includes(kw));renderRecords(rs.slice(-50).reverse(),rs.length)}
function renderRecords(rs,total){const lg=!!window.adminToken;document.getElementById('records').innerHTML=rs.length?rs.map((r,i)=>`<div class="row" id="record-${total-1-i}">${lg?`<input type="checkbox" class="cb" data-index="${total-1-i}" onchange="toggleSelect(${total-1-i})">`:''}<img class="r-av" src="https://q.qlogo.cn/headimg_dl?dst_uin=${r.user_id}&spec=640" onerror="this.style.display='none'"><div class="row-c"><div class="row-t">${r.user_name}</div><div class="row-s">群${r.group_id} · ${new Date(r.time).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'})}</div><div style="font-size:15px;color:var(--label);margin-top:6px;word-break:break-all">${r.message}</div><div style="font-size:13px;color:var(--orange);margin-top:4px">${r.reason}</div></div>${lg?`<button class="del" onclick="deleteSingle(${total-1-i})">删除</button>`:''}</div>`).join(''):'<div class="ld">暂无记录</div>'}
function updateRGS(){const m={};(window.allRecords||[]).forEach(r=>{m[r.group_id]=1});const s=document.getElementById('recordGroupSelect');s.innerHTML='<option value="">选择群聊</option>';Object.keys(m).forEach(id=>{s.innerHTML+=`<option value="${id}">群${id}</option>`})}
async function loadRecords(){try{const{data}=await(await fetch('/records')).json();window.allRecords=data||[];window.selectedIndices=new Set();document.getElementById('total').textContent=data.length;document.getElementById('users').textContent=new Set(data.map(r=>r.user_id)).size;document.getElementById('groups').textContent=new Set(data.map(r=>r.group_id)).size;updateRGS();updateGS();filterRecords();updateDB();updateRanking('global')}catch(e){document.getElementById('records').innerHTML='<div class="ld">加载失败</div>'}}
function toggleSelect(i){window.selectedIndices.has(i)?window.selectedIndices.delete(i):window.selectedIndices.add(i);updateDB()}
function selectAll(){document.querySelectorAll('.cb').forEach(c=>{c.checked=true;window.selectedIndices.add(+c.dataset.index)});updateDB()}
function selectNone(){document.querySelectorAll('.cb').forEach(c=>c.checked=false);window.selectedIndices.clear();updateDB()}
function updateDB(){const n=window.selectedIndices?.size||0;document.getElementById('selectedCount').textContent=n;document.getElementById('deleteSelectedBtn').style.display=n?'inline-block':'none'}
async function deleteSingle(i){if(!window.adminToken)return showToast('请先登录','error');if(!confirm('确定删除？'))return;await doDelete([i])}
async function deleteSelected(){if(!window.adminToken)return showToast('请先登录','error');if(!window.selectedIndices.size)return showToast('请选择','error');if(!confirm('删除'+window.selectedIndices.size+'条？'))return;await doDelete([...window.selectedIndices])}
async function doDelete(idx){try{const{code,msg}=await(await fetch('/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:window.adminToken,indices:idx})})).json();if(!code){showToast(msg,'success');loadRecords()}else{showToast(msg,'error');if(msg.includes('登录'))logout()}}catch(e){showToast('失败','error')}}
function switchTab(t,el){if(t==='global')document.getElementById('groupSelect').value='';if(el){document.querySelectorAll('#p-home .tab').forEach(x=>x.classList.remove('on'));el.classList.add('on')}updateRanking(t)}
function maskQQ(q){const s=String(q);return s.length<=4?s:s.slice(0,3)+'***'+s.slice(-3)}
function updateRanking(type){let rs=window.allRecords||[];if(type==='group'){const g=document.getElementById('groupSelect').value;rs=g?rs.filter(r=>r.group_id===g):[]}const st={};rs.forEach(r=>{if(!st[r.user_id])st[r.user_id]={qq:r.user_id,name:r.user_name,count:0,groups:{}};st[r.user_id].count++;st[r.user_id].groups[r.group_id]=1});const sorted=Object.entries(st).sort((a,b)=>b[1].count-a[1].count).slice(0,10);document.getElementById('ranking').innerHTML=sorted.length?sorted.map(([uid,u],i)=>`<div class="row"><div class="badge r${i<3?i+1:'o'}">${i+1}</div><img class="av" src="https://q.qlogo.cn/headimg_dl?dst_uin=${u.qq}&spec=640" onerror="this.style.display='none'"><div class="row-c"><div class="row-t">${u.name}</div><div class="row-s">${maskQQ(u.qq)} · ${Object.keys(u.groups).length}个群</div></div><div class="cnt">${u.count}<span>次</span></div></div>`).join(''):'<div class="ld">暂无数据</div>'}
function updateGS(){const m={};(window.allRecords||[]).forEach(r=>{m[r.group_id]=1});const s=document.getElementById('groupSelect');s.innerHTML='<option value="">选择群聊</option>';Object.keys(m).forEach(id=>{s.innerHTML+=`<option value="${id}">群${id}</option>`})}
let adminToken=localStorage.getItem('adminToken')||'';window.adminToken=adminToken;
function checkLogin(){adminToken=localStorage.getItem('adminToken')||'';window.adminToken=adminToken;document.getElementById('loginSection').style.display=adminToken?'none':'block';document.getElementById('adminSection').style.display=adminToken?'block':'none';document.getElementById('adminBtns').style.display=adminToken?'inline':'none';loadRecords()}
async function login(){const pw=document.getElementById('loginPassword').value;if(!pw)return showToast('请输入密码','error');try{const{code,token,msg}=await(await fetch('/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:pw})})).json();if(!code){adminToken=token;localStorage.setItem('adminToken',token);checkLogin();showToast('登录成功','success');document.getElementById('loginPassword').value=''}else showToast(msg,'error')}catch(e){showToast('失败','error')}}
function logout(){adminToken='';localStorage.removeItem('adminToken');checkLogin();showToast('已退出','success')}
function showToast(msg,type){const t=document.createElement('div');t.className='toast toast-'+type;t.textContent=msg;document.body.appendChild(t);setTimeout(()=>t.remove(),2000)}
async function clearRecords(){if(!confirm('清空全部？'))return;try{const{code,msg}=await(await fetch('/clear',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:adminToken})})).json();if(!code){showToast(msg,'success');loadRecords()}else{showToast(msg,'error');if(msg.includes('登录'))logout()}}catch(e){showToast('失败','error')}}
checkLogin();
</script>
</body></html>"""
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
