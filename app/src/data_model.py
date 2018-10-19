from datetime import datetime, timedelta
from google.appengine.ext.ndb import Model, IntegerProperty, FloatProperty, StringProperty, BooleanProperty, DateTimeProperty, StructuredProperty, KeyProperty


class JobParameters(Model):
    num_iter = IntegerProperty(indexed=False, required=True, default=5)
    img_height = IntegerProperty(indexed=False, required=True, default=400)
    content_weight = FloatProperty(indexed=False, required=True, default=0.025)
    style_weight = FloatProperty(indexed=False, required=True, default=1.0)
    style_scale = FloatProperty(indexed=False, required=True, default=1.0)
    style_count = IntegerProperty(indexed=False, required=True, default=1)
    preserve_color = BooleanProperty(indexed=False, required=True, default=False)


class State(Model):
    chat_id = IntegerProperty(required=True)
    job_name = StringProperty()
    step = StringProperty(indexed=False, choices=['set_style', 'processing', 'completed', 'error'])
    compress_result = BooleanProperty(indexed=False, required=True)

    content_file_id = StringProperty(indexed=False)
    content_message_id = IntegerProperty(indexed=False)
    progress_message_id = IntegerProperty(indexed=False)
    content_from_id = IntegerProperty()
    style_file_id = StringProperty(indexed=False, repeated=True)
    result_file_id = StringProperty(indexed=False)

    created = DateTimeProperty(auto_now_add=True)
    started = DateTimeProperty()
    completed = DateTimeProperty()
    consumed_ml_units = FloatProperty(indexed=False)
    
    parameters = StructuredProperty(JobParameters)

    @classmethod
    def get_count_last_day(cls, chat_id):
        return cls.query(cls.chat_id == chat_id, cls.started >= datetime.now() - timedelta(days=1)).count()
        
    @classmethod
    def get_by_chat_id_and_job_name(cls, chat_id, job_name):
        return cls.query(cls.chat_id == chat_id, cls.job_name == job_name).get()        


class Chat(Model):
    id = IntegerProperty(indexed=True, required=True)
    num_iter_max = IntegerProperty(indexed=False, required=True, default=10)
    img_height_max = IntegerProperty(indexed=False, required=True, default=500)
    style_count_max = IntegerProperty(indexed=False, required=True, default=3)
    requests_per_day = IntegerProperty(indexed=False, required=True, default=5)
    default_language = StringProperty(indexed=False)
    created = DateTimeProperty(auto_now_add=True)
    state = KeyProperty(kind=State, indexed=False)
    last_activity = DateTimeProperty(auto_now_add=True)

    default_parameters = StructuredProperty(JobParameters, required=True, default=JobParameters())

    @classmethod
    def get_by_id(cls, chat_id):
        return cls.query(cls.id == chat_id).get()

    def get_state(self):
        return self.state.get() if self.state else None

    def put_new_state(self, content_file_id, compress_result, message_id, from_id):
        chat_model_state = State(chat_id=self.id,
                                 parameters=self.default_parameters,
                                 step="set_style",
                                 content_file_id=content_file_id,
                                 compress_result=compress_result,
                                 content_message_id=int(message_id),
                                 content_from_id=int(from_id) if from_id else None)
        self.state = chat_model_state.put()
        self.put()

        return chat_model_state

    def set_default_language(self, default_language):
        if default_language:
            self.default_language = default_language[:2]


class SupportRequest(Model):
    original_message_id = IntegerProperty(required=True)
    original_chat_id = IntegerProperty(required=True)
    original_from_id = IntegerProperty()
    support_message_id = IntegerProperty(required=True)
    replied_from_id = IntegerProperty()
    replied_message_id = IntegerProperty()

    created = DateTimeProperty(auto_now_add=True)
    replied = DateTimeProperty()

    @classmethod
    def get_by_support_message_id(cls, message_id):
        return cls.query(cls.support_message_id == message_id).get()
