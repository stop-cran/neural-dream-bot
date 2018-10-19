from enum import Enum
from io import BytesIO
import json
from six.moves.urllib.request import urlopen
from six.moves.urllib.parse import urlencode
from six.moves.urllib.error import HTTPError

import requests


class ImageReadResult(Enum):
    INVALID = 0,
    TOO_BIG = 1,
    OK = 2


class Bot:
    def __init__(self, base_url, file_url):
        self.base_url = base_url
        self.file_url = file_url

    @staticmethod
    def deconstruct_message(body):
        if "message" in body:
            message = body["message"]
            return message["chat"]["id"], message["from"], message, None
        elif "callback_query" in body:
            callback_query = body["callback_query"]
            return callback_query["message"]["chat"]["id"], callback_query["from"], None, callback_query

    @staticmethod
    def get_file_id(message):
        if "photo" in message:
            photo = message["photo"][-1]
            if photo["file_size"] > 1e7 or photo["width"] > 3000 or photo["height"] > 3000:
                return ImageReadResult.TOO_BIG, None, None
            return ImageReadResult.OK, photo["file_id"], True
        elif "document" in message:
            document = message["document"]
            if "image" in document["mime_type"]:
                if document["file_size"] > 1e7:
                    return ImageReadResult.TOO_BIG, None, None
                else:
                    return ImageReadResult.OK, document["file_id"], False
            else:
                return ImageReadResult.INVALID, None, None

    @staticmethod
    def to_inline_keyboard(items):
        keyboard = [[dict(
            text=item[1],
            callback_data=item[0]
        ) for item in row] for row in items]
        return json.dumps(dict(inline_keyboard=keyboard))

    def forward_message(self, from_chat_id, chat_id, message_id):
        request = urlopen(self.base_url + "forwardMessage",
                          urlencode(dict(
                              chat_id=chat_id,
                              from_chat_id=from_chat_id,
                              message_id=message_id
                          )))
        resp = json.loads(request.read().decode())

        assert resp["ok"], "forward_message from %d to %s (message id %d) unsuccessful." %\
                           (from_chat_id, chat_id, message_id)
        return resp["result"]["message_id"]

    def send_message(self, chat_id, text, reply_markup=None, reply_to_message_id=None):
        params = dict(
            chat_id=str(chat_id),
            text=text.encode("utf-8"),
            parse_mode="Markdown")
        if reply_markup:
            params["reply_markup"] = reply_markup
        if reply_to_message_id:
            params["reply_to_message_id"] = reply_to_message_id

        request = urlopen(self.base_url + "sendMessage", urlencode(params))
        resp = json.loads(request.read().decode())

        assert resp["ok"], "send_message to %s unsuccessful." % chat_id
        return resp["result"]["message_id"]

    def edit_message(self, chat_id, message_id, text, reply_markup=None):
        params = dict(
            chat_id=str(chat_id),
            message_id=str(message_id),
            text=text.encode("utf-8"),
            parse_mode="Markdown")
        if reply_markup:
            params["reply_markup"] = reply_markup

        try:
            urlopen(self.base_url + "editMessageText", urlencode(params)).close()
        except HTTPError:
            pass

    def answer_callback_query(self, callback_query_id):
        urlopen(self.base_url + "answerCallbackQuery",
                urlencode(dict(
                    callback_query_id=str(callback_query_id)
                ))).close()

    def send_typing(self, chat_id):
        urlopen(self.base_url + "sendChatAction",
                urlencode(dict(
                    chat_id=str(chat_id),
                    action="typing"
                ))).close()

    def send_photo(self, chat_id, photo_file, caption):
        with requests.post(self.base_url + "sendPhoto",
                           files=dict(
                               photo=("result.jpg", photo_file, "multipart/form-data")),
                           data=dict(
                               chat_id=chat_id,
                               caption=caption
                           )) as response:
            content = json.loads(response.content)
            return content["result"]["photo"][-1]["file_id"]

    def open_photo(self, file_id):
        resp = json.loads(urlopen(self.base_url + "getFile?file_id=" + file_id).read().decode())
        assert resp["ok"]
        assert resp["result"]["file_size"] < 1e7

        return BytesIO(urlopen(self.file_url + resp["result"]["file_path"]).read())
