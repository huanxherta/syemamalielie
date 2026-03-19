import json
import os
from datetime import datetime
from aiohttp import web
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger


@register(
    "astrbot_plugin_profanity_monitor",
    "huanxherta",
    "使用LLM智能识别群聊中的脏话，数据持久化并提供HTTP API查询。",
    "1.0.0",
)
class ProfanityMonitor(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.data_dir = os.path.join("data", "profanity_monitor")
        self.data_file = os.path.join(self.data_dir, "records.json")
        self.records = []
        self.http_runner = None
        self.http_site = None
        self.host = "0.0.0.0"
        self.port = 10050

    async def initialize(self):
        os.makedirs(self.data_dir, exist_ok=True)
        self._load_records()
        await self._start_http_server()

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
        app.router.add_get("/api/records", self._handle_get_records)
        app.router.add_get("/api/stats", self._handle_get_stats)
        self.http_runner = web.AppRunner(app)
        await self.http_runner.setup()
        self.http_site = web.TCPSite(self.http_runner, self.host, self.port)
        await self.http_site.start()
        logger.info(f"HTTP API 已启动: http://{self.host}:{self.port}")

    async def _handle_get_records(self, request: web.Request) -> web.Response:
        return web.json_response({"code": 0, "data": self.records})

    async def _handle_get_stats(self, request: web.Request) -> web.Response:
        stats = {}
        for r in self.records:
            uid = r.get("user_id", "unknown")
            if uid not in stats:
                stats[uid] = {"user_name": r.get("user_name", ""), "count": 0}
            stats[uid]["count"] += 1
        return web.json_response({"code": 0, "data": stats})

    @filter.on_message()
    async def on_group_message(self, event: AstrMessageEvent):
        if not event.is_group():
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
            llm_result = await self.context.get_using_provider().text_chat(
                prompt=prompt
            )
            response_text = llm_result.completion_text
            result = json.loads(response_text)
            if result.get("is_profanity"):
                record = {
                    "time": datetime.now().isoformat(),
                    "group_id": event.get_group_id(),
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
