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
| 主按钮 | 空闲 **发送** / 忙碌 **停止**（Enter / Ctrl+Enter 同；Esc = 停止） |
| Ctrl+C | **不退出**（吞掉 Textual help_quit）；复制用终端拖选 / Ctrl+Shift+C；退出用 Ctrl+Q |
| 输入区 | **TextArea** 多行：Enter 发送；**Shift+Enter** 换行；高度约 3–8 行 |
| 停止效果 | 回滚本轮 history + 撕掉 `turn-live` 气泡 + 输入框预填原问题 |
| 终端复位 | 启动前 / 退出后 / `atexit` 清鼠标上报与 alt-screen（防 `^[[<…M` 花屏） |

若仍花屏：关掉该终端标签，**新开**一个再 `python main.py`（同一脏标签里重启不够时）。

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

## 会话斜杠（与 classic 对齐）

| 命令 | TUI 行为 |
|------|----------|
| `/resume` | Chat 列出会话 + 内联 picker 切换 |
| `/resume <N>` | 切换会话，`reload_session_view` 重灌 Chat |
| `/resume project` | 注入 `[Resume context]` |
| `/resume delete <N>` | 删会话目录（删当前则开新会话） |
| `/clear` | 清对话 + 默认清 `state.json` |
| `/clear session` | 只清对话，保留长任务 |
| `/skill` | 列 skill + picker；`/skill <name>` 注入全文（Chat 仅短提示） |

忙碌中禁止切换；需先 Stop。

## 关键文件

| 路径 | 作用 |
|------|------|
| `harness/ui/tui/app.py` | 布局 · 聊天流 · meta · picker · `reload_session_view` |
| `harness/ui/tui/commands.py` | `/model` `/mode` `/resume` `/clear` |
| `harness/ui/tui/chat_history.py` | session → 聊天事件 |
| `harness/ui/tui/usage_bar.py` | 顶栏用量 |
| `harness/ui/tui/widgets.py` | 可点 MetaChip |
| `harness/ui/renderer.py` | TUI exclusive sink |
