import os


def get_config_strategy():
    api_token = os.environ['API_TOKEN']
    hook_token = os.environ['HOOK_TOKEN']
    project_id = os.environ['PROJECT_ID']
    callback_token = os.environ['TASK_CALLBACK_TOKEN']

    config = dict(
        base_url='https://api.telegram.org/bot%s/' % api_token,
        file_url='https://api.telegram.org/file/bot%s/' % api_token,
        hook_token=hook_token,
        hook_url='https://%s.appspot.com/TG%s' % (project_id, hook_token),
        callback_token=callback_token,
        callback_url='https://%s.appspot.com/Callback%s' % (project_id, callback_token),
        project_id=project_id,
        gs_base_url='/%s.appspot.com/' % project_id,
        support_chat_id=int(os.environ['SUPPORT_CHAT_ID'])
    )

    def config_strategy(type_to_resolve, parameter_name):
        return config.get(parameter_name)

    return config_strategy
