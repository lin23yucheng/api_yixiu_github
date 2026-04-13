"""
2d标注相关接口
"""
import os
import time
from api import api_login, api_space
from common.Request_Response import ApiClient

env = api_login.url
time_str = time.strftime("%Y%m%d%H%M%S", time.localtime())


class Api2DLabel:
    def __init__(self, client: ApiClient):
        self.client = client
        self.product_info_id = api_space.ApiSpace().product_query()

    # 查询2D标注任务
    def query_2d_task(self, taskName):
        url = f"{env}/miai/brainstorm/dimensiontask/page"
        payload = {"data": {"taskStatus": None, "labelUser": "", "startTime": "", "endTime": "", "taskName": taskName},
                   "page": {"pageIndex": 1, "pageSize": 10}}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 查询标注图片
    def query_2d_sample(self, dimensionTaskId):
        url = f"{env}/miai/brainstorm/dimensiontaskdatalist/page"
        payload = {"data": {"imgName": "", "labelNames": [], "status": "2", "dimensionTaskId": dimensionTaskId},
                   "page": {"pageIndex": 1, "pageSize": 9999, "total": 0, "pages": 0}}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 获取标注标签
    def query_2d_label(self):
        url = f"{env}/miai/brainstorm/labelinfo/productCode?spaceType=1"
        payload = None

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 标注多边形
    def label_2d_polygon(self, dataId, label, shape_type, points, isDispute):
        url = f"{env}/miai/brainstorm/dimensiontaskdatalist/saveLabelJson"
        payload = {"dataId": dataId, "shapes": [
            {"disputeProcessTime": None, "disputeResult": None, "radius": "", "attributeP": "", "attributeM": "",
             "Smoothness": "", "ContrastRatio": "", "IsUneven": "", "DefectWidth": "", "DefectLength": "",
             "Brightness": "", "Area": "", "Shape": "", "confusionType": "", "checkType": "", "grade": "GQX",
             "isDispute": isDispute, "visualGrade": "S2", "definition": "QX", "customDefectField": {}, "label": label,
             "shape_type": shape_type, "width": 1,
             "points": points}],
                   "classifyType": label, "timeConsuming": 2400, "imageProperties": {"": ""}}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 标注矩形
    def label_2d_rectangle(self, dataId, label, shape_type, points, isDispute):
        url = f"{env}/miai/brainstorm/dimensiontaskdatalist/saveLabelJson"
        payload = {"dataId": dataId, "shapes": [
            {"label": label, "shape_type": shape_type, "width": 1, "radius": "",
             "points": points, "attributeP": "", "attributeM": "", "Smoothness": "",
             "ContrastRatio": "", "IsUneven": "", "DefectWidth": "", "DefectLength": "", "Brightness": "", "Area": "",
             "Shape": "", "confusionType": "", "checkType": "", "grade": "", "isDispute": isDispute, "visualGrade": "",
             "definition": "", "customDefectField": {}}], "classifyType": label, "timeConsuming": 200,
                   "imageProperties": {"": ""}}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 提交复核
    def submit_review(self, dimensionTaskId):
        url = f"{env}/miai/brainstorm/dimensiontask/update1"
        payload = {"dimensionTaskId": dimensionTaskId, "taskStatus": 3}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 复核判定（taskStatus：8-不通过，taskStatus：4-通过）
    def review_judge(self, dimensionTaskId, taskStatus):
        url = f"{env}/miai/brainstorm/dimensiontask/update2"
        payload = {"dimensionTaskId": dimensionTaskId, "taskStatus": taskStatus}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 标注/重标（变更状态为：进行中）
    def re_label(self, dimensionTaskId):
        url = f"{env}/miai/brainstorm/dimensiontask/update3"
        payload = {"dimensionTaskId": dimensionTaskId, "taskStatus": 2}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 创建&提交数据集
    def create_dataset(self, name, dimensionTaskId):
        url = f"{env}/miai/brainstorm/dimensiontask/addTaskDataListToDataset"
        payload = {"type": 0, "name": name, "trainPercent": 50, "testPercent": 50, "dimensionTaskId": dimensionTaskId,
                   "dataAlgorithmTestDatasetId": ""}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 获取争议缺陷id
    def query_dispute_defect_id(self, dataId):
        url = f"{env}/miai/brainstorm/standard/manage/detail"
        payload = {"dataId": dataId, "label": "", "disputeResult": ""}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 争议判定
    def dispute_judge(self, dataId, DateTime, dispute_id, label, points):
        url = f"{env}/miai/brainstorm/standard/manage/process"
        payload = {"canEdit": False, "dataId": dataId, "label": "", "shapes": [
            {"customDefectField": {}, "isDispute": "Dispute", "label": label, "disputeResult": "误判",
             "disputeProcessTime": f"{DateTime}T02:01:38.683Z", "score": None, "length": None, "width": 1, "radius": "",
             "flags": {}, "tag": None, "points": points,
             "position": None, "grade": "GQX", "checkType": "", "confusionType": "", "definition": "QX",
             "visualGrade": "S2", "Shape": "", "Area": "", "Brightness": "", "IsUneven": "", "ContrastRatio": "",
             "Smoothness": "", "DefectLength": "", "DefectWidth": "", "point_arr": None, "id": dispute_id,
             "data_clean_result": None, "class_type": None, "data_result": None, "data_type": None, "pixel_area": None,
             "if_model": None, "model_info": None,
             "labeller_info": {"name": "linyucheng", "date": f"{DateTime} 10:00:58"}, "shape_type": "polygon",
             "labelType": None, "group_id": None, "merge_type": None, "gt_label": None, "pre_label": None, "type": None,
             "post_process_label": None, "use_show_result_type": None, "exception_cut": None, "color": "#FF0000",
             "labelIndex": 0}]}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 争议处理
    def dispute_handle(self, dataId, DateTime, label, points):
        url = f"{env}/miai/brainstorm/standard/manage/process"
        payload = {"dataId": dataId, "shapes": [
            {"disputeProcessTime": f"{DateTime}T02:12:52.009Z", "disputeResult": "变更标准", "radius": "",
             "attributeP": "", "attributeM": "", "Smoothness": "", "ContrastRatio": "", "IsUneven": "",
             "DefectWidth": "", "DefectLength": "", "Brightness": "", "Area": "", "Shape": "", "confusionType": "",
             "checkType": "", "grade": "GQX", "isDispute": "Undispute", "visualGrade": "S2", "definition": "QX",
             "customDefectField": {}, "label": label, "shape_type": "polygon", "width": 1,
             "points": points}],
                   "classifyType": label, "canEdit": True, "label": ""}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 查询2D数据集
    def query_2d_dataset(self):
        url = f"{env}/miai/brainstorm/datasetinfo/train/page"
        payload = {"data": {"datasetType": 0, "endTime": "", "sampleSource": None, "sampleType": "", "status": None,
                            "startTime": "", "commitUser": ""}, "page": {"pageIndex": 1, "pageSize": 10}}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 数据集撤回
    def dataset_withdraw(self, datasetId):
        url = f"{env}/miai/brainstorm/datasetinfo/revocation/{datasetId}"
        payload = None

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 发起重标
    def dataset_relabel(self, datasetId):
        url = f"{env}/miai/brainstorm/datasetinfo/relabel/{datasetId}"
        payload = None

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 上传数据集
    def upload_dataset(self, name, sample_type, dataset_type, file_path):
        """
        上传数据集zip文件
        :param name: 数据集名称，如: api_158_ng
        :param sample_source: 样本来源，1=BASH样本
        :param dataset_id: 数据集ID
        :param sample_type: 样本类型，如: ng
        :param dataset_type: 数据集类型，0=训练集，1=测试集
        :param file_path: zip文件路径
        :return: response
        """
        url = f"{env}/miai/brainstorm/synthetic/upload/zip"

        # 构建multipart/form-data参数
        data = {
            "name": name,
            "sampleSource": 1,
            "datasetId": "",
            "sampleType": sample_type,
            "datasetType": dataset_type
        }

        # 打开文件并构建files参数
        with open(file_path, 'rb') as f:
            files = {
                "file": (os.path.basename(file_path), f, "application/zip")
            }
            response = self.client.post_with_retry(url, data=data, files=files)

        return response