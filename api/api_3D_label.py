"""
3d标注相关接口
"""
import time
import random
from api import api_login
from common.Request_Response import ApiClient
from common.product_info import ProductInfoResolverMixin

env = api_login.url
time_str = time.strftime("%Y%m%d%H%M%S", time.localtime())


class Api3DLabel(ProductInfoResolverMixin):
    def __init__(self, client: ApiClient):
        self.client = client
        self._product_info_id = None

    # 查询3D样本库
    def query_3d_sample(self, startDateTime, endDateTime, sortingSampleType, isUse, status):
        url = f"{env}/miai/brainstorm/threedim/sampleproductsyncmanage/sample/page"
        payload = {
            "data": {"date": [f"{startDateTime}T16:00:00.000Z", f"{endDateTime}T15:59:59.000Z"], "dataSyncIds": [],
                     "sampleSource": "2", "taskId": "", "workpieceId": "", "deviceId": "",
                     "sortingSampleType": "", "statusList": [], "startDateTime": f"{startDateTime}T16:00:00.000Z",
                     "endDateTime": f"{endDateTime}T15:59:59.000Z", "productInfoId": self.product_info_id,
                     "isUse": None, "status": 1}, "page": {"pageIndex": 1, "pageSize": 15}}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 分拣3D样本
    def sort_3d_sample(self, sampleDataSyncId, sortingSampleType):
        url = f"{env}/miai/brainstorm/threedim/sampleproductsyncmanage/classify"

        # 参数逻辑判断
        if sortingSampleType == "ng":
            sortingSampleTypeDetail = random.choice([0, 9])  # 随机选择0或9
        elif sortingSampleType == "ok":
            sortingSampleTypeDetail = 4
        else:
            raise ValueError("sortingSampleType值无效，只允许“ng”或“ok”")

        payload = {
            "sampleDataSyncId": sampleDataSyncId,
            "sortingSampleType": sortingSampleType,
            "sortingSampleTypeDetail": sortingSampleTypeDetail
        }

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 创建3D标注任务
    def create_3d_label_task(self, taskName, startDateTime, endDateTime, dataSyncIds):
        url = f"{env}/miai/brainstorm/threedim/sampleproductsyncmanage/addSampleToTask"
        payload = {"taskName": taskName, "dimensionTaskList": [
            {"labelUsers": [{"labelUserId": "1000000000000000002", "labelUserName": "示例用户测试使用"}],
             "taskName": f"{taskName}-1"}], "subTaskNum": 1, "subTaskSampleNum": 100,
                   "date": [f"{startDateTime}T16:00:00.000Z", f"{endDateTime}T15:59:59.000Z"],
                   "dataSyncIds": dataSyncIds, "sampleSource": "2", "taskId": "", "workpieceId": "",
                   "deviceId": "", "sortingSampleType": "ng", "statusList": [],
                   "startDateTime": f"{startDateTime}T16:00:00.000Z", "endDateTime": f"{endDateTime}T15:59:59.000Z",
                   "productInfoId": self.product_info_id, "isUse": False, "status": 2, "excludeDataSyncIds": []}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 查询可追加的3D标注任务
    def query_append_3d_task(self):
        url = f"{env}/miai/brainstorm/threedim/sampleproductsyncmanage/dimension/canAppend"
        payload = {}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 追加3D标注任务
    def append_3d_label_task(self, startDateTime, endDateTime, dataSyncIds, dimensionTaskId):
        url = f"{env}/miai/brainstorm/threedim/sampleproductsyncmanage/appendToTask"
        payload = {"date": [f"{startDateTime}T16:00:00.000Z", f"{endDateTime}T15:59:59.000Z"],
                   "dataSyncIds": dataSyncIds,
                   "sampleSource": "2", "taskId": "", "workpieceId": "", "deviceId": "", "sortingSampleType": "ng",
                   "statusList": [], "startDateTime": f"{startDateTime}T16:00:00.000Z",
                   "endDateTime": f"{endDateTime}T15:59:59.000Z", "productInfoId": self.product_info_id, "isUse": False,
                   "status": 2, "excludeDataSyncIds": [], "dimensionId": dimensionTaskId}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 创建提交3Dok数据集
    def ok_graph_create_dataset(self, name, startDateTime, endDateTime, dataSyncIds):
        url = f"{env}/miai/brainstorm/threedim/sampleproductsyncmanage/addSampleToDataset"
        payload = {"name": name, "testPercent": 0, "trainPercent": 100,
                   "date": [f"{startDateTime}T16:00:00.000Z", f"{endDateTime}T15:59:59.999Z"],
                   "dataSyncIds": dataSyncIds, "sampleSource": "2", "taskId": "", "workpieceId": "",
                   "deviceId": "", "sortingSampleType": "ok", "statusList": [],
                   "startDateTime": f"{startDateTime}T16:00:00.000Z", "endDateTime": f"{endDateTime}T15:59:59.999Z",
                   "productInfoId": self.product_info_id, "isUse": False, "status": 2, "excludeDataSyncIds": []}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 查询3D数据集
    def query_3d_dataset(self):
        url = f"{env}/miai/brainstorm/threedim/datasetinfo/train/page"
        payload = {"data": {"datasetType": 0, "endTime": "", "sampleSource": None, "sampleType": "", "status": None,
                            "startTime": "", "commitUser": ""}, "page": {"pageIndex": 1, "pageSize": 10}}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 3D数据集撤回
    def dataset_3d_withdraw(self, datasetId):
        url = f"{env}/miai/brainstorm/threedim/datasetinfo/revocation/{datasetId}"
        payload = None

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 发起3D重标
    def dataset_3d_relabel(self, datasetId):
        url = f"{env}/miai/brainstorm/threedim/datasetinfo/relabel/{datasetId}"
        payload = None

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 查询3D标注任务
    def query_3d_task(self):
        url = f"{env}/miai/brainstorm/threedim/dimensiontask/page"
        payload = {"data": {"taskStatus": None, "labelUser": "", "startTime": "", "endTime": "", "taskName": ""},
                   "page": {"pageIndex": 1, "pageSize": 10}}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 3D任务标注/重标（变更状态为：进行中）
    def change_3d_task_status(self, dimensionTaskId):
        url = f"{env}/miai/brainstorm/threedim/dimensiontask/update3"
        payload = {"dimensionTaskId": dimensionTaskId, "taskStatus": 2}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 获取3D样本dimensionDataId
    def query_3d_dimensiondataid(self, dimensionTaskId):
        url = f"{env}/miai/brainstorm/threedim/dimensiontaskdatalist/list"
        payload = {"dimensionTaskId": dimensionTaskId, "status": 2}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 获取标注标签
    def query_3d_label(self):
        url = f"{env}/miai/brainstorm/labelinfo/productCode?spaceType=1"
        payload = None

        response = self.client.post_with_retry(url, json=payload)
        return response


    # 3D标注
    def label_3d(self, dataId, points, label, confusionType):
        url = f"{env}/miai/brainstorm/threedim/dimensiontaskdatalist/saveLabelJson"
        payload = {"dataId": dataId, "shapes": [{"points": points, "shape_type": "polygon",
                                                 "label": label, "confusionType": confusionType}]}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 3D任务提交复核
    def three_dim_task_commit_review(self, dimensionTaskId):
        url = f"{env}/miai/brainstorm/threedim/dimensiontask/update1"
        payload = {"dimensionTaskId": dimensionTaskId, "taskStatus": 3}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 3D任务复核判定（taskStatus：8-不通过，taskStatus：4-通过）
    def three_dim_task_review_judge(self, dimensionTaskId, taskStatus):
        url = f"{env}/miai/brainstorm/threedim/dimensiontask/update2"
        payload = {"dimensionTaskId": dimensionTaskId, "taskStatus": taskStatus}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 创建&提交3D数据集
    def create_3d_dataset(self, name, dimensionTaskId):
        url = f"{env}/miai/brainstorm/threedim/dimensiontask/addTaskDataListToDataset"
        payload = {"name": name, "trainPercent": 50, "testPercent": 50,
                   "dimensionTaskId": dimensionTaskId}

        response = self.client.post_with_retry(url, json=payload)
        return response
