# 智能体构建范式 — 从本项目提炼的实战架构

> 基于 learn-claude-code 12 个递进课程提炼，适用于任何领域的智能体构建。

---

## 核心哲学

> **模型本身就是智能体。你的代码只是给它工具，然后让开。**

不要过度工程化。不要预设工作流。不要用 if-else 替代模型的推理能力。
你的代码只做三件事：**提供能力、注入知识、保护上下文**。

---

## 一、不可动摇的基座：Agent Loop

所有智能体的内核是同一个循环，**从 s01 到 s12，循环本身始终不变**：

```python
def agent_loop(messages: list):
    while True:
        response = client.messages.create(
            model=MODEL, system=SYSTEM,
            messages=messages, tools=TOOLS, max_tokens=8000,
        )
        messages.append({"role": "assistant", "content": response.content})

        # 退出条件：模型不再调用工具
        if response.stop_reason != "tool_use":
            return

        # 执行工具，收集结果
        results = []
        for block in response.content:
            if block.type == "tool_use":
                output = TOOL_HANDLERS[block.name](**block.input)
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output,
                })
        messages.append({"role": "user", "content": results})
```

**关键设计决策：**
- `stop_reason != "tool_use"` 是唯一的退出条件 — 模型自己决定何时停止
- `messages` 是累积式列表 — 所有历史都在里面
- 工具结果作为 `user` 消息追加 — 这是 Anthropic API 的约定

---

## 二、递进式叠加范式（只在需要时添加）

### 层级 0：最小可用智能体

```
Model + 1 个工具（bash） + 1 个循环 = 一个智能体
```

**适用场景**：快速原型、脚本自动化、CLI 助手

```python
# 全部代码不到 30 行
TOOLS = [{"name": "bash", ...}]
TOOL_HANDLERS = {"bash": run_bash}
```

### 层级 1：多工具分发（s02 Tool Use）

```
新增工具 → 注册到 dispatch map → 循环不用动
```

**范式**：name → handler 映射表

```python
TOOL_HANDLERS = {
    "bash":       lambda **kw: run_bash(kw["command"]),
    "read_file":  lambda **kw: run_read(kw["path"]),
    "write_file": lambda **kw: run_write(kw["path"], kw["content"]),
    "edit_file":  lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"]),
}
```

**原则**：起步 3-5 个工具。只在模型因缺少能力而**反复失败**时才新增。

### 层级 2：规划与进度跟踪（s03 TodoWrite）

```
没有计划的 agent 走哪算哪 → 先列步骤再动手
```

**范式**：TodoManager + nag 提醒

```python
class TodoManager:
    def update(self, items: list) -> str: ...   # 写入/更新
    def render(self) -> str: ...                 # 渲染进度
    def has_open_items(self) -> bool: ...        # 检测未完成

# 在 agent_loop 里加 nag 逻辑
if TODO.has_open_items() and rounds_without_todo >= 3:
    results.insert(0, {"type": "text", "text": "<reminder>Update your todos.</reminder>"})
```

### 层级 3：子智能体隔离（s04 Subagent）

```
大任务拆小 → 每个子任务用独立 messages[] → 不污染主对话
```

**范式**：spawn → work → return summary

```python
def run_subagent(prompt: str, agent_type: str = "Explore") -> str:
    sub_msgs = [{"role": "user", "content": prompt}]
    for _ in range(30):  # 最大轮数限制
        resp = client.messages.create(model=MODEL, messages=sub_msgs, tools=sub_tools)
        sub_msgs.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason != "tool_use":
            break
        # ... 执行工具 ...
    return extract_summary(resp)  # 只返回摘要给主 agent
```

**关键**：子智能体有自己的 `messages[]`，主对话只收到一句摘要。

### 层级 4：按需知识注入（s05 Skills）

```
用到什么知识，临时加载什么知识 → 通过 tool_result 注入
```

**范式**：SKILL.md + SkillLoader

```
skills/
  agent-builder/
    SKILL.md          # YAML frontmatter + Markdown 正文
  code-review/
    SKILL.md
```

```python
class SkillLoader:
    def load(self, name: str) -> str:
        return f"<skill name=\"{name}\">\n{skill_body}\n</skill>"

# 作为工具注册
TOOL_HANDLERS["load_skill"] = lambda **kw: SKILLS.load(kw["name"])
```

**原则**：知识放在 tool_result 里按需注入，不要塞进 system prompt。

### 层级 5：上下文压缩（s06 Context Compact）

```
上下文总会满 → 三层压缩策略
```

**范式**：微压缩 → 自动压缩 → 手动压缩

```python
# 1. 微压缩：清除旧的 tool_result 内容
def microcompact(messages):
    # 只保留最近 3 个 tool_result，其余替换为 "[cleared]"

# 2. 自动压缩：token 超阈值时触发
if estimate_tokens(messages) > TOKEN_THRESHOLD:
    messages[:] = auto_compact(messages)  # LLM 总结 → 替换历史

# 3. 手动压缩：用户输入 /compact
```

---

## 三、生产级扩展范式

### 持久化任务系统（s07）

```
大目标拆成小任务 → 排好序 → 记在磁盘上
```

```python
class TaskManager:
    def create(self, subject, description) -> str: ...
    def update(self, tid, status, ...) -> str: ...
    def list_all(self) -> str: ...
    def claim(self, tid, owner) -> str: ...

# 任务存储为 .tasks/task_1.json, task_2.json, ...
# 支持依赖关系：blockedBy / blocks
```

### 后台任务（s08）

```
慢操作丢后台 → agent 继续想下一步
```

```python
class BackgroundManager:
    def run(self, command, timeout=120) -> str:
        # 守护线程执行
        threading.Thread(target=self._exec, ..., daemon=True).start()

    def drain(self) -> list:
        # 每轮循环前检查通知队列
        while not self.notifications.empty():
            notifs.append(self.notifications.get_nowait())
```

### 智能体团队（s09-s12）

```
s09: 持久化队友 + 异步 JSONL 邮箱
s10: 统一的 request-response 协议
s11: 自治 — 空闲轮询 + 自动认领任务
s12: Worktree 隔离 — 各干各的目录
```

```python
class TeammateManager:
    def spawn(self, name, role, prompt) -> str:
        # 每个队友是一个独立线程，有自己的 agent_loop
        threading.Thread(target=self._loop, args=(...), daemon=True).start()

class MessageBus:
    def send(self, sender, to, content, msg_type) -> str:
        # JSONL 文件作为邮箱：.team/inbox/{name}.jsonl
```

---

## 四、完整范式总结：从零到一的检查清单

```
阶段 1 — 先跑起来（1 小时）
├── [ ] 实现 agent_loop（while + stop_reason）
├── [ ] 注册 1 个工具（bash）
└── [ ] 加 REPL 交互入口

阶段 2 — 能干活（半天）
├── [ ] 扩展 tool dispatch map（read/write/edit）
├── [ ] 加 TodoManager 规划能力
└── [ ] 加 safe_path 安全检查

阶段 3 — 干得聪明（1 天）
├── [ ] 子智能体（隔离上下文）
├── [ ] 技能加载（按需知识注入）
└── [ ] 上下文压缩（三层策略）

阶段 4 — 干得多（2-3 天）
├── [ ] 文件持久化任务系统
├── [ ] 后台任务（守护线程 + 通知队列）
├── [ ] 团队协作（邮箱 + 协议）
└── [ ] Worktree 隔离执行
```

---

## 五、反模式警告

| 反模式 | 问题 | 正确做法 |
|--------|------|----------|
| 过度工程化 | 没需求就加功能 | 从最小开始，需要时才加 |
| 工具太多 | 模型选择困难 | 起步 3-5 个 |
| 硬编码工作流 | 无法适应变化 | 让模型自己推理流程 |
| 知识全塞 system prompt | 上下文浪费 | 按需加载 |
| 上下文不管理 | 模型迷失方向 | 三层压缩策略 |
| 不信任模型 | 用 if-else 替代推理 | 给工具，让模型决定 |

---

## 六、最小可复制模板

把下面的代码保存为 `my_agent.py`，填入 API key 即可运行：

```python
#!/usr/bin/env python3
"""最小智能体模板 — 基于 learn-claude-code 范式"""
import os, subprocess
from anthropic import Anthropic

client = Anthropic()
MODEL = "claude-sonnet-4-20250514"

SYSTEM = f"You are a helpful agent at {os.getcwd()}. Use tools to accomplish tasks."

TOOLS = [
    {"name": "bash", "description": "Run a shell command.",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
    {"name": "read_file", "description": "Read file contents.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "write_file", "description": "Write content to file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
]

def run_bash(cmd):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
        return (r.stdout + r.stderr).strip()[:50000] or "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout"

HANDLERS = {
    "bash":       lambda **kw: run_bash(kw["command"]),
    "read_file":  lambda **kw: open(kw["path"]).read()[:50000],
    "write_file": lambda **kw: (open(kw["path"], "w").write(kw["content"]), f"Wrote {kw['path']}")[1],
}

def agent_loop(messages):
    while True:
        resp = client.messages.create(model=MODEL, system=SYSTEM, messages=messages, tools=TOOLS, max_tokens=8000)
        messages.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason != "tool_use":
            return
        results = []
        for b in resp.content:
            if b.type == "tool_use":
                output = HANDLERS.get(b.name, lambda **kw: "Unknown tool")(**b.input)
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": str(output)})
        messages.append({"role": "user", "content": results})

if __name__ == "__main__":
    history = []
    while True:
        q = input(">> ")
        if q.strip().lower() in ("q", "exit", ""): break
        history.append({"role": "user", "content": q})
        agent_loop(history)
        for b in history[-1].get("content", []):
            if hasattr(b, "text"): print(b.text)
        print()
```

---

## 七、一句话记住

```
智能体 = while(模型想用工具) { 执行工具; 把结果喂回去; }
其余一切都是在这个循环上叠加策略。
循环不变，策略递增。
```

**模型就是智能体。我们的工作就是给它工具，然后让开。**
