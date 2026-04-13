from flask import Blueprint, request, abort
from linebot.exceptions import InvalidSignatureError
from linebot.models import TextSendMessage, MessageEvent, TextMessage

from config import handler, line_bot_api
from repositories.user_repository import get_user_by_line_id, upsert_user


webhook_bp = Blueprint("webhook", __name__)


@webhook_bp.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = (event.message.text or "").strip()
    user_line_id = event.source.user_id

    if text.startswith("登録"):
        name = text.replace("登録", "", 1).lstrip("：:").strip()
        if not name:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="登録：太郎 の形式で送ってください")
            )
            return

        user = get_user_by_line_id(user_line_id)
        if user and (user["name"] or "").strip():
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="名前はすでに登録されています。変更したい場合は管理者に連絡してください。")
            )
            return

        upsert_user(user_line_id, name)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="登録完了"))
        return

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(
            text="使い方:\n"
                 "・LIFFで提出（リッチメニューのボタン）\n"
                 "・名前登録: 登録：太郎"
        )
    )
