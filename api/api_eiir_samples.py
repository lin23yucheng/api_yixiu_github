"""
EIIR空间检测样例相关接口
"""
import time
from api import api_login
from common.Request_Response import ApiClient

env = api_login.url
time_str = time.strftime("%Y%m%d%H%M%S", time.localtime())


class ApiEiirSamples:
    def __init__(self, client: ApiClient):
        self.client = client

    # 查询EIIR检测样本
    def query_eiir_sample(self, startTime, endTime, labelStatus):
        url = f"{env}/miai/brainstorm/eiir/sample/center/page"
        payload = {
            "data": {"sampleType": 1, "startTime": f"{startTime}T16:00:00.000Z", "endTime": f"{endTime}T15:59:59.000Z",
                     "imgName": "", "subTaskId": "", "machineId": [], "cameraId": [],
                     "labelStatus": labelStatus, "componentLabel": [], "taskId": []},
            "page": {"pageIndex": 1, "pageSize": 10}}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 创建EIIR标注任务
    def create_label_task(self, taskName, preLabelModelId, startTime, endTime, selectIds):
        url = f"{env}/miai/brainstorm/eiir/sample/center/createTask"
        payload = {"id": "", "taskName": taskName, "preLabel": True,
                   "preLabelModelId": preLabelModelId, "dimensionTaskList": [
                {"labelUsers": [{"labelUserId": "1000000000000000002", "labelUserName": "示例用户测试使用"}],
                 "taskName": f"{taskName}-1"}], "subTaskNum": 1, "subTaskSampleNum": 100, "sampleType": 1,
                   "startTime": f"{startTime}T16:00:00.000Z", "endTime": f"{endTime}T15:59:59.000Z", "imgName": "",
                   "subTaskId": "", "machineId": [], "cameraId": [], "labelStatus": ["1"], "componentLabel": [],
                   "taskId": [], "selectIds": selectIds, "notSelectIds": []}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 创建EIIR训练任务
    def create_train_task(self, taskName, startTime, endTime, machineId, componentLabel):
        url = f"{env}/miai/brainstorm/eiir/traintask/createTrainTask"
        payload = {"taskName": taskName, "trainingSetProportion": 70, "testSetProportion": 30,
                   "sampleCenterPageRequest": {"sampleType": 1, "startTime": f"{startTime}T16:00:00.000Z",
                                               "endTime": f"{endTime}T15:59:59.000Z", "imgName": "", "subTaskId": "",
                                               "machineId": machineId, "cameraId": [], "labelStatus": ["3"],
                                               "componentLabel": componentLabel, "taskId": [], "selectIds": [],
                                               "notSelectIds": []}}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 追加训练任务
    def append_train_task(self, trainTaskId, startTime, endTime, machineId, componentLabel):
        url = f"{env}/miai/brainstorm/eiir/traintask/appendTrainTask"
        payload = {"trainTaskId": trainTaskId, "datasetType": 3,
                   "sampleCenterPageRequest": {"sampleType": 1, "startTime": f"{startTime}T16:00:00.000Z",
                                               "endTime": f"{endTime}T15:59:59.000Z", "imgName": "", "subTaskId": "",
                                               "machineId": machineId, "cameraId": [], "labelStatus": ["3"],
                                               "componentLabel": componentLabel, "taskId": [], "selectIds": [],
                                               "notSelectIds": []}}

        response = self.client.post_with_retry(url, json=payload)
        return response
