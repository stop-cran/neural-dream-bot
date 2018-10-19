import re
from datetime import datetime
from PIL import Image
import cloudstorage as gcs
from data_model import Chat, State, SupportRequest
from bot import ImageReadResult
from i18n import get_loc


class Processor:
    def __init__(self, support_chat_id, gs_base_url, loc, bot, ml, logger):
        self.support_chat_id = support_chat_id
        self.gs_base_url = gs_base_url
        self.loc = get_loc(self, loc)
        self.bot = bot
        self.ml = ml
        self.logger = logger

    def process(self, body):
        self.logger.info("Request body: " + str(body))

        chat_id, from_user, message, callback_query = self.deconstruct_message(body)

        chat_model = Chat.get_by_id(int(chat_id))

        if not chat_model:
            chat_model = Chat(id=int(chat_id))

        chat_model.set_default_language(from_user.get("language_code"))
        chat_model.last_activity = datetime.now()
        chat_model.put()

        if chat_model.id == self.support_chat_id:
            if message:
                self.process_support_message(message)
        elif message:
            self.process_message(chat_model, message)
        elif callback_query:
            self.process_callback_query(chat_model, callback_query["data"], callback_query["message"]["message_id"])
            self.bot.answer_callback_query(callback_query["id"])

    @staticmethod
    def deconstruct_message(body):
        if "message" in body:
            message = body["message"]
            return message["chat"]["id"], message["from"], message, None
        elif "callback_query" in body:
            callback_query = body["callback_query"]
            return callback_query["message"]["chat"]["id"], callback_query["from"], None, callback_query

    def process_support_message(self, message):
        reply_to_message = message.get("reply_to_message")
        text = message.get("text")

        if text and reply_to_message:
            support_message_id = reply_to_message["message_id"]
            support_request = SupportRequest.get_by_support_message_id(support_message_id)

            if support_request:
                if "from" in message:
                    support_request.replied_from_id = message["from"].get("id")
                support_request.replied_message_id = message["message_id"]
                support_request.replied = datetime.now()
                support_request.put()
                self.bot.send_message(support_request.original_chat_id,
                                      text,
                                      reply_to_message_id=support_request.original_message_id)
            else:
                from_id = message["reply_to_message"]["forward_from"]["id"]
                self.logger.warn("Failed to get SupportRequest for support_message_id %s, replying to %s." %
                                 (support_message_id, from_id))
                self.bot.send_message(from_id, text)

    @staticmethod
    def is_command(text, command):
        return re.search("/%s(@neuraldreambot)?([^a-zA-Z_]|$)" % command, text)

    def process_message(self, chat_model, message):

        if message["chat"].get("type") != "private":
            chat_model.requests_per_day = 0
            chat_model.put()

        message_from = message.get("from") or {}

        if "photo" in message or "document" in message:
            try:
                result, file_id, compress = self.bot.get_file_id(message)
                self.process_photo(chat_model, result, file_id, compress,
                                   message["message_id"],
                                   message_from.get("id"))
            except:
                self.logger.error("Error processing a photo. Chat id=%d." % chat_model.id, exc_info=True)
                loc, send_message = self.loc(chat_model)
                send_message(loc.job_error)
        else:
            loc, send_message = self.loc(chat_model)
            chat_model_state = chat_model.get_state()

            if message.get("group_chat_created"):
                self.bot.send_message(chat_model.id, loc.group_hello)
            elif "text" in message:
                text = message["text"]
                if self.is_command(text, "start"):
                    if chat_model_state and chat_model_state.step == "processing":
                        send_message(loc.another_job_in_progress)
                    elif State.get_count_last_day(chat_model.id) > chat_model.requests_per_day:
                        send_message(loc.too_many_queries(count=chat_model.requests_per_day))
                    else:
                        chat_model.state = None
                        chat_model.put()
                        if message_from.get("is_bot"):
                            send_message(loc.bot_hello(name=message_from.get("username")))
                        else:
                            send_message(loc.user_hello(name=message_from.get("first_name")))
                elif self.is_command(text, "task_count"):
                    send_message(str(State.get_count_last_day(chat_model.id)))
                elif re.search("^/settings(@neuraldreambot)?$", text):
                    self.send_style_weight_setting(chat_model)
                    self.send_style_scale_setting(chat_model)
                    self.send_style_count_setting(chat_model)
                    self.send_num_iter_setting(chat_model)
                    self.send_img_height_setting(chat_model)
                elif re.search("^/settings(@neuraldreambot)? (.+)", text):
                    if not self.process_callback_query(chat_model,
                                                       re.search("^/settings(@neuraldreambot)? (.+)",
                                                                 text).group(2)):
                        send_message(loc.unknown_settings_command)
                elif self.is_command(text, "support"):
                    if text == u'/support' or text == u'/support@neuraldreambot':
                        send_message(loc.support_help(keyword=text))
                    else:
                        try:
                            message_id = message["message_id"]
                            support_message_id = self.bot.forward_message(chat_model.id,
                                                                          self.support_chat_id,
                                                                          message_id)

                            if support_message_id:
                                SupportRequest(
                                    original_message_id=message_id,
                                    original_chat_id=chat_model.id,
                                    original_from_id=message_from.get("id"),
                                    support_message_id=support_message_id
                                ).put()
                                send_message(loc.support_question_accepted)
                            else:
                                send_message(loc.job_error)
                        except:
                            self.logger.error("Error processing a support message. Chat id=%d." % chat_model.id,
                                              exc_info=True)
                            send_message(loc.job_error)
                else:
                    send_message(loc.no_such_a_command)

    def process_photo(self, chat_model, result, file_id, compress, message_id, from_id):
        chat_model_state = chat_model.get_state()
        loc, send_message = self.loc(chat_model)

        if chat_model_state and chat_model_state.step == "processing":
            send_message(loc.another_job_in_progress)
        elif State.get_count_last_day(chat_model.id) >= chat_model.requests_per_day:
            send_message(loc.too_many_queries(count=chat_model.requests_per_day))
        else:
            if result == ImageReadResult.INVALID:
                send_message(loc.invalid_format_prompt)
            elif result == ImageReadResult.TOO_BIG:
                send_message(loc.too_big_file_prompt)
            elif result == ImageReadResult.OK:
                if not chat_model_state:
                    chat_model.put_new_state(file_id, compress, message_id, from_id)
                    send_message(loc.send_single_style_prompt)
                elif chat_model_state.step == "set_style":
                    chat_model_state.style_file_id.append(file_id)
                    chat_model_state.parameters = chat_model.default_parameters
                    style_count = len(chat_model_state.style_file_id)

                    if style_count >= chat_model_state.parameters.style_count:
                        self.bot.send_typing(chat_model.id)

                        if self.start_job(chat_model_state):
                            chat_model_state.put()
                            chat_model_state.progress_message_id = send_message(loc.job_started)
                            chat_model_state.put()
                        else:
                            send_message(loc.job_error)
                    else:
                        chat_model_state.put()
                        send_message(loc.send_next_style_prompt(actual=style_count + 1,
                                                                total=chat_model_state.parameters.style_count))

    def start_job(self, chat_model_state):
        job_name = "???"
        try:
            job_name = self.ml.new_job_id(chat_model_state.chat_id)
            folder = "jobs/" + job_name
            self.move_to_storage(chat_model_state.content_file_id, folder + "/content.jpg")
            index = 1
            for style_file_id in chat_model_state.style_file_id:
                self.move_to_storage(style_file_id, "%s/style%d.jpg" % (folder, index))
                index = index + 1
            chat_model_state.job_name = job_name
            self.ml.create_job(chat_model_state)
            chat_model_state.step = "processing"
            chat_model_state.started = datetime.now()
            self.logger.info(
                "Successfully started job. Job name: %s, chat id: %d." % (job_name, chat_model_state.chat_id),
                exc_info=True)
            return True
        except:
            self.logger.error(
                "Error creating job. Job name: %s, chat id: %d." % (job_name, chat_model_state.chat_id),
                exc_info=True)
            return False

    def process_callback_query(self, chat_model, data, message_id=None):
        update_callback = None
        if data.startswith("style_weight="):
            new_style_weight = self.try_parse_float_in_bounds(data[len("style_weight="):], 0.1, 10.0, 1)

            if new_style_weight:
                chat_model.default_parameters.style_weight = new_style_weight
                update_callback = self.send_style_weight_setting
        elif data.startswith("style_scale="):
            new_style_scale = self.try_parse_float_in_bounds(data[len("style_scale="):], 0.1, 3.0, 1)

            if new_style_scale:
                chat_model.default_parameters.style_scale = new_style_scale
                update_callback = self.send_style_scale_setting
        elif data.startswith("style_count="):
            new_style_count = self.try_parse_int_in_bounds(data[len("style_count="):],
                                                           1, chat_model.style_count_max)

            if new_style_count:
                chat_model.default_parameters.style_count = new_style_count
                update_callback = self.send_style_count_setting
        elif data.startswith("num_iter="):
            new_num_iter = self.try_parse_int_in_bounds(data[len("num_iter="):],
                                                        1, chat_model.num_iter_max)

            if new_num_iter:
                chat_model.default_parameters.num_iter = new_num_iter
                update_callback = self.send_num_iter_setting
        elif data.startswith("img_size="):
            new_img_height = self.try_parse_int_in_bounds(data[len("img_size="):],
                                                          100, chat_model.img_height_max, -1)

            if new_img_height:
                chat_model.default_parameters.img_height = new_img_height
                update_callback = self.send_img_height_setting
        elif data.startswith("preserve_color="):
            new_value = data[len("preserve_color="):]

            if new_value == "True":
                new_value = True
            elif new_value == "False":
                new_value = False
            else:
                new_value = None

            if new_value is not None:
                chat_model.default_parameters.preserve_color = new_value
                update_callback = self.send_img_height_setting

        if update_callback:
            chat_model.put()
            update_callback(chat_model, message_id)
            return True
        else:
            return False

    @staticmethod
    def try_parse_float_in_bounds(data, min_value, max_value, round_digits):
        try:
            return round(min(max(float(data), min_value), max_value), round_digits)
        except ValueError:
            return None

    @staticmethod
    def try_parse_int_in_bounds(data, min_value, max_value, round_digits=0):
        try:
            return int(round(min(max(int(data), min_value), max_value), round_digits))
        except ValueError:
            return None

    def send_style_weight_setting(self, chat_model, message_id=None):
        loc, _ = self.loc(chat_model)
        style_weight = chat_model.default_parameters.style_weight
        text = loc.style_weight_caption(value=style_weight)
        keyboard = self.bot.to_inline_keyboard([
            self.build_setting_keyboard("style_weight", style_weight, 0.1, 0.5, 1)])

        if message_id:
            self.bot.edit_message(chat_model.id, message_id, text, reply_markup=keyboard)
        else:
            self.bot.send_message(chat_model.id, text, reply_markup=keyboard)

    def send_style_scale_setting(self, chat_model, message_id=None):
        loc, _ = self.loc(chat_model)
        style_scale = chat_model.default_parameters.style_scale
        text = loc.style_scale_caption(value=style_scale)
        keyboard = self.bot.to_inline_keyboard([
            self.build_setting_keyboard("style_scale", style_scale, 0.1, 0.5, 1)])

        if message_id:
            self.bot.edit_message(chat_model.id, message_id, text, reply_markup=keyboard)
        else:
            self.bot.send_message(chat_model.id, text, reply_markup=keyboard)

    def send_style_count_setting(self, chat_model, message_id=None):
        loc, _ = self.loc(chat_model)
        style_count = chat_model.default_parameters.style_count
        text = loc.style_count_caption(count=style_count)
        keyboard = self.bot.to_inline_keyboard([
            self.build_setting_keyboard("style_count", style_count, 1, 5, 0)])

        if message_id:
            self.bot.edit_message(chat_model.id, message_id, text, reply_markup=keyboard)
        else:
            self.bot.send_message(chat_model.id, text, reply_markup=keyboard)

    def send_num_iter_setting(self, chat_model, message_id=None):
        loc, _ = self.loc(chat_model)
        num_iter = chat_model.default_parameters.num_iter
        text = loc.num_iter_caption(count=num_iter)
        keyboard = self.bot.to_inline_keyboard([
            self.build_setting_keyboard("num_iter", num_iter, 1, 5, 0)])

        if message_id:
            self.bot.edit_message(chat_model.id, message_id, text, reply_markup=keyboard)
        else:
            self.bot.send_message(chat_model.id, text, reply_markup=keyboard)

    def send_img_height_setting(self, chat_model, message_id=None):
        loc, _ = self.loc(chat_model)
        img_height = chat_model.default_parameters.img_height
        preserve_color = chat_model.default_parameters.preserve_color
        preserve_color_text = loc.preserve_color_caption if preserve_color else loc.dont_preserve_color_caption
        text = loc.img_size_caption(size=img_height)
        keyboard = self.bot.to_inline_keyboard([
            self.build_setting_keyboard("img_size", img_height, 10, 50, -1),
            [
                ("preserve_color=%s" % (not preserve_color), preserve_color_text)
            ]])

        if message_id:
            self.bot.edit_message(chat_model.id, message_id, text, reply_markup=keyboard)
        else:
            self.bot.send_message(chat_model.id, text, reply_markup=keyboard)

    def move_to_storage(self, file_id, gs_path):
        with gcs.open(self.gs_base_url + gs_path, "w", content_type="image/jpeg") as f:
            Image.open(self.bot.open_photo(file_id)).save(f, "JPEG")

    @staticmethod
    def build_setting_keyboard(name, value, small_change, large_change, digits):
        format = "%d" if digits <= 0 else "%%0.%df" %  digits
        key = "%s=%s" % (name, format)
        return [
            (key % round(value + large_change, digits), "+" + format % large_change),
            (key % round(value + small_change, digits), "+" + format % small_change),
            (key % round(value - small_change, digits), "-" + format % small_change),
            (key % round(value - large_change, digits), "-" + format % large_change)]
