import asyncio
import random
import json
import os
import time
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.enums import ChatType
from pyrogram.errors import UserNotParticipant, FloodWait, PeerIdInvalid

# ========== CONFIG ==========
API_ID = 4880420
API_HASH = "fe7c528c27d3993a438599063bc03a3b"
SESSIONS = []  # Will be loaded from devour.json
SUDO_USERS = [6836139884]
DELAY_RANGE = (4, 6)
DATA_FILE = "devour.json"
PERSONAL_BOT = "im_bakabot"

# ========== SHARED STATE ==========
REPLY_TEXT1 = {}
REPLY_TEXT2 = {}
DEVOUR_STATE = {}
LAST_SCAN = {}

def load_data():
    global REPLY_TEXT1, REPLY_TEXT2, LAST_SCAN, SESSIONS
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
        REPLY_TEXT1 = {int(k): v for k, v in data.get("reply_text1", {}).items()}
        REPLY_TEXT2 = {int(k): v for k, v in data.get("reply_text2", {}).items()}
        LAST_SCAN = {int(k): v for k, v in data.get("last_scan", {}).items()}
        SESSIONS = data.get("sessions", [])
    else:
        SESSIONS = []
        save_data()

def save_data():
    try:
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
    except Exception:
        data = {
            "reply_text1": {},
            "reply_text2": {},
            "execution_logs": [],
            "last_scan": {},
            "sessions": [],
        }
    data["reply_text1"] = {str(k): v for k, v in REPLY_TEXT1.items()}
    data["reply_text2"] = {str(k): v for k, v in REPLY_TEXT2.items()}
    data["last_scan"] = {str(k): v for k, v in LAST_SCAN.items()}
    data["sessions"] = SESSIONS
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def save_execution_log(chat_id, msg_links, texts, mode):
    try:
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
    except Exception:
        data = {
            "reply_text1": {},
            "reply_text2": {},
            "execution_logs": [],
            "last_scan": {},
            "sessions": [],
        }
    log = {
        "chat_id": chat_id,
        "mode": mode,
        "texts": texts,
        "message_links": msg_links,
        "count": len(msg_links),
        "timestamp": time.time(),
    }
    data.setdefault("execution_logs", []).append(log)
    data["reply_text1"] = {str(k): v for k, v in REPLY_TEXT1.items()}
    data["reply_text2"] = {str(k): v for k, v in REPLY_TEXT2.items()}
    data["last_scan"] = {str(k): v for k, v in LAST_SCAN.items()}
    data["sessions"] = SESSIONS
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def owner_or_sudo(_, __, m):
    return m.from_user and (m.from_user.id in SUDO_USERS or m.outgoing)

sudo_filter = filters.create(owner_or_sudo)

def build_main_menu(state, has_scan):
    return (
        f"**🎯 Target:** {state['target_name']}\n"
        f"**Group ID:** `{state['chat_id']}`"
        f"{' | 💾 Scan loaded' if has_scan else ''}\n\n"
        "**Main Menu:**\n"
        "1️⃣ Scan all users (text1)\n"
        "2️⃣ Attack by message links\n"
        "3️⃣ Use last scan\n"
        "4️⃣ 2-text blast (/settext1 + /settext2)\n"
        "5️⃣ Temporary text blast\n"
        "6️⃣ Rob mode (/rob 200/150/100/50/1000)\n"
        "7️⃣ Attack a specific message from all accounts\n"
        "8️⃣ Delete all my messages from group\n"
        "9️⃣ Claim `/daily` from all accounts in @im_bakabot\n"
        "Reply `1-9` or use /cancel"
    )

def parse_message_link(link):
    link = link.strip()
    if link.startswith("https://"):
        link = link.replace("https://", "", 1)
    if link.startswith("http://"):
        link = link.replace("http://", "", 1)
    if link.startswith("t.me/"):
        link = link[5:]
    parts = link.split("/")
    if len(parts) < 2:
        raise ValueError("Invalid link format")
    if parts[0] == "c":
        # t.me/c/123456/789
        if len(parts) < 3:
            raise ValueError("Invalid /c/ link format")
        channel_id = int(parts[1])
        msg_id = int(parts[2])
        chat_id = int(f"-100{channel_id}")
        return chat_id, msg_id
    else:
        username = parts[0]
        msg_id = int(parts[1])
        return username, msg_id

async def add_new_session(apps, name, session_string):
    new_app = Client(
        name,
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=session_string,
    )
    _attach_attack_method(new_app)
    register_handlers(new_app, apps)
    await new_app.start()
    apps.append(new_app)

async def remove_session(apps, name):
    idx = None
    for i, s in enumerate(SESSIONS):
        if s["name"] == name:
            idx = i
            break
    if idx is not None:
        for i, app in enumerate(apps):
            if app.name == name:
                try:
                    await app.stop()
                except Exception:
                    pass
                apps.pop(i)
                break
        SESSIONS.pop(idx)
        save_data()

async def run_parallel_attacks(app_list, chat_id, msg_id, text, times):
    async def attack_one(app):
        for _ in range(times):
            try:
                await app.send_message(chat_id, text, reply_to_message_id=msg_id)
                await asyncio.sleep(0.25)
            except FloodWait as e:
                await asyncio.sleep(e.value)
            except Exception:
                break
    await asyncio.gather(*[attack_one(a) for a in app_list])

def _attach_attack_method(app):
    async def send_spam_attack(chat_id, msg_id, text, times):
        for _ in range(times):
            try:
                await app.send_message(chat_id, text, reply_to_message_id=msg_id)
                await asyncio.sleep(0.25)
            except Exception:
                break
    app.send_spam_attack = send_spam_attack.__get__(app, Client)
    return app

def register_handlers(app, all_apps=None):

    @app.on_message(filters.command("devour") & sudo_filter & filters.private)
    async def devour_start(client, message):
        user_id = message.from_user.id
        DEVOUR_STATE[user_id] = {"step": "await_target"}
        await message.reply("🔗 Send the group link (`https://t.me/...`), @username or chat id (-100...) of the target chat.")

    @app.on_message(
        sudo_filter
        & filters.private
        & ~filters.command(
            [
                "devour",
                "settext1",
                "settext2",
                "help",
                "cancel",
                "stop",
                "joinchat",
                "addacc",
                "delacc",
                "delall",
                "claim",
            ]
        )
    )
    async def devour_menu(client, message):
        user_id = message.from_user.id
        if user_id not in DEVOUR_STATE:
            return
        state = DEVOUR_STATE[user_id]
        text = message.text.strip()

        # STEP 1: choose target chat
        if state["step"] == "await_target":
            chat_input = text
            try:
                # normalize username or id or full link
                if chat_input.startswith("https://t.me/") or chat_input.startswith("http://t.me/"):
                    # let Pyrogram resolve the URL directly
                    chat = await client.get_chat(chat_input)
                else:
                    # username or id
                    chat = await client.get_chat(chat_input)
                if not chat:
                    await message.reply("❌ Could not find that chat.")
                    DEVOUR_STATE.pop(user_id, None)
                    return

                try:
                    member = await client.get_chat_member(chat.id, "me")
                    if not member:
                        await message.reply("❌ Not a member. Join with /joinchat <invite link>.")
                        DEVOUR_STATE.pop(user_id, None)
                        return
                except UserNotParticipant:
                    await message.reply("❌ Not a member. Join with /joinchat <invite link>.")
                    DEVOUR_STATE.pop(user_id, None)
                    return

                scan = LAST_SCAN.get(chat.id)
                state.update(
                    {
                        "step": "main_menu",
                        "target_name": chat.title or str(chat.id),
                        "chat_id": chat.id,
                    }
                )
                menu = build_main_menu(state, scan is not None)
                await message.reply(menu)
            except PeerIdInvalid:
                await message.reply("❌ Peer ID invalid or unknown. Make sure this account joined the group.")
                DEVOUR_STATE.pop(user_id, None)
            except Exception as e:
                await message.reply(f"❌ Error accessing chat: {e}")
                DEVOUR_STATE.pop(user_id, None)
            return

        # STEP MAIN MENU
        if state["step"] == "main_menu":
            opt = text.lower()
            chat_id = state["chat_id"]

            # 1) Scan all users (text1)
            if opt == "1":
                state["step"] = "scanning"
                status = await message.reply(f"🔍 Scanning all users in **{state['target_name']}**...")
                user_msgs = {}
                try:
                    async for msg in client.get_chat_history(chat_id):
                        if (
                            msg.from_user
                            and not msg.from_user.is_bot
                            and not getattr(msg.from_user, "is_deleted", False)
                        ):
                            if msg.from_user.id not in user_msgs:
                                user_msgs[msg.from_user.id] = msg.id
                except PeerIdInvalid:
                    await status.edit("❌ Peer ID invalid or not joined.")
                    DEVOUR_STATE.pop(user_id, None)
                    return
                last_count = len(user_msgs)
                LAST_SCAN[chat_id] = {
                    "user_msgs": user_msgs,
                    "count": last_count,
                    "timestamp": time.time(),
                }
                save_data()
                state["step"] = "await_count"
                state["user_msgs"] = user_msgs
                await status.edit(
                    f"✅ Found **{last_count}** users.\n\nHow many to execute (1-{last_count})? Reply with a number."
                )
                return

            # 2) message-links attack
            if opt == "2":
                state["step"] = "await_links"
                await message.reply("📎 Send message links (one per line).")
                return

            # 3) use last scan
            if opt == "3":
                scan = LAST_SCAN.get(chat_id)
                if not scan or not scan.get("user_msgs"):
                    await message.reply("❌ No cached previous scan data. Use option 1 first.")
                    DEVOUR_STATE.pop(user_id, None)
                    return
                state["user_msgs"] = scan["user_msgs"]
                state["step"] = "await_count"
                await message.reply(
                    f"💾 Loaded cached data (**{len(scan['user_msgs'])} users**).\n\nHow many to execute? Reply with number."
                )
                return

            # 4) 2-text blast
            if opt == "4":
                state["step"] = "wait_2text_prepare"
                await message.reply(
                    "📝 Set texts with `/settext1 <text>` and `/settext2 <text>`.\nWhen ready, reply with how many users to execute."
                )
                return

            # 5) temporary text (one-time)
            if opt == "5":
                state["step"] = "await_temptext"
                await message.reply(
                    "📝 Send `/temptext 1 <text>` for one reply, or `/temptext 2 <text>` for two identical replies per user."
                )
                return

            # 6) rob mode
            if opt == "6":
                state["step"] = "rob_select"
                await message.reply(
                    "💰 **Rob Mode**\n"
                    "1️⃣ /rob 200\n"
                    "2️⃣ /rob 150\n"
                    "3️⃣ /rob 100\n"
                    "4️⃣ /rob 50\n"
                    "5️⃣ /rob 1000\n"
                    "Reply with 1-5"
                )
                return

            # 7) attack a specific message from all accounts
            if opt == "7":
                state["step"] = "attack_message_link"
                await message.reply(
                    "🔥 **Attack by Message Link**\nSend the target message link "
                    "(right-click/copy link from the user message)."
                )
                return

            # 8) delete all self messages from group
            if opt == "8":
                status = await message.reply("🗑 Deleting all my messages from group...")
                deleted_count = 0
                async for msg in client.get_chat_history(chat_id):
                    if msg.from_user and msg.from_user.is_self:
                        try:
                            await client.delete_messages(chat_id, msg.id)
                            deleted_count += 1
                            await asyncio.sleep(0.1)
                        except Exception:
                            pass
                await status.edit(f"✅ Done! Deleted {deleted_count} messages.")
                await message.reply("✅ All bot messages removed from group.")
                DEVOUR_STATE.pop(user_id, None)
                return

            # 9) claim daily on @im_bakabot
            if opt == "9":
                await message.reply("⏳ Claiming `/daily` from all accounts in @im_bakabot...")
                failed = 0
                for sess in SESSIONS:
                    try:
                        temp_app = None
                        if all_apps:
                            for a in all_apps:
                                if a.name == sess["name"]:
                                    temp_app = a
                                    break
                        if temp_app is None:
                            temp_app = Client(
                                sess["name"],
                                api_id=API_ID,
                                api_hash=API_HASH,
                                session_string=sess["session_string"],
                            )
                            await temp_app.start()
                        await temp_app.send_message(PERSONAL_BOT, "/daily")
                        if all_apps is None or temp_app not in all_apps:
                            await temp_app.stop()
                        await asyncio.sleep(2)
                    except Exception:
                        failed += 1
                await message.reply(
                    f"✅ `/daily` claimed in @im_bakabot.\nAccounts: {len(SESSIONS)}, Failed: {failed}"
                )
                DEVOUR_STATE.pop(user_id, None)
                return

            await message.reply("❌ Invalid option. Reply `1-9`.")
            return

        # ROB MODE
        if state["step"] == "rob_select":
            opt = text
            rob_commands = {
                "1": "/rob 200",
                "2": "/rob 150",
                "3": "/rob 100",
                "4": "/rob 50",
                "5": "/rob 1000",
            }
            if opt in rob_commands:
                state["rob_cmd"] = rob_commands[opt]
                state["step"] = "rob_count"
                await message.reply(
                    f"✅ Selected: `{rob_commands[opt]}`.\nHow many users to execute? Reply with number."
                )
            else:
                await message.reply("❌ Reply with `1-5`.")
            return

        if state["step"] == "rob_count":
            if not text.isdigit():
                await message.reply("❌ Reply with a number.")
                return
            count = int(text)
            scan = LAST_SCAN.get(state["chat_id"])
            pairs = list(scan["user_msgs"].items())[:count] if scan else []
            if not pairs:
                await message.reply("❌ No scan data. Use option 1 first.")
                DEVOUR_STATE.pop(user_id, None)
                return
            state["msg_pairs"] = pairs
            state["step"] = "rob_confirm"
            await message.reply(
                f"✅ Will send `{state['rob_cmd']}` to **{count} users**.\nType `yes` to confirm."
            )
            return

        # ATTACK BY MESSAGE LINK FROM ALL ACCOUNTS
        if state["step"] == "attack_message_link":
            link = text
            try:
                chatid_or_username, msg_id = parse_message_link(link)
            except Exception:
                await message.reply(
                    "❌ Invalid message link.\nUse `t.me/c/<id>/<msg_id>` or `t.me/<username>/<msg_id>` format."
                )
                DEVOUR_STATE.pop(user_id, None)
                return
            state["attack_msg_link"] = link
            state["attack_chat"] = chatid_or_username
            state["attack_msg_id"] = msg_id
            state["step"] = "attack_text"
            await message.reply("✏️ What message/command to spam? (e.g. `/rob 10000`)")
            return

        if state["step"] == "attack_text":
            custom_text = text
            if not custom_text:
                await message.reply("❌ Message text required.")
                return
            state["attack_text"] = custom_text
            state["step"] = "attack_times"
            await message.reply(
                "🔢 How many times to spam (per account)? (1–100)\n"
                "This will be executed from **all accounts** in parallel."
            )
            return

        if state["step"] == "attack_times":
            if not text.isdigit():
                await message.reply("❌ Reply with a number 1–100.")
                return
            times = int(text)
            if times < 1 or times > 100:
                await message.reply("❌ Number must be between 1 and 100.")
                return
            state["attack_times"] = times
            state["step"] = "attack_link_confirm"
            await message.reply(
                f"Ready! Will spam `{state['attack_text']}` {times} times per account at:\n"
                f"`{state['attack_msg_link']}`\n\nType `yes` to confirm."
            )
            return

        if state["step"] == "attack_link_confirm":
            if text.lower() != "yes":
                await message.reply("❌ Type `yes` to execute.")
                return
            chatid_or_username = state["attack_chat"]
            msg_id = state["attack_msg_id"]
            text_to_send = state["attack_text"]
            times = state["attack_times"]
            # Resolve username to id if needed using this client
            try:
                if isinstance(chatid_or_username, str):
                    chat_obj = await client.get_chat(chatid_or_username)
                    chat_id = chat_obj.id
                else:
                    chat_id = chatid_or_username
            except Exception as e:
                await message.reply(f"❌ Failed to resolve chat: {e}")
                DEVOUR_STATE.pop(user_id, None)
                return
            await message.reply("🚀 Spamming now from all accounts (in background)...")
            if all_apps:
                asyncio.create_task(
                    run_parallel_attacks(all_apps, chat_id, msg_id, text_to_send, times)
                )
            DEVOUR_STATE.pop(user_id, None)
            return

        # SCAN RESULT EXECUTION (simple single-text mode based on REPLY_TEXT1)
        if state["step"] == "await_count":
            if not text.isdigit():
                await message.reply("❌ Enter a valid number.")
                return
            count = int(text)
            user_msgs = state.get("user_msgs")
            if not user_msgs:
                await message.reply("❌ No user scan loaded.")
                DEVOUR_STATE.pop(user_id, None)
                return
            pairs = list(user_msgs.items())[:count]
            state["step"] = "execution_confirm"
            state["msg_pairs"] = pairs
            await message.reply(
                f"Ready to execute on {count} users using Text1.\nType `yes` to confirm."
            )
            return

        if state["step"] == "execution_confirm":
            if text.lower() != "yes":
                await message.reply("❌ Type `yes` to confirm.")
                return
            pairs = state.get("msg_pairs", [])
            chat_id = state["chat_id"]
            reply_text = REPLY_TEXT1.get(message.chat.id, "Hi there!")
            sent = 0
            for _, msg_id in pairs:
                try:
                    await client.send_message(chat_id, reply_text, reply_to_message_id=msg_id)
                    sent += 1
                    await asyncio.sleep(random.uniform(*DELAY_RANGE))
                except FloodWait as e:
                    await asyncio.sleep(e.value)
                except Exception:
                    pass
            await message.reply(f"✅ Done! Message sent to {sent} users.")
            DEVOUR_STATE.pop(user_id, None)
            return

        # Simple rob execution (re-using same executor but with rob_cmd)
        if state["step"] == "rob_confirm":
            if text.lower() != "yes":
                await message.reply("❌ Type `yes` to execute.")
                return
            pairs = state.get("msg_pairs", [])
            chat_id = state["chat_id"]
            rob_cmd = state["rob_cmd"]
            sent = 0
            for _, msg_id in pairs:
                try:
                    await client.send_message(chat_id, rob_cmd, reply_to_message_id=msg_id)
                    sent += 1
                    await asyncio.sleep(random.uniform(*DELAY_RANGE))
                except FloodWait as e:
                    await asyncio.sleep(e.value)
                except Exception:
                    pass
            await message.reply(f"✅ Done! `{rob_cmd}` sent to {sent} users.")
            DEVOUR_STATE.pop(user_id, None)
            return

    # ========== BASIC COMMANDS ==========

    @app.on_message(filters.command("addacc") & sudo_filter & filters.private)
    async def addacc(client, message):
        parts = message.text.split(" ", 2)
        if len(parts) < 3:
            await message.reply(
                "❌ **Usage:** `/addacc <name> <session_string>`\n"
                "Example: `/addacc acc1 BQAbc123...xyz`"
            )
            return
        name, session_string = parts[1].strip(), parts[2].strip()
        if any(s["name"].lower() == name.lower() for s in SESSIONS):
            await message.reply(f"❌ Account with name `{name}` already exists!")
            return
        SESSIONS.append({"name": name, "session_string": session_string})
        save_data()
        if all_apps is not None:
            await add_new_session(all_apps, name, session_string)
            await message.reply(f"✅ Account `{name}` added & started (no restart needed).")
        else:
            await message.reply(f"✅ Account `{name}` added. Restart to activate.")

    @app.on_message(filters.command("delacc") & sudo_filter & filters.private)
    async def delacc(client, message):
        parts = message.text.split(" ", 1)
        if len(parts) < 2:
            await message.reply("❌ **Usage:** `/delacc <name>`")
            return
        name = parts[1].strip()
        if not any(s["name"] == name for s in SESSIONS):
            await message.reply(f"❌ No such account: {name}")
            return
        if all_apps is not None:
            await remove_session(all_apps, name)
            await message.reply(f"✅ Account `{name}` removed and stopped.")
        else:
            await message.reply("Account removed. Please restart for changes to take effect.")

    @app.on_message(filters.command("joinchat") & sudo_filter)
    async def joinchat(client, message):
        parts = message.text.split(" ", 1)
        if len(parts) < 2:
            await message.reply("❌ **Usage:** `/joinchat <invite_link>`")
            return
        try:
            chat = await client.join_chat(parts[1].strip())
            await message.reply(f"✅ Joined **{chat.title or chat.id}**.")
        except Exception as e:
            await message.reply(f"❌ Error: {e}")

    @app.on_message(filters.command(["cancel", "stop"]) & sudo_filter)
    async def cancel(client, message):
        user_id = message.from_user.id
        DEVOUR_STATE.pop(user_id, None)
        await message.reply("🛑 Current task cancelled/reset.")

    @app.on_message(filters.command("settext1") & sudo_filter & filters.private)
    async def settext1(client, message):
        parts = message.text.split(" ", 1)
        if len(parts) == 2 and parts[1].strip():
            REPLY_TEXT1[message.chat.id] = parts[1].strip()
            save_data()
            await message.reply(f"✅ **Text1 set to:** `{parts[1].strip()}`")
        else:
            await message.reply("❌ **Usage:** `/settext1 <text>`")

    @app.on_message(filters.command("settext2") & sudo_filter & filters.private)
    async def settext2(client, message):
        parts = message.text.split(" ", 1)
        if len(parts) == 2 and parts[1].strip():
            REPLY_TEXT2[message.chat.id] = parts[1].strip()
            save_data()
            await message.reply(f"✅ **Text2 set to:** `{parts[1].strip()}`")
        else:
            await message.reply("❌ **Usage:** `/settext2 <text>`")

    @app.on_message(filters.command("delall") & sudo_filter & filters.private)
    async def delall(client, message):
        user_id = message.from_user.id
        state = DEVOUR_STATE.get(user_id)
        if not state or "chat_id" not in state:
            await message.reply("❌ Set a target chat via /devour first.")
            return
        chat_id = state["chat_id"]
        status = await message.reply("🗑 Deleting all my messages from group...")
        deleted_count = 0
        async for msg in client.get_chat_history(chat_id):
            if msg.from_user and msg.from_user.is_self:
                try:
                    await client.delete_messages(chat_id, msg.id)
                    deleted_count += 1
                    await asyncio.sleep(0.1)
                except Exception:
                    pass
        await status.edit(f"✅ Done! Deleted {deleted_count} messages.")
        await message.reply("✅ All my messages removed from group.")

    @app.on_message(filters.command("claim") & sudo_filter & filters.private)
    async def claim(client, message):
        await message.reply("⏳ Claiming `/daily` from all accounts in @im_bakabot...")
        failed = 0
        for sess in SESSIONS:
            try:
                temp_app = None
                if all_apps:
                    for a in all_apps:
                        if a.name == sess["name"]:
                            temp_app = a
                            break
                if temp_app is None:
                    temp_app = Client(
                        sess["name"],
                        api_id=API_ID,
                        api_hash=API_HASH,
                        session_string=sess["session_string"],
                    )
                    await temp_app.start()
                await temp_app.send_message(PERSONAL_BOT, "/daily")
                if all_apps is None or temp_app not in all_apps:
                    await temp_app.stop()
                await asyncio.sleep(2)
            except Exception:
                failed += 1
        await message.reply(
            f"✅ `/daily` claimed in @im_bakabot.\nAccounts: {len(SESSIONS)}, Failed: {failed}"
        )

    @app.on_message(filters.command("help") & sudo_filter)
    async def help_msg(client, message):
        await message.reply(
            "**🤖 Devour UserBot Help:**\n\n"
            "**DM Commands:**\n"
            "`/devour` - Open main control menu\n"
            "`/settext1 <text>` - Set Text1\n"
            "`/settext2 <text>` - Set Text2\n"
            "`/joinchat <link>` - Join group/channel\n"
            "`/addacc <name> <session>` - Add new account (hot add)\n"
            "`/delacc <name>` - Remove account (hot remove)\n"
            "`/delall` - Delete all my messages from target group\n"
            "`/claim` - Call `/daily` from all accounts in @im_bakabot\n"
            "`/cancel`, `/stop` - Cancel current task\n"
            "`/help` - Show this help\n\n"
            f"**Data:** `{DATA_FILE}` | **Active accounts:** {len(SESSIONS)}"
        )

async def main():
    load_data()
    if not SESSIONS:
        print("❌ No sessions found! Add sessions using /addacc in DM or edit devour.json")
        print("Creating sample devour.json structure...")
        save_data()
        return
    apps = []
    for sess in SESSIONS:
        app = Client(
            sess["name"],
            api_id=API_ID,
            api_hash=API_HASH,
            session_string=sess["session_string"],
        )
        _attach_attack_method(app)
        register_handlers(app, apps)
        apps.append(app)
    print(f"🤖 Running {len(apps)} session(s) with DM-based control.")
    print(f"💾 Data file: {DATA_FILE}")
    print(f"👤 Sudo users: {SUDO_USERS}")
    # Start all apps in parallel and keep them running
    await asyncio.gather(*[a.start() for a in apps])
    # Idle forever
    await asyncio.get_event_loop().create_future()

if __name__ == "__main__":
    asyncio.run(main())
