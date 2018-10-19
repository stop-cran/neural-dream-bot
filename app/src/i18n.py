from collections import namedtuple
import yaml
import re


def read_loc():
    with open("i18n.yaml", 'rb') as stream:
        d = yaml.load(stream)

    res = {}
    for key, items in d.items():
        for lan, value in items.items():
            if lan not in res:
                res[lan] = {}
            res[lan][key] = value

    res2 = {}
    for lan, items in res.items():
        values = [v.format if re.search('{[^}]+\}', v) else v for v in items.values()]
        res2[lan] = namedtuple("LocStrings", items.keys())(*values)
    return res2


def get_loc(obj, loc):
    def loc_helper(chat_model):
        def send_message(text):
            return obj.bot.send_message(chat_model.id, text)
        return loc(chat_model), send_message
    return loc_helper


def get_loc_strategy():
    loc_d = read_loc()

    def loc_strategy(type_to_resolve, parameter_name):
        def loc(chat_model):
            if chat_model.default_language not in ["en", "ru"]:
                chat_model.default_language = "en"
            return loc_d[chat_model.default_language]
        return loc if parameter_name == "loc" else None

    return loc_strategy
