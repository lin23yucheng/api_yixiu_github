"""
EIIR空间训练任务相关接口
"""
import time
from api import api_login
from common.Request_Response import ApiClient

env = api_login.url
time_str = time.strftime("%Y%m%d%H%M%S", time.localtime())


class ApiEiirTraining:
    def __init__(self, client: ApiClient):
        self.client = client

    # 查询EIIR训练任务列表页
    def query_eiir_task(self, taskName):
        url = f"{env}/miai/brainstorm/eiir/traintask/mypage"
        payload = {"data": {"trainTaskType": "", "taskName": taskName, "startTime": None, "endTime": None},
                   "page": {"pageIndex": 1, "pageSize": 10}}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 删除EIIR训练任务
    def delete_eiir_task(self, trainTaskId):
        url = f"{env}/miai/brainstorm/eiir/traintask/delete/{trainTaskId}"
        response = self.client.post_with_retry(url, json=None)
        return response

    # 查询EIIR训练机器
    def query_eiir_machine(self):
        url = f"{env}/miai/brainstorm/computingpower/enabledcomputinglist/3"
        payload = None

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 开始EIIR模型训练
    def create_train_task(self, computingPowerId, trainTaskId, ):
        url = f"{env}/miai/brainstorm/eiir/modeltrain/create"
        payload = {"modelCaseTemplateId": "1", "computingPowerId": computingPowerId,
                   "trainTaskId": trainTaskId, "schemePhaseConfigList": [
                {"createUser": None, "updateUser": None, "createTime": None, "updateTime": None,
                 "modelCaseTemplateConfigId": "1", "epoch": 200, "batchSize": 16, "lr": 0.01, "schemePhase": 1,
                 "resizeWidth": 1280, "resizeHeight": 736, "gpuCount": 1}]}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 查询模型训练记录
    def query_train_record(self, trainTaskId):
        url = f"{env}/miai/brainstorm/eiir/modeltrain/page"
        payload = {"data": {"trainTaskId": trainTaskId}, "page": {"pageIndex": 1, "pageSize": 10}}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # EIIR模型提交
    def submit_eiir_model(self, modelName, modelTrainId):
        url = f"{env}/miai/brainstorm/eiir/modeltrain/commit"
        payload = {"modelName": modelName, "modelTrainId": modelTrainId}

        response = self.client.post_with_retry(url, json=payload)
        return response
