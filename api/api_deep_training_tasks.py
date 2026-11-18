"""
深度训练任务相关接口
"""
import json
import time
from api import api_login
from common.Request_Response import ApiClient
from common.product_info import ProductInfoResolverMixin

env = api_login.url
time_str = time.strftime("%Y%m%d%H%M%S", time.localtime())


# --------------------------------深度训练任务列表页--------------------------------
class ApiDeepTrainTasks:
    def __init__(self, client: ApiClient):
        self.client = client

    # 查询深度训练任务
    def query_train_tasks(self, task_name, page_size=10):
        url = f"{env}/miai/brainstorm/train/task/page"
        payload = {
            "data": {
                "productCode": "",
                "onlySelf": True,
                "onlyMachineTable": False,
                "taskName": task_name,
                "caseId": ""
            },
            "page": {
                "pageIndex": 1,
                "pageSize": page_size
            }
        }

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 删除深度训练任务
    def delete_train_tasks(self, trainTaskId):
        url = f"{env}/miai/brainstorm/train/task/delete/{trainTaskId}"
        payload = None

        response = self.client.post_with_retry(url, json=payload)
        return response


# --------------------------------数据管理页--------------------------------
class ApiDataManagement(ProductInfoResolverMixin):
    def __init__(self, client: ApiClient):
        self.client = client
        self._product_info_id = None

    # 移除训练集样本
    def remove_sample_train(self, trainTaskId, productId, sample_id):
        url = f"{env}/miai/brainstorm/train/task/split/trainDelete"
        payload = {"updateDate": [], "endTime": None, "startTime": None, "updateStartTime": None, "updateEndTime": None,
                   "datasetType": [0], "trainTaskId": trainTaskId, "imgName": "", "visualGrade": [],
                   "errorTag": [], "productId": productId, "defectName": [], "dataStatus": [],
                   "photoId": [], "updateTime": [], "classifyType": [], "imageDefinition": [], "sampleType": [],
                   "difficultTag": [], "sampleSource": [], "createTime": [], "datasetRecordId": "", "taskType": 1,
                   "ids": sample_id, "notSelectIds": []}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 移除验证集样本
    def remove_sample_verify(self, trainTaskId, productId, sample_id):
        url = f"{env}/miai/brainstorm/train/task/split/verifyDelete"
        payload = {"endTime": None, "startTime": None, "updateStartTime": None, "updateEndTime": None,
                   "datasetType": [1], "trainTaskId": trainTaskId, "imgName": "", "updateDate": [],
                   "visualGrade": [], "errorTag": [], "productId": productId, "defectName": [],
                   "dataStatus": [], "photoId": [], "updateTime": [], "classifyType": [], "imageDefinition": [],
                   "sampleType": [], "difficultTag": [], "sampleSource": [], "createTime": [], "datasetRecordId": "",
                   "taskType": 1, "ids": sample_id, "notSelectIds": []}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 异常标注分析(datasetType=0表示训练集，1表示验证集)
    def abnormal_annotation_analysis(self, datasetType, trainTaskId):
        url = f"{env}/miai/brainstorm/train/task/split/errorTagAnalysis"
        payload = {"datasetType": datasetType, "trainTaskId": trainTaskId}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 数据管理-导出样本(datasetType=0表示训练集，1表示验证集)
    def export_sample(self, datasetType, trainTaskId):
        url = f"{env}/miai/brainstorm/train/task/split/trainOutput"
        payload = {"updateDate": [], "endTime": None, "startTime": None, "updateStartTime": None, "updateEndTime": None,
                   "datasetType": [datasetType], "trainTaskId": trainTaskId, "imgName": "", "defectName": [],
                   "imageDefinition": [], "photoId": [], "productId": [], "sampleType": [], "visualGrade": [],
                   "sampleSource": [], "datasetRecordId": "", "errorTag": [], "dataStatus": [], "updateTime": [],
                   "classifyType": [], "difficultTag": [], "createTime": [], "ids": [], "notSelectIds": [],
                   "outputRange": 1, "taskType": 1}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 数据管理-查看操作记录(datasetType=0表示训练集，1表示验证集)
    def view_operation_record(self, trainTaskId, datasetType):
        url = f"{env}/miai/brainstorm/datasetRecord/page"
        payload = {"data": {"datasetType": datasetType, "trainTaskId": trainTaskId, "viewType": "split"},
                   "page": {"pageIndex": 1, "pageSize": 10}}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 数据管理-列表页查询(datasetType=0表示训练集，1表示验证集)
    def query_data_list(self, trainTaskId, datasetType):
        url = f"{env}/miai/brainstorm/train/task/split/es/page"
        payload = {"data": {"updateDate": [], "endTime": None, "startTime": None, "updateStartTime": None,
                            "updateEndTime": None, "datasetType": [datasetType], "trainTaskId": trainTaskId,
                            "imgName": "", "visualGrade": [], "errorTag": [], "productId": [], "defectName": [],
                            "dataStatus": [], "photoId": [], "updateTime": [], "classifyType": [],
                            "imageDefinition": [], "sampleType": [], "difficultTag": [], "sampleSource": [],
                            "createTime": [], "datasetRecordId": ""}, "page": {"pageIndex": 1, "pageSize": 10}}

        response = self.client.post_with_retry(url, json=payload)
        return response


# --------------------------------模型训练--------------------------------
class ApiModelTrain:
    def __init__(self, client: ApiClient):
        self.client = client

    # 目标检测/实例分割模型方案查询
    def query_model(self):
        url = f"{env}/miai/brainstorm/algorithmcase/list/1"

        response = self.client.post_with_retry(url, json=None)
        return response

    # 图像分类模型方案查询
    def query_model_cls(self):
        url = f"{env}/miai/brainstorm/algorithmcase/list/2"

        response = self.client.post_with_retry(url, json=None)
        return response

    # 训练机器查询
    def query_machine(self):
        url = f"{env}/miai/brainstorm/computingpower/enabledcomputinglist/1"

        response = self.client.post_with_retry(url, json=None)
        return response

    # 开始模型训练
    def start_train(self, Width, Height, caseId, modelSize, computingPowerId, epoch, batchSize, lr,
                    trainTaskId, modelCaseTemplateId):
        url = f"{env}/miai/brainstorm/newmodeltrain/startTrain"
        payload = {"openMoreParam": False, "hyperparameters": None, "resizeWidth": Width, "resizeHeight": Height,
                   "caseId": caseId, "modelSize": modelSize, "gpuSize": 999, "source": 0, "keepLabels": [],
                   "computingPowerId": computingPowerId, "trainParams": True, "schemePhase": 1, "modelVersion": None,
                   "paramSetting1": {"epoch": epoch, "batchSize": batchSize, "lr": lr}, "paramSetting2": None,
                   "trainTaskId": trainTaskId, "remark": f"接口自动化训练-{time_str}",
                   "modelCaseTemplateId": modelCaseTemplateId}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 训练记录查询
    def query_train_records(self, trainTaskId):
        url = f"{env}/miai/brainstorm/newmodeltrain/page"
        payload = {"data": {"trainTaskId": trainTaskId, "onlyMachineTable": False},
                   "page": {"pageIndex": 1, "pageSize": 1000}}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 模型提交
    def submit_model(self, modelName, modelTrainId):
        url = f"{env}/miai/brainstorm/newmodeltrain/submit"
        payload = {"modelName": modelName, "sides": [{"photoId": "", "productCode": "", "productId": 0}],
                   "modelThreshold": 0.1, "iouThreshold": 0.45, "modelTrainId": modelTrainId}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 模型删除
    def delete_model(self, modelTrainId):
        url = f"{env}/miai/brainstorm/newmodeltrain/delete/{modelTrainId}"

        response = self.client.post_with_retry(url, json=None)
        return response

    # 终止训练
    def stop_train(self, modelTrainId):
        url = f"{env}/miai/brainstorm/newmodeltrain/stopTrain/{modelTrainId}"

        response = self.client.post_with_retry(url, json=None)
        return response


# --------------------------------后处理--------------------------------
class ApiPostProcess:
    def __init__(self, client: ApiClient):
        self.client = client

    # 报表分析
    def report_analysis(self, verifyId):
        url = f"{env}/miai/brainstorm/model/verify/report/reanalysis"
        payload = {"verifyId": verifyId,
                   "thresholds": [{"showName": "全局阈值", "label": "all", "score": "0.05"}],
                   "filterNonDetection": False}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 报表分析-状态查询
    def report_analysis_status(self, verifyId):
        url = f"{env}/miai/brainstorm/model/verify/processStatus/{verifyId}"

        response = self.client.post_with_retry(url, json=None)
        return response

    # 样本分析
    def sample_analysis(self, verifyId):
        url = f"{env}/miai/brainstorm/model/verify/report/sampleAnalysis/{verifyId}"

        response = self.client.post_with_retry(url, json=None)
        return response

    # 样本分析-状态查询
    def sample_analysis_status(self, verifyId):
        url = f"{env}/miai/brainstorm/model/verify/processStatus/{verifyId}"

        response = self.client.post_with_retry(url, json=None)
        return response

    # 查询过检样本
    def query_over_samples(self, verifyId):
        url = f"{env}/miai/brainstorm/es/sample/analysis/overkillPage"
        payload = {"data": {"visualGrade": [None], "productId": [None], "defectName": [None], "photoId": [None],
                            "classifyType": [None], "sampleType": [None], "imageDefinition": [None],
                            "sampleStatus": [None], "preLabel": [None], "modelVerifyId": verifyId,
                            "sortDirection": 0, "imgName": "", "score": 1, "scoreType": 1},
                   "page": {"pageIndex": 1, "pageSize": 16}}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 查询漏检样本
    def query_miss_samples(self, verifyId):
        url = f"{env}/miai/brainstorm/es/sample/analysis/lossPage"
        payload = {"data": {"modelVerifyId": verifyId, "sortDirection": 0, "imgName": ""},
                   "page": {"pageIndex": 1, "pageSize": 16}}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 查询错检样本
    def query_error_samples(self, verifyId):
        url = f"{env}/miai/brainstorm/es/sample/analysis/wrongDetectionPage"
        payload = {"data": {"modelVerifyId": verifyId, "sortDirection": 0, "imgName": "", "score": 1,
                            "scoreType": 1}, "page": {"pageIndex": 1, "pageSize": 16}}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 查询图片中GT/PRE数据
    def query_gt_pre_data(self, image_id, verifyId):
        url = f"{env}/miai/brainstorm/es/sample/analysis/getGtPre"
        payload = {"id": image_id, "modelVerifyId": verifyId}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 标记/取消标记
    def batch_mark(self, defect_id, postprocess_label, verifyId, image_id, img_name):
        url = f"{env}/miai/brainstorm/es/sample/analysis/setPostProcessLabel"
        payload = {"defectIdList": [defect_id], "postProcessLabel": postprocess_label,
                   "modelVerifyId": verifyId, "id": image_id,
                   "imgName": img_name}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 拷贝到训练集(copy_type: 0-过检, 1-漏检, 2-错检)
    def copy_to_trainset(self, train_task_id, num, verifyId, image_id, copy_type):
        url = f"{env}/miai/brainstorm/es/sample/analysis/copytotrain"
        payload = {"targetTrainTaskId": train_task_id, "cutNum": num, "modelVerifyId": verifyId,
                   "imgName": "", "selectIds": [image_id], "notSelectIds": [], "type": copy_type, "visualGrade": [None],
                   "productId": [None], "defectName": [None], "photoId": [None], "classifyType": [None],
                   "imageDefinition": [None], "sampleType": [None], "sampleStatus": [None], "gtLabel": [None],
                   "postProcessLabel": [None]}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 分类切图查看样本分析
    def classify_cutting(self, class_verifyId):
        url = f"{env}/miai/brainstorm/es/sample/analysis/page"
        payload = {"data": {"visualGrade": [None], "productId": [None], "defectName": [None], "photoId": [None],
                            "classifyType": [None], "imageDefinition": [None], "sampleType": [None], "preLabel": [None],
                            "gtLabel": [None], "modelVerifyId": class_verifyId, "sortDirection": 0,
                            "imgName": "", "score": 1, "scoreType": 1}, "page": {"pageIndex": 1, "pageSize": 16}}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 分类切图拷贝增广
    def class_copy(self, class_trainTaskId, class_verifyId, copy_id):
        url = f"{env}/miai/brainstorm/es/sample/analysis/classify/copy"
        payload = {"targetTrainTaskId": class_trainTaskId, "cutNum": 5, "modelVerifyId": class_verifyId,
                   "imgName": "", "selectIds": copy_id, "notSelectIds": [],
                   "visualGrade": [None], "productId": [None], "defectName": [None], "photoId": [None],
                   "classifyType": [None], "imageDefinition": [None], "sampleType": [None], "preLabel": [None],
                   "gtLabel": [None]}

        response = self.client.post_with_retry(url, json=payload)
        return response


if __name__ == '__main__':
    pass
