# 群聊脏话监控插件

[![AstrBot](https://img.shields.io/badge/AstrBot-Plugin-blue)](https://github.com/AstrBotDevs/AstrBot)
[![Version](https://img.shields.io/badge/version-v1.2.0-green)]()

使用 LLM 智能识别群聊中的脏话，支持谐音、缩写、网络梗等变体识别，提供 iOS 风格 Web 管理界面。

## 功能特性

### 智能识别
- 直接脏话粗俗用语
- 谐音替代词（tm、卧槽、尼玛、特么等）
- 拼音首字母缩写（nmsl、wc 等）
- 网络黑话/隐语（祖安等侮辱性用法）
- 符号遮挡脏话（f\*\*k、s\*it）
- 结合语境判断，避免误判单个词

### Web 管理界面
- iOS 风格 UI，自动跟随系统深色模式
- 分页面切换（概览/记录/设置）
- 统计概览 + 脏话排行榜
- 搜索、分群筛选
- 单独删除/批量删除
- 电脑端双列布局适配
- 隐私保护（QQ号、群号打码）

### HTTP API
- `GET /` - Web 管理界面
- `GET /records` - 获取记录
- `GET /stats` - 获取统计
- `POST /login` - 登录
- `POST /delete` - 删除记录
- `POST /clear` - 清空记录

### Bot 指令
- `/profanity_stats` - 查询本群统计
- `/profanity_clear` - 清空本群记录

## 配置项

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| provider_id | string | 空 | LLM 提供商 |
| custom_prompt | text | 见默认 | 自定义分析 Prompt |
| enable_groups | list | [] | 启用监控的群聊 |
| ignore_groups | list | [] | 忽略监控的群聊 |
| enable_http_api | bool | false | 启用 HTTP API |
| http_host | string | 0.0.0.0 | API 绑定地址 |
| http_port | int | 10050 | API 端口 |
| admin_password | string | m1234 | 管理密码 |

## 安装

1. 克隆到 AstrBot 的 `data/plugins/` 目录
2. 重启 AstrBot 或在 WebUI 重载
3. 配置 LLM 提供商
4. 可选：开启 HTTP API

## 安全机制

- 登录失败 5 次锁定 30 分钟
- Token 有效期 30 分钟
- 删除需登录验证
- QQ 号、群号脱敏显示

## 更新日志

### v1.2.0 (2026-03-19)
- UI 重构为 iOS 风格，支持深色模式
- 分页面切换（概览/记录/设置）
- 电脑端双列布局适配
- 群号打码显示保护隐私
- 优化 prompt，提高识别准确性
- 自定义 prompt 配置

### v1.1.0 (2026-03-19)
- 增强脏话识别（谐音、缩写、黑话）
- Web 管理界面
- 用户排行榜
- QQ 头像显示
- 单独删除/批量删除
- 分群筛选

### v1.0.0 (2026-03-19)
- 基础脏话监控
- LLM 智能识别
- 数据持久化
- HTTP API
- 插件配置
- 登录验证

## 许可证

[AGPL-3.0](LICENSE)
