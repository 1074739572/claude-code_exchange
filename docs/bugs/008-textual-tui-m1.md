# 008 — Textual TUI

## 痛点

经典 Rich 行模式难以做成「Kimi / 千问」式分区；终答与步骤拆开也不好回看历史。

## 锁定方案（grill-me）

| 项 | 选择 |
|----|------|
| 图标 | Emoji |
| 主区 | **单框聊天历史**（合并原 Steps+Answer） |
| 工具行 | H1 全进同一时间线 |
| 灌历史 | S1 启动加载当前 session |
| 顶栏 | 今日用量 + 周用量 |
| 聊天下方 | 🤖 模型 · 🧭 模式 · 状态（可点展开内联列表 B2） |
| 终答 | R3 Markdown；User/工具纯文本 |
| 权限 | Allow? 仍 Modal |

## 打断 / 退出（X1 · B2 · U1）

| 项 | 行为 |
|----|------|
| 退出 TUI | `request_cancel` + 吞掉 console 输出；等当前轮结束后再退 |
| 主按钮 | 空闲 **发送** / 忙碌 **停止**（Enter 同；Esc = 停止） |
| 停止效果 | 回滚本轮 history + 撕掉 `turn-live` 气泡 + 输入框预填原问题 |

```sh
python main.py              # 默认 TUI
python main.py --classic    # Rich 行模式
HARNESS_TUI=0 python main.py
```

## 欢迎页（Chat 置顶）

| 项 | 选择 |
|----|------|
| 位置 | 每次进入 Chat 顶部，下方接历史（W1） |
| Hero | 瘦身品牌行：小空心笑脸 + `HELLO` + 淡 tagline（宽屏并排 / 窄屏一行） |
| 配色 | 笑脸 `#E6B84D` · HELLO `#7FDBFF` · 引用卡琥珀竖线 |
| 每日一句 | **引用卡**：`TODAY` + 引号正文 + 右对齐来源；Hitokoto 队列 F1 |
| 动效 | 进场一次：品牌 → 引用卡 → 渐变细线 |
| 分隔 | 琥珀→亮青渐变 `━` 细线 |
| 会话表 | 已去掉 |

```sh
python -m harness.ui.tui.quotes status
python -m harness.ui.tui.quotes refill   # 手动灌满本地队列
python -m harness.ui.tui.quotes today
```

队列文件：`.project/daily_quotes.json`

## 关键文件

| 路径 | 作用 |
|------|------|
| `harness/ui/tui/app.py` | 布局 · 聊天流 · meta · picker |
| `harness/ui/tui/chat_history.py` | session → 聊天事件 |
| `harness/ui/tui/usage_bar.py` | 顶栏用量 |
| `harness/ui/tui/widgets.py` | 可点 MetaChip |
| `harness/ui/renderer.py` | TUI exclusive sink |
