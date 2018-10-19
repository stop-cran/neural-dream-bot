from datetime import datetime
from six.moves.urllib.parse import urlencode
from six.moves.urllib.error import HTTPError

from google.appengine.api import app_identity
from google.appengine.ext import ndb
from googleapiclient import discovery


class Ml:
    def __init__(self, project_id, callback_url, logger):
        self.logger = logger
        self.project_id = project_id
        self.callback_url = callback_url
        self.ml_jobs = discovery.build("ml", "v1").projects().jobs()

    def new_job_id(self, chat_id):
        prefix = "job_%s_%s_" % (str(chat_id), datetime.today().strftime("%Y_%m_%d"))
        jobs = self.list_jobs(prefix)
        job_number = len(jobs) + 1
        job_name = prefix + str(job_number)
        while job_name in jobs:
            job_number = job_number + 1
            job_name = prefix + str(job_number)
        return job_name

    def list_jobs(self, job_filter):

        response = self.ml_jobs.list(parent="projects/" + self.project_id,
                                     filter="jobId:" + job_filter).execute()

        if "jobs" in response:
            return [job["jobId"] for job in response["jobs"]]
        return []

    def get_consumed_ml_units(self, job_name):
        try:
            response = self.ml_jobs.list(parent="projects/" + self.project_id,
                                         filter="jobId:" + job_name).execute()

            return response["jobs"][0]["trainingOutput"]["consumedMLUnits"]
        except (HTTPError, KeyError, IndexError):
            self.logger.warn("Error retrieving consumed ML units for job %s." % job_name, exc_info=True)
            return None

    def create_job(self, chat_model_state):
        def args_dict(*args, **kwargs):
            def flatten(pair):
                if type(pair[1]) is list:
                    res = [str(x) for x in pair[1]]
                    res.insert(0, "--%s" % pair[0])
                    return res
                else:
                    return ["--%s" % pair[0], str(pair[1])]

            return [arg for item in dict(*args, **kwargs).items()
                    for arg in flatten(item)]

        bucket_name = "gs://%s.appspot.com" % self.project_id
        style_file_names = ['style%d.jpg' % i for i in range(1, len(chat_model_state.style_file_id) + 1)]

        request = self.ml_jobs.create(parent="projects/" + self.project_id,
                                      body=dict(
                                          jobId=chat_model_state.job_name,
                                          trainingInput=dict(
                                              args=args_dict(
                                                  content_image="content.jpg",
                                                  syle_images=style_file_names,
                                                  callback_url=self.callback_url + "?" + urlencode(dict(
                                                      chat_id=chat_model_state.chat_id,
                                                      job_name=chat_model_state.job_name)),
                                                  num_iter=chat_model_state.parameters.num_iter,
                                                  image_size=chat_model_state.parameters.img_height,
                                                  content_weight=chat_model_state.parameters.content_weight,
                                                  style_weight=chat_model_state.parameters.style_weight,
                                                  style_scale=chat_model_state.parameters.style_scale,
                                                  preserve_color=chat_model_state.parameters.preserve_color),
                                              jobDir=bucket_name + "/jobs/" + chat_model_state.job_name,
                                              masterType="complex_model_l",
                                              packageUris=[bucket_name + "/packages/neural_dream-1.0.tar.gz"],
                                              pythonModule="neural_dream.task",
                                              region="us-central1",
                                              runtimeVersion="1.7",
                                              scaleTier="CUSTOM")))

        try:
            request.execute()
        except HTTPError:
            self.logger.warn("Error starting job %s for chat %s." % (chat_model_state.job_name,
                                                                     chat_model_state.chat_id),
                             exc_info=True)
