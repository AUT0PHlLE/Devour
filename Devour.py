import asyncio
import random
import json
import os
import time
from datetime import datetime
from pyrogram import Client, filters, compose
from pyrogram.enums import ChatType
from pyrogram.errors import UserNotParticipant

# ========== CONFIG ==========
API_ID = 123456      # Your app's API ID (SAME for all)
API_HASH = "your_api_hash"   # Your app's hash (SAME for all)
SESSIONS = []  # Will be loaded from devour.json
SUDO_USERS = [6836139884]
DELAY_RANGE = (1, 1.5)   # seconds
DATA_FILE = "devour.json"

# ========== SHARED STATE ==========
REPLY_TEXT1 = {}
REPLY_TEXT2 = {}
DEVOUR_STATE = {}    # {user_id: {step, ...}}
LAST_SCAN = {}       # {chat_id: ...}

def load_data():
    global REPLY_TEXT1, REPLY_TEXT2, LAST_SCAN, SESSIONS
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
            REPLY_TEXT1 = {int(k): v for k,v in data.get('reply_text1', {}).items()}
            REPLY_TEXT2 = {int(k): v for k,v in data.get('reply_text2', {}).items()}
            LAST_SCAN = {int(k): v for k,v in data.get('last_scan', {}).items()}
            SESSIONS = data.get('sessions', [])
    else:
        SESSIONS = []
        save_data()

def save_data():
    try:
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
    except:
        data = {'reply_text1': {}, 'reply_text2': {}, 'execution_logs': [], 'last_scan': {}, 'sessions': []}
    data['reply_text1'] = {str(k): v for k,v in REPLY_TEXT1.items()}
    data['reply_text2'] = {str(k): v for k,v in REPLY_TEXT2.items()}
    data['last_scan'] = {str(k): v for k,v in LAST_SCAN.items()}
    data['sessions'] = SESSIONS
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def save_execution_log(chat_id, msg_links, texts, mode):
    try:
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
    except:
        data = {'reply_text1': {}, 'reply_text2': {}, 'execution_logs': [], 'last_scan': {}, 'sessions': []}
    log = {
        "chat_id": chat_id,
        "mode": mode,
        "texts": texts,
        "message_links": msg_links,
        "count": len(msg_links),
        "timestamp": time.time()
    }
    data.setdefault("execution_logs", []).append(log)
    data['reply_text1'] = {str(k): v for k,v in REPLY_TEXT1.items()}
    data['reply_text2'] = {str(k): v for k,v in REPLY_TEXT2.items()}
    data['last_scan'] = {str(k): v for k,v in LAST_SCAN.items()}
    data['sessions'] = SESSIONS
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def owner_or_sudo(_, __, m):
    return m.from_user and (m.from_user.id in SUDO_USERS or m.outgoing)
sudo_filter = filters.create(owner_or_sudo)

def is_dm(message):
    return (message.chat.type==ChatType.PRIVATE)

def register_handlers(app):
    @app.on_message(filters.command("devour") & sudo_filter & filters.private)
    async def devour_start(client, message):
        user_id = message.from_user.id
        DEVOUR_STATE[user_id] = {"step": "await_target"}
        await message.reply("Send the link or @username of the target chat.")

    @app.on_message(sudo_filter & filters.private & ~filters.command([
        "devour", "settext1", "settext2", "help", "cancel", "stop", "joinchat", "addacc"]))
    async def devour_menu(client, message):
        user_id = message.from_user.id
        if user_id not in DEVOUR_STATE:
            return
        state = DEVOUR_STATE[user_id]

        if state["step"] == "await_target":
            chat_link = message.text.strip()
            try:
                target = await client.get_chat(chat_link)
                if not target:
                    await message.reply("❌ Could not find that chat.")
                    del DEVOUR_STATE[user_id]
                    return
                try:
                    member = await client.get_chat_member(target.id, "me")
                    if not member:
                        await message.reply('❌ Not a member of this group. Join with /joinchat <invite link>.')
                        del DEVOUR_STATE[user_id]
                        return
                except UserNotParticipant:
                    await message.reply('❌ Not a member of this group. Join with /joinchat <invite link>.')
                    del DEVOUR_STATE[user_id]
                    return

                scan = LAST_SCAN.get(target.id)
                scan_info = f"
   💾 {scan['count']} users cached" if scan else "
   ❌ No cached scan"
                state.update({
                    "step": "main_menu",
                    "target_name": target.title or str(target.id),
                    "chat_id": target.id
                })
                options_txt = (
                    f"**Target:** {target.title or target.id} (`{chat_link}`)
"
                    f"{scan_info}

"
                    "Choose option:
"
                    "1️⃣ Scan all users (text1)
"
                    "2️⃣ Message links
"
                    "3️⃣ Previous scan data
"
                    "4️⃣ 2 texts (/settext1 and /settext2)
"
                    "5️⃣ Temporary text (one-time, not saved)
"
                    "6️⃣ Rob mode (/rob commands)"
                )
                await message.reply(options_txt)
            except Exception as e:
                await message.reply(f"❌ Error accessing chat: {e}")
                del DEVOUR_STATE[user_id]

        elif state["step"] == "main_menu":
            opt = message.text.strip()
            if opt == "1":
                state["step"], chat_id = "scanning", state["chat_id"]
                status = await message.reply(f"🔍 Scanning all users in **{state['target_name']}**...")
                user_msgs = {}
                async for msg in client.get_chat_history(chat_id):
                    if (msg.from_user and not msg.from_user.is_bot
                        and not msg.from_user.is_deleted):
                        if msg.from_user.id not in user_msgs:
                            user_msgs[msg.from_user.id] = msg.id
                last_count = len(user_msgs)
                LAST_SCAN[chat_id] = {'user_msgs': user_msgs, 'count': last_count, 'timestamp': time.time()}
                save_data()
                state["step"] = "await_count"
                state["user_msgs"] = user_msgs
                await status.edit(f"✅ Found **{last_count}** users in **{state['target_name']}**.

How many to execute? Reply with number.")

            elif opt == "2":
                state.update({"step": "await_links"})
                await message.reply("📎 Send message links (one per line).")

            elif opt == "3":
                scan = LAST_SCAN.get(state["chat_id"])
                if not scan or not scan.get("user_msgs"):
                    await message.reply("❌ No cached previous scan data. Use option 1 first.")
                    del DEVOUR_STATE[user_id]
                    return
                state["user_msgs"], state["step"] = scan["user_msgs"], "await_count"
                await message.reply(f"💾 Loaded cached data (**{len(scan['user_msgs'])} users**).

How many to execute? Reply with number.")

            elif opt == "4":
                state["step"] = "wait_2text_prepare"
                await message.reply("📝 Set texts with `/settext1 <text>` and `/settext2 <text>`.
When ready, reply with number of users to execute.")

            elif opt == "5":
                state["step"] = "await_temptext"
                await message.reply("📝 Send `/temptext 1 <text>` for one reply, or `/temptext 2 <text>` for two identical replies.")

            elif opt == "6":
                state["step"] = "rob_select"
                await message.reply("💰 Rob Mode

Select rob amount:
1️⃣ /rob 200
2️⃣ /rob 150
3️⃣ /rob 100
Reply with 1, 2, or 3.")

            else:
                await message.reply("❌ Reply `1`, `2`, `3`, `4`, `5`, or `6`.")

        elif state["step"] == "rob_select":
            opt = message.text.strip()
            rob_commands = {"1": "/rob 200", "2": "/rob 150", "3": "/rob 100"}
            if opt in rob_commands:
                state["rob_cmd"] = rob_commands[opt]
                state["step"] = "rob_count"
                await message.reply(f"✅ Selected: `{rob_commands[opt]}`

How many users to execute? Reply with number.")
            else:
                await message.reply("❌ Reply with `1`, `2`, or `3`.")

        elif state["step"] == "rob_count":
            if not message.text.strip().isdigit():
                await message.reply("❌ Reply with a number.")
                return
            count = int(message.text.strip())
            scan = LAST_SCAN.get(state["chat_id"])
            pairs = list(scan["user_msgs"].items())[:count] if scan else []
            if not pairs:
                await message.reply("❌ No scan data. Use option 1 first.")
                del DEVOUR_STATE[user_id]
                return
            state.update({"step": "rob_confirm", "msg_pairs": pairs})
            await message.reply(f"✅ Will send `{state['rob_cmd']}` to **{count} users**.

Type `yes` to confirm.")

        elif state["step"] == "await_count":
            if not message.text.strip().isdigit():
                await message.reply("❌ Reply with a number.")
                return
            count = int(message.text.strip())
            user_msgs = list(state["user_msgs"].items())
            state.update({"step": "execute_all", "exec_count": count, "msg_pairs": user_msgs[:count]})
            await message.reply(f"✅ Ready. Will reply to **{count} users**.
Type `yes` to confirm.")

        elif state["step"] == "await_links":
            links = message.text.splitlines()
            msg_ids = []
            for link in links:
                try:
                    msg_ids.append(int(link.strip().split("/")[-1]))
                except:
                    continue
            if not msg_ids:
                await message.reply("❌ No valid message links!")
                del DEVOUR_STATE[user_id]
                return
            state.update({"step": "links_confirm", "msg_ids": msg_ids})
            await message.reply(f"✅ Found **{len(msg_ids)} messages**.
Type `yes` to confirm.")

        elif state["step"] == "wait_2text_prepare":
            if not message.text.strip().isdigit():
                await message.reply("❌ Reply with a number.")
                return
            count = int(message.text.strip())
            scan = LAST_SCAN.get(state["chat_id"])
            pairs = list(scan["user_msgs"].items())[:count] if scan else []
            if not pairs:
                await message.reply("❌ No scan data. Use option 1 first.")
                del DEVOUR_STATE[user_id]
                return
            state.update({"step": "exec_2text", "msg_pairs": pairs})
            await message.reply(f"✅ Will send both texts to **{count} users**.
Type `yes` to confirm.")

        elif state["step"] == "await_temptext":
            if message.text.strip().startswith("/temptext "):
                try:
                    parts = message.text.strip().split(" ", 2)
                    if len(parts) < 3:
                        await message.reply("❌ Usage: `/temptext 1 <text>` or `/temptext 2 <text>`")
                        return
                    num, rest = parts[1], parts[2]
                    if num not in ["1", "2"]:
                        await message.reply("❌ Send `/temptext 1 <text>` or `/temptext 2 <text>`.")
                        return
                    state.update({"step": "temptext_count", "tempcount": int(num), "temptext": rest.strip()})
                    await message.reply(f"✅ Temporary text set.
How many users to execute? Reply with number.")
                except:
                    await message.reply("❌ Send valid `/temptext` command.")
            else:
                await message.reply("❌ Send `/temptext 1 <text>` or `/temptext 2 <text>`.")

        elif state["step"] == "temptext_count":
            if not message.text.strip().isdigit():
                await message.reply("❌ Reply with a number.")
                return
            count = int(message.text.strip())
            scan = LAST_SCAN.get(state["chat_id"])
            pairs = list(scan["user_msgs"].items())[:count] if scan else []
            if not pairs:
                await message.reply("❌ No scan data. Use option 1 first.")
                del DEVOUR_STATE[user_id]
                return
            state.update({"step": "temptext_confirm", "tempcount_usr": count, "msg_pairs": pairs})
            if state["tempcount"] == 1:
                await message.reply(f"✅ Will send temporary text to **{count} user(s)**.
Type `yes` to confirm.")
            else:
                await message.reply(f"✅ Will send 2x same temporary text to **{count} user(s)**.
Type `yes` to confirm.")

        elif state["step"] in [
            "execute_all", "exec_2text", "links_confirm", "temptext_confirm", "rob_confirm"
        ]:
            if message.text.strip().lower() != "yes":
                await message.reply("❌ Type `yes` to execute.")
                return

            chat_id = state["chat_id"]
            to_delete_ids = []
            if state["step"] == "execute_all":
                msg_pairs = state["msg_pairs"]
                reply_text = REPLY_TEXT1.get(chat_id, "/kill")
                status = await message.reply(f"⚡ Executing... (0/{len(msg_pairs)})")
                for idx, (_, msg_id) in enumerate(msg_pairs, 1):
                    try:
                        out = await client.send_message(chat_id, reply_text, reply_to_message_id=msg_id)
                        to_delete_ids.append(out.id)
                    except Exception as e:
                        print(f"Error: {e}")
                    await asyncio.sleep(random.uniform(*DELAY_RANGE))
                    if idx % 5 == 0:
                        try:
                            await status.edit(f"⚡ Executing... ({idx}/{len(msg_pairs)})")
                        except:
                            pass
                save_execution_log(chat_id, [f"https://t.me/c/{str(chat_id)[4:]}/{mid}" for _,mid in msg_pairs], [reply_text], "all")
                await status.edit(f"✅ Done! Sent to **{len(msg_pairs)} users**.

🗑 Auto-deleting bot replies...")
                try:
                    await client.delete_messages(chat_id, to_delete_ids)
                except:
                    pass
                await message.reply("✅ Complete. All bot replies deleted from group.")

            elif state["step"] == "links_confirm":
                reply_text = REPLY_TEXT1.get(chat_id, "/kill")
                status = await message.reply(f"⚡ Executing... (0/{len(state['msg_ids'])})")
                for idx, msg_id in enumerate(state["msg_ids"], 1):
                    try:
                        out = await client.send_message(chat_id, reply_text, reply_to_message_id=msg_id)
                        to_delete_ids.append(out.id)
                    except Exception as e:
                        print(f"Error: {e}")
                    await asyncio.sleep(random.uniform(*DELAY_RANGE))
                    if idx % 5 == 0:
                        try:
                            await status.edit(f"⚡ Executing... ({idx}/{len(state['msg_ids'])})")
                        except:
                            pass
                save_execution_log(chat_id, [f"https://t.me/c/{str(chat_id)[4:]}/{mid}" for mid in state["msg_ids"]], [reply_text], "msglinks")
                await status.edit(f"✅ Done! Sent to **{len(state['msg_ids'])} messages**.

🗑 Auto-deleting bot replies...")
                try:
                    await client.delete_messages(chat_id, to_delete_ids)
                except:
                    pass
                await message.reply("✅ Complete. All bot replies deleted from group.")

            elif state["step"] == "exec_2text":
                msg_pairs = state["msg_pairs"]
                reply_text1 = REPLY_TEXT1.get(chat_id, "/kill")
                reply_text2 = REPLY_TEXT2.get(chat_id, "/rob 150")
                status = await message.reply(f"⚡ Executing 2-text mode... (0/{len(msg_pairs)})")
                for idx, (_, msg_id) in enumerate(msg_pairs, 1):
                    try:
                        out1 = await client.send_message(chat_id, reply_text1, reply_to_message_id=msg_id)
                        to_delete_ids.append(out1.id)
                        await asyncio.sleep(0.5)
                        out2 = await client.send_message(chat_id, reply_text2, reply_to_message_id=msg_id)
                        to_delete_ids.append(out2.id)
                    except Exception as e:
                        print(f"Error: {e}")
                    await asyncio.sleep(random.uniform(*DELAY_RANGE))
                    if idx % 5 == 0:
                        try:
                            await status.edit(f"⚡ Executing... ({idx}/{len(msg_pairs)})")
                        except:
                            pass
                save_execution_log(chat_id, [f"https://t.me/c/{str(chat_id)[4:]}/{mid}" for _,mid in msg_pairs], [reply_text1, reply_text2], "2text")
                await status.edit(f"✅ Done! Sent 2 texts to **{len(msg_pairs)} users**.

🗑 Auto-deleting bot replies...")
                try:
                    await client.delete_messages(chat_id, to_delete_ids)
                except:
                    pass
                await message.reply("✅ Complete. All bot replies deleted from group.")

            elif state["step"] == "temptext_confirm":
                msg_pairs = state["msg_pairs"]
                temptext = state["temptext"]
                status = await message.reply(f"⚡ Executing temp text... (0/{len(msg_pairs)})")
                for idx, (_, msg_id) in enumerate(msg_pairs, 1):
                    try:
                        out1 = await client.send_message(chat_id, temptext, reply_to_message_id=msg_id)
                        to_delete_ids.append(out1.id)
                        if state["tempcount"] == 2:
                            await asyncio.sleep(0.5)
                            out2 = await client.send_message(chat_id, temptext, reply_to_message_id=msg_id)
                            to_delete_ids.append(out2.id)
                    except Exception as e:
                        print(f"Error: {e}")
                    await asyncio.sleep(random.uniform(*DELAY_RANGE))
                    if idx % 5 == 0:
                        try:
                            await status.edit(f"⚡ Executing... ({idx}/{len(msg_pairs)})")
                        except:
                            pass
                await status.edit(f"✅ Done! Temp text sent to **{len(msg_pairs)} users**.

🗑 Auto-deleting bot replies...")
                try:
                    await client.delete_messages(chat_id, to_delete_ids)
                except:
                    pass
                await message.reply("✅ Complete. All bot replies deleted from group.")

            elif state["step"] == "rob_confirm":
                msg_pairs = state["msg_pairs"]
                rob_cmd = state["rob_cmd"]
                status = await message.reply(f"⚡ Executing Rob mode... (0/{len(msg_pairs)})")
                for idx, (_, msg_id) in enumerate(msg_pairs, 1):
                    try:
                        out = await client.send_message(chat_id, rob_cmd, reply_to_message_id=msg_id)
                        to_delete_ids.append(out.id)
                    except Exception as e:
                        print(f"Error: {e}")
                    await asyncio.sleep(random.uniform(*DELAY_RANGE))
                    if idx % 5 == 0:
                        try:
                            await status.edit(f"⚡ Executing... ({idx}/{len(msg_pairs)})")
                        except:
                            pass
                save_execution_log(chat_id, [f"https://t.me/c/{str(chat_id)[4:]}/{mid}" for _,mid in msg_pairs], [rob_cmd], "rob")
                await status.edit(f"✅ Done! Sent `{rob_cmd}` to **{len(msg_pairs)} users**.

🗑 Auto-deleting bot replies...")
                try:
                    await client.delete_messages(chat_id, to_delete_ids)
                except:
                    pass
                await message.reply("✅ Complete. All bot replies deleted from group.")
            DEVOUR_STATE.pop(user_id, None)

    @app.on_message(filters.command("settext1") & sudo_filter & filters.private)
    async def settext1(client, message):
        parts = message.text.split(" ", 1)
        if len(parts)==2 and parts[1].strip():
            REPLY_TEXT1[message.chat.id] = parts[1].strip()
            save_data()
            await message.reply(f"✅ **Text1 set to:**
`{parts[1].strip()}`")
        else:
            await message.reply("❌ **Usage:** `/settext1 <text>`")

    @app.on_message(filters.command("settext2") & sudo_filter & filters.private)
    async def settext2(client, message):
        parts = message.text.split(" ", 1)
        if len(parts)==2 and parts[1].strip():
            REPLY_TEXT2[message.chat.id] = parts[1].strip()
            save_data()
            await message.reply(f"✅ **Text2 set to:**
`{parts[1].strip()}`")
        else:
            await message.reply("❌ **Usage:** `/settext2 <text>`")

    @app.on_message(filters.command("addacc") & sudo_filter & filters.private)
    async def addacc(client, message):
        user_id = message.from_user.id
        parts = message.text.split(" ", 2)
        if len(parts) < 3:
            await message.reply("❌ **Usage:** `/addacc <name> <session_string>`

Example: `/addacc haley BQAbc123...xyz`")
            return
        name = parts[1].strip()
        session_string = parts[2].strip()
        if any(s["name"].lower() == name.lower() for s in SESSIONS):
            await message.reply(f"❌ Account with name `{name}` already exists!")
            return
        SESSIONS.append({"name": name, "session_string": session_string})
        save_data()
        await message.reply(f"✅ Account `{name}` added successfully!
⚠️ **Restart the bot to activate this account.**")

    @app.on_message(filters.command("joinchat") & sudo_filter)
    async def joinchat(client, message):
        parts = message.text.split(" ", 1)
        if len(parts)<2:
            await message.reply("❌ **Usage:** `/joinchat <invite_link>`")
            return
        try:
            chat = await client.join_chat(parts[1])
            await message.reply(f"✅ Joined **{chat.title or chat.id}**.")
        except Exception as e:
            await message.reply(f"❌ Error: {e}")

    @app.on_message(filters.command(["cancel", "stop"]) & sudo_filter)
    async def cancel(client, message):
        user_id = message.from_user.id
        DEVOUR_STATE.pop(user_id, None)
        await message.reply("🛑 Current task cancelled/reset.")

    @app.on_message(filters.command("help") & sudo_filter)
    async def help_msg(client, message):
        await message.reply(
            "🤖 **Devour UserBot Help:**

"
            "**Commands (use in DM):**
"
            "• `/devour` - Start the process
"
            "• `/settext1 <text>` - Set primary text
"
            "• `/settext2 <text>` - Set secondary text (for 2-text mode)
"
            "• `/joinchat <link>` - Join group/channel
"
            "• `/temptext 1 <text>` - One-time temporary text
"
            "• `/temptext 2 <text>` - Send temp text twice
"
            "• `/addacc <name> <session_string>` - Add new account
"
            "• `/cancel` or `/stop` - Cancel current operation
"
            "• `/help` - Show this message

"
            f"**Data file:** `{DATA_FILE}`
"
            f"**Active accounts:** {len(SESSIONS)}"
        )

async def main():
    load_data()
    if not SESSIONS:
        print("❌ No sessions found! Add sessions using /addacc command or manually edit devour.json")
        print("Creating sample devour.json structure...")
        save_data()
        return
    apps = []
    for sess in SESSIONS:
        app = Client(sess["name"], api_id=API_ID, api_hash=API_HASH, session_string=sess["session_string"])
        register_handlers(app)
        apps.append(app)
    print(f"🤖 Running {len(apps)} account(s) with DM-based control.")
    print(f"💾 Data file: {DATA_FILE}")
    print(f"👤 Sudo users: {SUDO_USERS}")
    await compose(apps)

if __name__ == "__main__":
    asyncio.run(main())
