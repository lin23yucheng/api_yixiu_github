"""
bash样本库相关接口
"""
import time
import random
from api import api_login
from common.Request_Response import ApiClient
from common.product_info import ProductInfoResolverMixin

env = api_login.url
time_str = time.strftime("%Y%m%d%H%M%S", time.localtime())


class ApiBashSample(ProductInfoResolverMixin):
    def __init__(self, client: ApiClient):
        self.client = client
        self._product_info_id = None

    # 查询bash样本库-原始样本/分拣后样本
    def query_bash_sample(self, startDateTime, endDateTime):
        url = f"{env}/miai/brainstorm/sampleproductsyncmanage/sample/page"
        payload = {"data": {"dataType": 1, "sceneSampleType": "",
                            "date": [f"{startDateTime}T16:00:00.000Z", f"{endDateTime}T15:59:59.000Z"],
                            "statusList": [],
                            "sampleSource": 1, "bashSampleType": "", "dataAlgorithmSampleType": "", "taskId": "",
                            "channelId": "", "deviceId": "", "photoId": "", "opticsSchemeId": "", "workpieceId": "",
                            "cameraId": "", "status": 1, "labelNames": [], "isUse": None, "sortingSampleType": "",
                            "productInfoId": self.product_info_id, "deepModelSampleType": "", "cvSampleType": "",
                            "bashUser": "", "isRelateOpticalSurface": False,
                            "startDateTime": f"{startDateTime}T16:00:00.000Z",
                            "endDateTime": f"{endDateTime}T15:59:59.000Z"},
                   "page": {"pageIndex": 1, "pageSize": 15}}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # bash样本库-分拣样本
    def bash_sorting_sample(self, sampledatasyncid, sortingsampletype):
        # 定义类型到详细值的映射规则
        type_detail_map = {
            "ng": [0, 8, 9],
            "ok": [1, 2, 3, 4]
        }

        # 验证输入类型是否有效
        if sortingsampletype not in type_detail_map:
            raise ValueError(f"无效的 sortingSampleType: {sortingsampletype}。只接受 'ng' 或 'ok'")

        # 随机选择对应的详细值
        sortingSampleTypeDetail = random.choice(type_detail_map[sortingsampletype])

        url = f"{env}/miai/brainstorm/sampleproductsyncmanage/classify"
        payload = {
            "productInfoId": self.product_info_id,
            "sampleDataSyncId": sampledatasyncid,
            "sortingSampleType": sortingsampletype,
            "sortingSampleTypeDetail": sortingSampleTypeDetail
        }

        response = self.client.post_with_retry(url, json=payload)
        return response

    # bash样本库-创建标注任务
    def create_label_task(self, sampledatasyncid, startDateTime, endDateTime, taskName):
        url = f"{env}/miai/brainstorm/sampleproductsyncmanage/addSampleToTask"
        payload = {"taskName": taskName, "dimensionTaskList": [
            {"labelUsers": [{"labelUserId": "1000000000000000002", "labelUserName": "示例用户测试使用"}],
             "taskName": f"{taskName}-1"}], "subTaskNum": 1, "subTaskSampleNum": 100,
                   "sceneSampleType": "",
                   "date": [f"{startDateTime}T16:00:00.000Z", f"{endDateTime}T15:59:59.000Z"], "statusList": [],
                   "sampleSource": 1, "bashSampleType": "", "dataAlgorithmSampleType": "", "taskId": "",
                   "channelId": "", "deviceId": "", "photoId": "", "opticsSchemeId": "", "workpieceId": "",
                   "cameraId": "", "status": 2, "labelNames": [], "isUse": False, "sortingSampleType": "ng",
                   "productInfoId": self.product_info_id, "dataType": 1, "deepModelSampleType": "", "cvSampleType": "",
                   "bashUser": "", "startDateTime": f"{startDateTime}T16:00:00.000Z",
                   "endDateTime": f"{endDateTime}T15:59:59.000Z", "excludeDataSyncIds": [],
                   "dataSyncIds": sampledatasyncid}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 查询可追加的标注任务
    def query_append_task_id(self):
        url = f"{env}/miai/brainstorm/sampleproductsyncmanage/dimension/canAppend"
        payload = {"sampleSource": 1}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # bash样本库-追加标注任务
    def append_label_task(self, startDateTime, endDateTime, sampledatasyncid, dimensionTaskId):
        url = f"{env}/miai/brainstorm/sampleproductsyncmanage/appendToTask"
        payload = {"sceneSampleType": "", "date": [f"{startDateTime}T16:00:00.000Z", f"{endDateTime}T15:59:59.000Z"],
                   "statusList": [], "sampleSource": 1, "bashSampleType": "", "dataAlgorithmSampleType": "",
                   "taskId": "", "channelId": "", "deviceId": "", "photoId": "", "opticsSchemeId": "",
                   "workpieceId": "", "cameraId": "", "status": 2, "labelNames": [], "isUse": False,
                   "sortingSampleType": "ng", "productInfoId": self.product_info_id, "dataType": 1,
                   "deepModelSampleType": "", "cvSampleType": "", "bashUser": "",
                   "startDateTime": f"{startDateTime}T16:00:00.000Z", "endDateTime": f"{endDateTime}T15:59:59.000Z",
                   "excludeDataSyncIds": [], "dataSyncIds": sampledatasyncid,
                   "dimensionId": dimensionTaskId}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # bash样本库-ok图创建提交数据集
    def ok_graph_create_dataset(self, name, startDateTime, endDateTime, dataSyncIds):
        url = f"{env}/miai/brainstorm/sampleproductsyncmanage/addSampleToDataset"
        payload = {"name": name, "testPercent": 0, "trainPercent": 100, "sceneSampleType": "",
                   "date": [f"{startDateTime}T16:00:00.000Z", f"{endDateTime}T15:59:59.999Z"], "statusList": [],
                   "sampleSource": 1, "bashSampleType": "", "dataAlgorithmSampleType": "", "taskId": "",
                   "channelId": "", "deviceId": "", "photoId": "", "opticsSchemeId": "", "workpieceId": "",
                   "cameraId": "", "status": 2, "labelNames": [], "isUse": False, "sortingSampleType": "ok",
                   "productInfoId": self.product_info_id, "dataType": 1, "deepModelSampleType": "", "cvSampleType": "",
                   "bashUser": "", "startDateTime": f"{startDateTime}T16:00:00.000Z",
                   "endDateTime": f"{endDateTime}T15:59:59.999Z", "excludeDataSyncIds": [],
                   "dataSyncIds": dataSyncIds}

        response = self.client.post_with_retry(url, json=payload)
        return response
