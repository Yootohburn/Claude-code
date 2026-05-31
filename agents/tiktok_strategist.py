#!/usr/bin/env python3
"""
tiktok_strategist.py - TikTok Viral Strategy Agent Team

A specialized multi-agent system for TikTok content strategy.
Built on the s09 agent-teams pattern with domain-specific teammates:

  Lead (TikTok Strategist)
    ├── trend_scout     - Real-time trend analysis & FYP algorithm insights
    ├── content_writer  - Viral content scripts & hooks (3-sec rule)
    ├── influencer_mgr  - Creator ecosystem & UGC campaign management
    └── analytics_ai    - Performance data, KPIs, ROI measurement

Each teammate has a bespoke system prompt tuned to its TikTok domain.
Communication flows through JSONL inboxes (same MessageBus as s09).

Usage:
    python tiktok_strategist.py

Commands:
    /team    - Show team roster and status
    /inbox   - Drain lead's inbox
    q/exit   - Quit
"""

import json
import os
import subprocess
import threading
import time
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv(override=True)
if os.getenv("ANTHROPIC_BASE_URL"):
    os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)

WORKDIR = Path.cwd()
client = Anthropic(base_url=os.getenv("ANTHROPIC_BASE_URL"))
MODEL = os.environ.get("MODEL_ID", "claude-opus-4-5-20251001")
TEAM_DIR = WORKDIR / ".tiktok_team"
INBOX_DIR = TEAM_DIR / "inbox"

# ── Lead system prompt ──────────────────────────────────────────────────────
LEAD_SYSTEM = """คุณคือ **หัวหน้าทีม TikTok Strategist** ผู้เชี่ยวชาญด้านการเติบโตไวรัลบน TikTok

## ทีมของคุณ
- **trend_scout**    : วิเคราะห์เทรนด์แบบเรียลไทม์ + อัลกอริทึม FYP
- **content_writer** : เขียน script ไวรัล + hooks 3 วินาที
- **influencer_mgr** : จัดการ Creator Ecosystem + UGC campaigns
- **analytics_ai**   : วิเคราะห์ KPI, ROI, engagement rate

## กฎเหล็กที่คุณยึดถือ
1. ภัยคุกคาม 3 วินาที — ดึงความสนใจทันทีหรือตายทันที
2. เทรนด์ + แบรนด์ = ไม่ทิ้งเอกลักษณ์เพราะตามกระแส
3. FYP Algorithm — completion rate > 70% คือเป้าหมายเสมอ
4. Gen Z/Alpha first — ภาษา, สุนทรียะ, และ vibe ต้องตรง
5. Data-driven creativity — ความคิดสร้างสรรค์ที่วัดผลได้

## วิธีทำงาน
- ได้รับ brief จากผู้ใช้ → แจกงานให้ teammate ที่เหมาะสม
- รอ/อ่าน inbox จาก teammate → สังเคราะห์ผลลัพธ์
- ส่ง deliverable ที่ชัดเจน actionable ให้ผู้ใช้

## Content Allocation
- 40% การให้ความรู้  |  30% ความบันเทิง
- 20% แรงบันดาลใจ   |  10% โปรโมชั่น

พูดภาษาไทย ตอบด้วยพลังงานสูง กระชับ เน้นผลลัพธ์"""

VALID_MSG_TYPES = {
    "message", "broadcast", "shutdown_request",
    "shutdown_response", "plan_approval_response",
}

# ── Teammate system prompts ──────────────────────────────────────────────────
TEAMMATE_PROMPTS = {
    "trend_scout": """คุณคือ **Trend Scout** ผู้เชี่ยวชาญด้านการวิเคราะห์เทรนด์ TikTok

ความเชี่ยวชาญ:
- ติดตามเพลง/เสียงยอดนิยม, hashtag challenges, visual effects กำลังมาแรง
- วิเคราะห์ตรรกะ FYP Algorithm: watch time, replays, shares, comments weight
- ระบุ micro-trends ก่อนที่จะกลายเป็น mainstream (window 24-48 ชม.)
- วิเคราะห์คู่แข่งในอุตสาหกรรมเดียวกัน

Output ที่คุณส่งกลับ:
1. Top 5 เทรนด์ที่ควรใช้ตอนนี้
2. เพลง/เสียงที่แนะนำ (พร้อมอธิบายว่าทำไม)
3. Hashtag mix: ยอดนิยม + niche + brand (5-8 tags)
4. Timing ที่ดีที่สุดในการโพสต์
5. คู่แข่งที่ทำได้ดีและทำไม

ส่งผลกลับให้ lead ผ่าน send_message เสมอ""",

    "content_writer": """คุณคือ **Content Writer** ผู้สร้าง script ไวรัลและ hooks สำหรับ TikTok

สูตรที่คุณใช้:
- **3-Second Hook Formula**: Visual surprise | Bold statement | Curiosity gap
- **Story Arc**: Problem (0-3s) → Tension (3-15s) → Resolution (15-30s) → CTA (สุดท้าย)
- **Pattern Interrupt**: เปลี่ยนฉาก/มุมกล้องทุก 2-3 วินาที
- **Text Overlay**: ข้อความบนหน้าจอต้องอ่านได้ใน 1 วินาที

Output ที่คุณสร้าง:
1. Hook (3 ตัวเลือก — เลือกสุดโหด 1 ข้อ)
2. Script เต็ม (timestamped ทุก 5 วินาที)
3. Text overlay suggestions
4. CTA ที่ drive engagement
5. Caption + hashtag copy

สไตล์: Gen Z energy, authentic ไม่ corporate, กระชับ punch

ส่งผลกลับให้ lead ผ่าน send_message เสมอ""",

    "influencer_mgr": """คุณคือ **Influencer Manager** ผู้เชี่ยวชาญ Creator Economy บน TikTok

ระดับ Influencer ที่คุณจัดการ:
- Nano  (1K-10K)   : authenticity สูง, niche community
- Micro (10K-100K) : engagement rate ดีที่สุด ~5-8%
- Mid   (100K-1M)  : reach + credibility สมดุล
- Top   (1M+)      : mass awareness, ราคาสูง

รูปแบบ Collaboration:
- Product seeding, Paid promotion, Brand ambassador
- Hashtag challenges, Duet/Stitch campaigns
- Live collaborations, Account takeovers

Output ที่คุณส่ง:
1. Influencer tier mix ที่แนะนำ (พร้อม budget allocation)
2. Outreach script/template
3. Campaign brief template สำหรับ creator
4. KPI benchmarks (ROI target 4:1)
5. UGC activation plan

ส่งผลกลับให้ lead ผ่าน send_message เสมอ""",

    "analytics_ai": """คุณคือ **Analytics AI** ผู้วิเคราะห์ข้อมูลประสิทธิภาพ TikTok

KPI ที่คุณติดตาม:
- Engagement Rate: target >8% (industry avg 5.96%)
- Completion Rate: >70% สำหรับ branded content
- Hashtag Challenge Views: >1M views
- Influencer ROI: >4:1
- Organic follower growth: >15%/month
- Cross-platform CTR: >12%
- TikTok Shop conversion: >3%

Framework การวิเคราะห์:
1. Content performance breakdown (by type/format/length)
2. Audience retention curve analysis
3. A/B test recommendations
4. Algorithm signal interpretation
5. Competitor benchmarking

Output ที่คุณส่ง:
1. Performance report (ตัวเลขชัดเจน)
2. Insight ที่ actionable (ไม่ใช่แค่ข้อมูล)
3. Recommendations ranked by impact
4. Next sprint priorities

ส่งผลกลับให้ lead ผ่าน send_message เสมอ""",
}


# ── MessageBus ───────────────────────────────────────────────────────────────
class MessageBus:
    def __init__(self, inbox_dir: Path):
        self.dir = inbox_dir
        self.dir.mkdir(parents=True, exist_ok=True)

    def send(self, sender: str, to: str, content: str,
             msg_type: str = "message", extra: dict = None) -> str:
        if msg_type not in VALID_MSG_TYPES:
            return f"Error: Invalid type '{msg_type}'. Valid: {VALID_MSG_TYPES}"
        msg = {
            "type": msg_type,
            "from": sender,
            "content": content,
            "timestamp": time.time(),
        }
        if extra:
            msg.update(extra)
        with open(self.dir / f"{to}.jsonl", "a") as f:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")
        return f"Sent {msg_type} to {to}"

    def read_inbox(self, name: str) -> list:
        inbox_path = self.dir / f"{name}.jsonl"
        if not inbox_path.exists():
            return []
        messages = []
        for line in inbox_path.read_text().strip().splitlines():
            if line:
                messages.append(json.loads(line))
        inbox_path.write_text("")
        return messages

    def broadcast(self, sender: str, content: str, teammates: list) -> str:
        count = sum(
            1 for name in teammates
            if name != sender and not self.send(sender, name, content, "broadcast").startswith("Error")
        )
        return f"Broadcast to {count} teammates"


BUS = MessageBus(INBOX_DIR)


# ── TeammateManager ──────────────────────────────────────────────────────────
class TeammateManager:
    def __init__(self, team_dir: Path):
        self.dir = team_dir
        self.dir.mkdir(exist_ok=True)
        self.config_path = self.dir / "config.json"
        self.config = self._load_config()
        self.threads: dict[str, threading.Thread] = {}

    def _load_config(self) -> dict:
        if self.config_path.exists():
            return json.loads(self.config_path.read_text())
        return {"team_name": "tiktok_strategy_team", "members": []}

    def _save_config(self):
        self.config_path.write_text(json.dumps(self.config, indent=2, ensure_ascii=False))

    def _find_member(self, name: str) -> dict | None:
        return next((m for m in self.config["members"] if m["name"] == name), None)

    def spawn(self, name: str, role: str, prompt: str) -> str:
        member = self._find_member(name)
        if member:
            if member["status"] not in ("idle", "shutdown"):
                return f"Error: '{name}' is currently {member['status']}"
            member.update({"status": "working", "role": role})
        else:
            self.config["members"].append({"name": name, "role": role, "status": "working"})
        self._save_config()
        thread = threading.Thread(
            target=self._teammate_loop,
            args=(name, role, prompt),
            daemon=True,
        )
        self.threads[name] = thread
        thread.start()
        return f"Spawned '{name}' (role: {role})"

    def _teammate_loop(self, name: str, role: str, prompt: str):
        # Use domain-specific system prompt if available
        base_prompt = TEAMMATE_PROMPTS.get(name, f"You are '{name}', role: {role}.")
        sys_prompt = base_prompt + f"\n\nWorking directory: {WORKDIR}"
        messages = [{"role": "user", "content": prompt}]
        tools = self._teammate_tools()

        for _ in range(60):
            inbox = BUS.read_inbox(name)
            for msg in inbox:
                messages.append({"role": "user", "content": json.dumps(msg, ensure_ascii=False)})
            try:
                response = client.messages.create(
                    model=MODEL,
                    system=sys_prompt,
                    messages=messages,
                    tools=tools,
                    max_tokens=8000,
                )
            except Exception as e:
                print(f"  [{name}] Error: {e}")
                break

            messages.append({"role": "assistant", "content": response.content})
            if response.stop_reason != "tool_use":
                break

            results = []
            for block in response.content:
                if block.type == "tool_use":
                    output = self._exec(name, block.name, block.input)
                    print(f"  [{name}] {block.name}: {str(output)[:150]}")
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(output),
                    })
            messages.append({"role": "user", "content": results})

        member = self._find_member(name)
        if member and member["status"] != "shutdown":
            member["status"] = "idle"
            self._save_config()

    def _exec(self, sender: str, tool_name: str, args: dict) -> str:
        match tool_name:
            case "bash":       return _run_bash(args["command"])
            case "read_file":  return _run_read(args["path"])
            case "write_file": return _run_write(args["path"], args["content"])
            case "edit_file":  return _run_edit(args["path"], args["old_text"], args["new_text"])
            case "send_message":
                return BUS.send(sender, args["to"], args["content"], args.get("msg_type", "message"))
            case "read_inbox": return json.dumps(BUS.read_inbox(sender), indent=2, ensure_ascii=False)
            case _:            return f"Unknown tool: {tool_name}"

    def _teammate_tools(self) -> list:
        return [
            {"name": "bash", "description": "Run a shell command.",
             "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
            {"name": "read_file", "description": "Read file contents.",
             "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
            {"name": "write_file", "description": "Write content to file.",
             "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
            {"name": "edit_file", "description": "Replace exact text in file.",
             "input_schema": {"type": "object", "properties": {
                 "path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}
             }, "required": ["path", "old_text", "new_text"]}},
            {"name": "send_message", "description": "Send message to lead or teammate.",
             "input_schema": {"type": "object", "properties": {
                 "to": {"type": "string"}, "content": {"type": "string"},
                 "msg_type": {"type": "string", "enum": list(VALID_MSG_TYPES)}
             }, "required": ["to", "content"]}},
            {"name": "read_inbox", "description": "Read and drain your inbox.",
             "input_schema": {"type": "object", "properties": {}}},
        ]

    def list_all(self) -> str:
        if not self.config["members"]:
            return "No teammates yet."
        lines = [f"Team: {self.config['team_name']}"]
        for m in self.config["members"]:
            lines.append(f"  {m['name']} ({m['role']}): {m['status']}")
        return "\n".join(lines)

    def member_names(self) -> list:
        return [m["name"] for m in self.config["members"]]


TEAM = TeammateManager(TEAM_DIR)


# ── Base tool implementations ────────────────────────────────────────────────
def _safe_path(p: str) -> Path:
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {p}")
    return path


def _run_bash(command: str) -> str:
    blocked = ["rm -rf /", "sudo", "shutdown", "reboot"]
    if any(b in command for b in blocked):
        return "Error: Dangerous command blocked"
    try:
        r = subprocess.run(command, shell=True, cwd=WORKDIR,
                           capture_output=True, text=True, timeout=120)
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"


def _run_read(path: str) -> str:
    try:
        return _safe_path(path).read_text()[:50000]
    except Exception as e:
        return f"Error: {e}"


def _run_write(path: str, content: str) -> str:
    try:
        fp = _safe_path(path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error: {e}"


def _run_edit(path: str, old_text: str, new_text: str) -> str:
    try:
        fp = _safe_path(path)
        c = fp.read_text()
        if old_text not in c:
            return f"Error: Text not found in {path}"
        fp.write_text(c.replace(old_text, new_text, 1), encoding="utf-8")
        return f"Edited {path}"
    except Exception as e:
        return f"Error: {e}"


# ── Lead tools ───────────────────────────────────────────────────────────────
def _spawn_tiktok_team() -> str:
    """Auto-spawn the full TikTok strategy team."""
    results = []
    roster = [
        ("trend_scout",    "Trend Analyst",       "รอรับ brief จาก lead แล้ววิเคราะห์เทรนด์ TikTok ที่เหมาะสม"),
        ("content_writer", "Viral Content Writer", "รอรับ brief จาก lead แล้วสร้าง script และ hooks ไวรัล"),
        ("influencer_mgr", "Influencer Manager",   "รอรับ brief จาก lead แล้ววางแผน influencer collaboration"),
        ("analytics_ai",   "Analytics Specialist", "รอรับ brief จาก lead แล้ววิเคราะห์ KPI และ performance"),
    ]
    for name, role, prompt in roster:
        results.append(TEAM.spawn(name, role, prompt))
    return "\n".join(results)


TOOL_HANDLERS = {
    "bash":               lambda **kw: _run_bash(kw["command"]),
    "read_file":          lambda **kw: _run_read(kw["path"]),
    "write_file":         lambda **kw: _run_write(kw["path"], kw["content"]),
    "edit_file":          lambda **kw: _run_edit(kw["path"], kw["old_text"], kw["new_text"]),
    "spawn_teammate":     lambda **kw: TEAM.spawn(kw["name"], kw["role"], kw["prompt"]),
    "spawn_tiktok_team":  lambda **kw: _spawn_tiktok_team(),
    "list_teammates":     lambda **kw: TEAM.list_all(),
    "send_message":       lambda **kw: BUS.send("lead", kw["to"], kw["content"], kw.get("msg_type", "message")),
    "read_inbox":         lambda **kw: json.dumps(BUS.read_inbox("lead"), indent=2, ensure_ascii=False),
    "broadcast":          lambda **kw: BUS.broadcast("lead", kw["content"], TEAM.member_names()),
    "wait_for_replies":   lambda **kw: _wait_for_replies(kw.get("seconds", 10)),
}

TOOLS = [
    {"name": "bash", "description": "Run a shell command.",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
    {"name": "read_file", "description": "Read file contents.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "write_file", "description": "Write content to file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"name": "edit_file", "description": "Replace exact text in file.",
     "input_schema": {"type": "object", "properties": {
         "path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}
     }, "required": ["path", "old_text", "new_text"]}},
    {"name": "spawn_tiktok_team",
     "description": "Auto-spawn the full TikTok strategy team (trend_scout, content_writer, influencer_mgr, analytics_ai).",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "spawn_teammate",
     "description": "Spawn a single custom teammate.",
     "input_schema": {"type": "object", "properties": {
         "name": {"type": "string"}, "role": {"type": "string"}, "prompt": {"type": "string"}
     }, "required": ["name", "role", "prompt"]}},
    {"name": "list_teammates", "description": "List all teammates with name, role, status.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "send_message", "description": "Send a message to a teammate's inbox.",
     "input_schema": {"type": "object", "properties": {
         "to": {"type": "string"}, "content": {"type": "string"},
         "msg_type": {"type": "string", "enum": list(VALID_MSG_TYPES)}
     }, "required": ["to", "content"]}},
    {"name": "read_inbox", "description": "Read and drain the lead's inbox.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "broadcast", "description": "Send a message to all teammates.",
     "input_schema": {"type": "object", "properties": {"content": {"type": "string"}}, "required": ["content"]}},
    {"name": "wait_for_replies",
     "description": "Wait N seconds for teammates to reply, then read inbox.",
     "input_schema": {"type": "object", "properties": {"seconds": {"type": "integer"}}}},
]


def _wait_for_replies(seconds: int = 10) -> str:
    time.sleep(seconds)
    msgs = BUS.read_inbox("lead")
    if not msgs:
        return "No replies yet."
    return json.dumps(msgs, indent=2, ensure_ascii=False)


# ── Lead agent loop ──────────────────────────────────────────────────────────
def agent_loop(messages: list):
    while True:
        inbox = BUS.read_inbox("lead")
        if inbox:
            messages.append({
                "role": "user",
                "content": f"<inbox>{json.dumps(inbox, indent=2, ensure_ascii=False)}</inbox>",
            })
            messages.append({"role": "assistant", "content": "Noted inbox messages."})

        response = client.messages.create(
            model=MODEL,
            system=LEAD_SYSTEM,
            messages=messages,
            tools=TOOLS,
            max_tokens=8000,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            return

        results = []
        for block in response.content:
            if block.type == "tool_use":
                handler = TOOL_HANDLERS.get(block.name)
                try:
                    output = handler(**block.input) if handler else f"Unknown tool: {block.name}"
                except Exception as e:
                    output = f"Error: {e}"
                print(f"\033[33m> {block.name}\033[0m: {str(output)[:200]}")
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(output),
                })
        messages.append({"role": "user", "content": results})


# ── CLI entry point ──────────────────────────────────────────────────────────
BANNER = """
\033[35m╔══════════════════════════════════════════════════════════╗
║        TikTok Viral Strategy Agent Team  v1.0            ║
║  Lead + trend_scout | content_writer | influencer_mgr    ║
║                    | analytics_ai                         ║
╚══════════════════════════════════════════════════════════╝\033[0m
\033[36mพิมพ์ 'สร้างทีม' เพื่อ spawn ทีมทั้งหมด หรือถามได้เลย\033[0m
Commands: /team  /inbox  q=quit
"""

if __name__ == "__main__":
    print(BANNER)
    history = []
    while True:
        try:
            query = input("\033[35mTikTok Lead >> \033[0m").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye! Stay viral 🚀")
            break

        if query.lower() in ("q", "exit", ""):
            print("Goodbye! Stay viral 🚀")
            break
        if query == "/team":
            print(TEAM.list_all())
            continue
        if query == "/inbox":
            msgs = BUS.read_inbox("lead")
            print(json.dumps(msgs, indent=2, ensure_ascii=False) if msgs else "Inbox empty.")
            continue

        history.append({"role": "user", "content": query})
        agent_loop(history)

        response_content = history[-1]["content"]
        if isinstance(response_content, list):
            for block in response_content:
                if hasattr(block, "text"):
                    print(f"\n\033[32m{block.text}\033[0m")
        elif isinstance(response_content, str):
            print(f"\n\033[32m{response_content}\033[0m")
        print()
