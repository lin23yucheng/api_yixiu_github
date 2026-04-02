"""
深度训练任务相关接口
"""
import json
import time
from api import api_login, api_space
from common.Request_Response import ApiClient

env = api_login.url
time_str = time.strftime("%Y%m%d%H%M%S", time.localtime())

# 初始化全局客户端
base_headers = {
    "Authorization": api_login.ApiLogin().login(),
    "Miai-Product-Code": api_login.code,
    "Miaispacemanageid": api_login.manageid
}
global_client = ApiClient(base_headers=base_headers)


# --------------------------------深度训练任务列表页--------------------------------
class ApiDeepTrainTasks:
    def __init__(self, client: ApiClient):
        self.client = client
        self.product_info_id = api_space.ApiSpace().product_query()

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


# --------------------------------模型训练--------------------------------
class ApiModelTrain:
    def __init__(self, client: ApiClient):
        self.client = client
        self.product_info_id = api_space.ApiSpace().product_query()

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


# --------------------------------后处理--------------------------------
class ApiPostProcess:
    def __init__(self, client: ApiClient):
        self.client = client
        self.product_info_id = api_space.ApiSpace().product_query()

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
    product_id = api_space.ApiSpace().product_query()
    api = ApiModelTrain(global_client)

    query_model_data = api.query_model()
    print("模型方案接口返回JSON:")
    print(json.dumps(query_model_data.json(), indent=2, ensure_ascii=False))
    # print('-' * 100)
    # query_machine_data = api.query_machine()
    # print("训练机器接口返回JSON:")
    # print(json.dumps(query_machine_data.json(), indent=2, ensure_ascii=False))
