# Claude Code Mods

ห้า Mod สำหรับ Claude Code (function-hook plugins) / Five Claude Code mods.

| Mod | ทำอะไร | ใช้ยังไง |
| --- | --- | --- |
| **next-steps** | หลัง Claude ตอบเสร็จ จะมีกล่องแนะนำ 3 ขั้นตอนถัดไปเหนือช่องพิมพ์ | กดตัวเลือก (หรือปุ่ม 1–3) เพื่อสั่งต่อทันที, กด **Dismiss** เพื่อปิด |
| **cache-keeper** | นับถอยหลังแคช 60 นาที, โทเคนที่ใช้/ขีดจำกัด, ค่าใช้จ่ายรอบล่าสุดและทั้งเซสชัน, เตือนเมื่อเหลือ 5 นาที | `/cachekeeper` เปิดแดชบอร์ด → **Session Handoff** สรุปงาน → **Clear and Continue** ล้างแชตแล้วเริ่มต่อด้วยสรุป |
| **recording-mode** | ซ่อนอีเมล, ยอดเงิน ($29, 500 บาท), API key, token, รหัสผ่าน บนหน้าจอ (ไฟล์จริงไม่ถูกแก้) | `/record on` เปิด, `/record off` ปิด |
| **goal-tracker** | แผงเช็กลิสต์งานย่อย, เวลาที่ใช้, % ความคืบหน้า แบบเรียลไทม์ | `/goal <เป้าหมาย>` เริ่มงาน, `/goals` เปิดแผง, ปุ่ม **All Tasks** ดูทุกเซสชัน |
| **collision-guard** | ก่อน Edit/Write/NotebookEdit ตรวจว่าไฟล์ถูกเซสชันอื่นแก้ใน 30 นาทีหรือไม่ แล้วถาม | เลือก **Proceed** / **Move to a worktree** / **Cancel** |

## Install

At the prompt of a Claude Code terminal session:

```
/plugin install next-steps --marketplace Yootohburn/Claude-code
```

Answer `y` to add the marketplace, then pick a scope. Repeat with `cache-keeper`, `recording-mode`, `goal-tracker`, `collision-guard`.

From a shell: `claude plugin install <mod> --marketplace Yootohburn/Claude-code`.
To try one from this checkout without installing: `claude --plugin-dir mods/<mod>`.

## Notes

- **next-steps** and **cache-keeper** (handoff) ask the model a short side question over the cached conversation, so they cost a little per use.
- **goal-tracker** and **collision-guard** share data between sessions through small JSON files in `~/.claude/mods-shared/`.
- If `/goal` already exists in your Claude Code, goal-tracker only tracks it; otherwise it adds its own `/goal`.
- Test: `claude plugin test mods/recording-mode`.
