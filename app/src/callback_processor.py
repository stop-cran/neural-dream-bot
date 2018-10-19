from datetime import datetime
import cloudstorage as gcs
from data_model import Chat, State
from i18n import get_loc


class CallbackProcessor:
    def __init__(self, loc, bot, ml, logger):
        self.loc = get_loc(self, loc)
        self.bot = bot
        self.ml = ml
        self.logger = logger

    def on_progress(self, chat_id, job_name, step):
        self.logger.info("Complete callback for chat id %s, step: %s" % (chat_id, step))

        chat_model = Chat.get_by_id(int(chat_id))

        if chat_model:
            loc, _ = self.loc(chat_model)

            chat_model_state = State.get_by_chat_id_and_job_name(chat_model.id, job_name)

            if chat_model_state:
                self.bot.edit_message(chat_model_state.chat_id,
                                      chat_model_state.progress_message_id,
                                      loc.job_progress(
                                          actual=int(step),
                                          total=chat_model_state.parameters.num_iter))
        else:
            self.logger.info("No such a chat: %s" % chat_id)

    def on_completed(self, chat_id, job_name, gs_url):
        self.logger.info("Complete callback for chat id %s, results URL: %s" % (chat_id, gs_url))

        chat_model = Chat.get_by_id(int(chat_id))

        if chat_model:
            loc, send_message = self.loc(chat_model)
            try:
                with gcs.open(gs_url, "r") as gs_file:
                    result_file_id = self.bot.send_photo(chat_model.id, gs_file, loc.job_completed)

                chat_model_state = State.get_by_chat_id_and_job_name(chat_model.id, job_name)

                if chat_model_state is not None:
                    if chat_model.state is not None:
                        if chat_model.state.id() == chat_model_state.key.id():
                            chat_model.state = None
                            chat_model.put()

                    chat_model_state.result_file_id = result_file_id
                    chat_model_state.completed = datetime.now()
                    chat_model_state.consumed_ml_units = self.ml.get_consumed_ml_units(chat_model_state.job_name)
                    chat_model_state.step = "completed"
                    chat_model_state.progress_message_id = None
                    chat_model_state.put()
            except:
                self.logger.error("Error sending file %s to chat %s." % (gs_url, chat_model.id), exc_info=True)
                self.bot.send_message(loc.job_error)
        else:
            self.logger.info("No such a chat: %s" % chat_id)

    def on_error(self, chat_id, job_name, error):
        self.logger.info("Error callback for chat id %s, error: %s." % (chat_id, error))

        chat_model = Chat.get_by_id(int(chat_id))

        if chat_model:
            loc, send_message = self.loc(chat_model)
            chat_model_state = State.get_by_chat_id_and_job_name(chat_model.id, job_name)

            if chat_model_state:
                if chat_model.state:
                    if chat_model.state.id() == chat_model_state.key.id():
                        chat_model.state = None
                        chat_model.put()

                chat_model_state.completed = datetime.now()
                chat_model_state.consumed_ml_units = self.ml.get_consumed_ml_units(chat_model_state.job_name)
                chat_model_state.step = "error"
                chat_model_state.progress_message_id = None
                chat_model_state.put()

            send_message(loc.job_error)
        else:
            self.logger.info("No such a chat: %s" % chat_id)
