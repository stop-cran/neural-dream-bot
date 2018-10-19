import os
import sys
import json
import logging
import webapp2
from six.moves.urllib.request import urlopen
from six.moves.urllib.parse import urlencode
from google.appengine.api import urlfetch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "lib"))

from bot import Bot
from ml import Ml
from config import get_config_strategy
from i18n import get_loc_strategy
from update_processor import Processor
from callback_processor import CallbackProcessor
from container import Container


# Set requests timeout (default is 15)
def set_timeout(timeout_in_seconds=60):
    urlfetch.set_default_fetch_deadline(timeout_in_seconds)


# Deserialize object and serialise it to JSON formatted string
def format_json(obj):
    return json.dumps(json.loads(obj.read().decode()), indent=4, sort_keys=True)


# --------------- Request handlers ---------------

class ForwardHandler(webapp2.RequestHandler):
    def __init__(self, base_url, path, *args, **kwargs):
        super(ForwardHandler, self).__init__(*args, **kwargs)

        self.url = base_url + path

    def get(self):
        set_timeout()

        response = urlopen(self.url)
        self.response.headers['Content-Type'] = 'text/plain'
        self.response.write(format_json(response))


# Set a web hook url for Telegram to POST to
class SetWebhookHandler(webapp2.RequestHandler):
    def __init__(self, base_url, hook_url, logger, *args, **kwargs):
        super(SetWebhookHandler, self).__init__(*args, **kwargs)

        self.base_url = base_url
        self.hook_url = hook_url
        self.logger = logger

    def get(self):
        set_timeout()
        self.logger.info('Setting new webhook to: %s' % self.hook_url)

        response = urlopen(self.base_url + 'setWebhook',
                           urlencode(dict(url=self.hook_url)))
        self.response.headers['Content-Type'] = 'text/plain'
        self.response.write(format_json(response))


# Handler for the web hook, called by Telegram
class WebhookHandler(webapp2.RequestHandler):
    def __init__(self, hook_token, logger, processor, *args, **kwargs):
        super(WebhookHandler, self).__init__(*args, **kwargs)

        self.hook_token = hook_token
        self.logger = logger
        self.processor = processor

    def post(self):
        set_timeout()
        self.logger.info('Received request: %s from %s' % (self.request.url, self.request.remote_addr))

        if self.hook_token in self.request.url:
            self.processor.process(json.loads(self.request.body))
        else:
            # Not coming from Telegram
            self.logger.warning('Post request without token from IP: %s' % self.request.remote_addr)


# Handler for the web hook, called by Telegram
class CallbackHandler(webapp2.RequestHandler):
    def __init__(self, callback_token, logger, callback_processor, *args, **kwargs):
        super(CallbackHandler, self).__init__(*args, **kwargs)

        self.callback_token = callback_token
        self.logger = logger
        self.callback_processor = callback_processor

    def get(self):
        set_timeout()
        self.logger.info('Received request: %s from %s' % (self.request.url, self.request.remote_addr))

        if self.callback_token in self.request.url:
            chat_id = self.request.get('chat_id')
            job_name = self.request.get('job_name')
            error = self.request.get('error')
            gs_url = self.request.get('gs_url')
            step = self.request.get('step')

            if (error or '') != '':
                self.callback_processor.on_error(chat_id, job_name, error)
            elif (gs_url or '') != '':
                self.callback_processor.on_completed(chat_id, job_name, gs_url)
            elif (step or '') != '':
                self.callback_processor.on_progress(chat_id, job_name, step)
        else:
            # Not coming from the task
            self.logger.warning('Callback post request without token from IP: %s' % self.request.remote_addr)


def auto_logger(type_to_resolve, parameter_name):
    return logging.getLogger(type_to_resolve.__name__) if parameter_name == 'logger' else None


def resolve_handlers():
    container = Container()
    container.add_strategies(auto_logger, get_config_strategy(), get_loc_strategy())
    container.register_types(Bot, Ml, Processor, CallbackProcessor)

    return [
        ('/me', container.resolve_partial(ForwardHandler, path='getMe')),
        ('/set_webhook', container.resolve_partial(SetWebhookHandler)),
        ('/get_webhook', container.resolve_partial(ForwardHandler, path='getWebhookInfo')),
        ('/del_webhook', container.resolve_partial(ForwardHandler, path='deleteWebhook')),
        (r'/TG.*', container.resolve_partial(WebhookHandler)),
        (r'/Callback.*', container.resolve_partial(CallbackHandler))]


app = webapp2.WSGIApplication(resolve_handlers(), debug=True)
