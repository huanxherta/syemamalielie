# 群聊脏话监控插件

[![AstrBot](https://img.shields.io/badge/AstrBot-Plugin-blue)](https://github.com/AstrBotDevs/AstrBot)
[![Version](https://img.shields.io/badge/version-v1.1.0-green)]()

使用 LLM 智能识别群聊中的脏话，支持黑话、谐音、网络梗等变体识别，数据持久化并提供美观的 Web 管理界面。

## 功能特性

### 核心功能
- **智能识别**：使用 LLM 分析消息，支持直接脏话、谐音、拼音缩写、黑话、网络梗等
- **数据持久化**：记录存储在本地 JSON 文件中
- **分群管理**：支持配置只监控特定群聊或忽略某些群聊

### HTTP API（默认关闭，需在配置中开启）
- `GET /` - 美观的 Web 管理界面
- `GET /records` - 获取所有脏话记录
- `GET /stats` - 获取统计数据（分群、分人）
- `POST /login` - 管理员登录
- `POST /delete` - 删除记录（需登录）

### Web 管理界面
- 统计概览（总记录数、涉及用户、涉及群组）
- 脏话排行榜（总榜 / 按群筛选）
- 用户头像显示，QQ号脱敏
- 登录后可单独删除或批量删除记录
- 淡蓝色二次元风格 UI

### 指令
- `/profanity_stats` - 查询本群脏话统计
- `/profanity_clear` - 清空本群脏话记录

## 配置项

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| provider_id | string | 空 | 使用的 LLM 提供商（留空使用默认） |
| enable_groups | list | [] | 启用监控的群聊 ID（留空监控所有） |
| ignore_groups | list | [] | 忽略监控的群聊 ID |
| enable_http_api | bool | false | 是否启用 HTTP API |
| http_host | string | 0.0.0.0 | HTTP 服务器绑定地址 |
| http_port | int | 10050 | HTTP 服务器端口 |
| admin_password | string | m1234 | 管理员密码 |

## 安装

1. 将本仓库克隆到 AstrBot 的 `data/plugins/` 目录
2. 重启 AstrBot 或在 WebUI 中重载插件
3. 在插件配置中设置 LLM 提供商
4. 可选：开启 HTTP API 并设置密码

## 安全机制

- 登录失败 5 次后锁定 30 分钟（按 IP）
- Token 有效期 30 分钟，操作后自动续期
- 删除操作需登录验证
- QQ 号在界面中脱敏显示

## 更新日志

### v1.1.0 (2026-03-19)
- 增强脏话识别：支持谐音、拼音缩写、黑话、网络梗等
- 添加 Web 管理界面（淡蓝色二次元风格）
- 添加用户排行榜（支持按群筛选）
- 显示 QQ 头像，QQ 号脱敏显示
- 支持单独删除和批量删除记录
- 未登录时隐藏删除功能
- 分群排行榜改为群号下拉选择

### v1.0.0 (2026-03-19)
- 基础脏话监控功能
- LLM 智能识别
- 数据持久化存储
- HTTP API 查询接口
- 插件配置支持
- 登录验证和安全机制

## 许可证

[AGPL-3.0](LICENSE)
