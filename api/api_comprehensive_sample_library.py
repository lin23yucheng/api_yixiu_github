"""
综合样本库相关接口
"""
from api import api_login, api_space
from common.Request_Response import ApiClient

env = api_login.url

# 初始化全局客户端
base_headers = {
    "Authorization": api_login.ApiLogin().login(),
    "Miai-Product-Code": api_login.code,
    "Miaispacemanageid": api_login.manageid
}
global_client = ApiClient(base_headers=base_headers)


class ApiComprehensiveSampleLibrary:
    def __init__(self, client: ApiClient):
        self.client = client
        self.product_info_id = api_space.ApiSpace().product_query()

    # 综合样本库查询
    def comprehensive_sample_query(self, imgName, defectName, photoId):
        url = f"{env}/miai/brainstorm/es/global/sample/page"

        payload = {
            "data": {"endTime": None, "startTime": None, "imgName": imgName, "visualGrade": [], "bashSampleType": [],
                     "productId": [self.product_info_id], "defectName": defectName, "photoId": photoId,
                     "classifyType": [],
                     "imageDefinition": [],
                     "sampleType": [], "dataAlgorithmSampleType": [], "deepModelSampleType": []},
            "page": {"pageIndex": 1, "pageSize": 10}}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 综合样本库-创建目标检测/分类切图训练任务（globalDatasetType：0为训练集）
    def create_deep_training_tasks(self, defectName, photoId, cut, taskName, classifyType, caseId, caseName,
                                   create_type,
                                   iscut, remark):
        url = f"{env}/miai/brainstorm/global/sample/createTrainTask"
        payload = {"endTime": None, "startTime": None, "imgName": "", "globalDatasetType": 0, "visualGrade": [],
                   "bashSampleType": [],
                   "productId": [self.product_info_id], "defectName": defectName, "photoId": photoId,
                   "classifyType": classifyType,
                   "imageDefinition": [], "sampleType": [], "dataAlgorithmSampleType": [], "deepModelSampleType": [],
                   "selectIds": [], "notSelectIds": [], "taskName": taskName, "testSetMinValue": 0,
                   "testSetProportion": 30,
                   "caseId": caseId, "caseName": caseName, "cut": iscut, "filter": False, "remark": remark,
                   "defectCount": "[{\"labelName\":\"\",\"count\":\"\"}]", "cutHeight": cut, "cutWidth": cut,
                   "type": create_type}

        response = self.client.post_with_retry(url, json=payload)
        print(response.json())
        return response

    # 综合样本库-创建分类大图训练任务（globalDatasetType：0为训练集）
    def create_class_training_tasks(self, defectName, photoId, cut, taskName, classifyType, caseId, caseName,
                                    create_type, iscut, remark):
        # 读取配置文件获取classify_type
        import configparser
        import json
        import os

        config = configparser.ConfigParser()
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'env_config.ini')
        config.read(config_path, encoding='utf-8')

        classify_types = eval(config.get('class_ids', 'classify_type'))

        # 验证列表长度，如果不足则报错
        if len(classify_types) < 2:
            raise ValueError("配置文件[class_ids]下的classify_type列表至少需要包含两个元素")

        # 构造映射字典（每个标签映射到自己）
        type_mapping_dict = {t: t for t in classify_types}
        type_mapping = json.dumps(type_mapping_dict)

        url = f"{env}/miai/brainstorm/global/sample/createTrainTask"
        payload = {"endTime": None, "startTime": None, "imgName": "", "globalDatasetType": 0, "visualGrade": [],
                   "bashSampleType": [], "productId": [self.product_info_id], "defectName": defectName,
                   "photoId": photoId,
                   "classifyType": classifyType, "imageDefinition": [], "sampleType": [],
                   "dataAlgorithmSampleType": [], "deepModelSampleType": [], "selectIds": [], "notSelectIds": [],
                   "taskName": taskName, "testSetMinValue": 0, "testSetProportion": 30, "caseId": caseId,
                   "caseName": caseName, "cut": iscut, "remark": remark,
                   "defectCount": "[{\"labelName\":\"\",\"count\":\"\"}]", "cutHeight": cut, "cutWidth": cut,
                   "typeMapping": type_mapping, "type": create_type}

        response = self.client.post_with_retry(url, json=payload)
        print(response.json())
        return response

    # 综合样本库-追加到深度训练任务(目标检测-按比例划分)
    def append_deep_training_tasks1(self, defectName, photoId, trainId):
        url = f"{env}/miai/brainstorm/global/sample/addition"

        payload = {"endTime": None, "startTime": None, "imgName": "", "globalDatasetType": 0, "visualGrade": [],
                   "bashSampleType": [],
                   "productId": [self.product_info_id], "defectName": defectName, "photoId": photoId,
                   "classifyType": [],
                   "imageDefinition": [], "sampleType": [], "dataAlgorithmSampleType": [], "deepModelSampleType": [],
                   "selectIds": [], "notSelectIds": [], "testSetMinValue": 0, "testSetProportion": 40,
                   "trainId": trainId, "datasetType": 3, "filter": False, "defectCount": "[]"}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 综合样本库-追加到深度训练任务(目标检测-划分训练集1/验证集2)
    def append_deep_training_tasks2(self, photoId, sampleType, trainId, datasetType):
        url = f"{env}/miai/brainstorm/global/sample/addition"

        payload = {"imgName": "", "endTime": None, "startTime": None, "globalDatasetType": 0, "visualGrade": [],
                   "bashSampleType": [],
                   "productId": [self.product_info_id], "defectName": None, "photoId": photoId,
                   "classifyType": [],
                   "sampleType": [sampleType], "imageDefinition": [], "dataAlgorithmSampleType": [],
                   "deepModelSampleType": [],
                   "selectIds": [], "notSelectIds": [], "trainId": trainId, "datasetType": datasetType,
                   "filter": False, "defectCount": "[]"}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 综合样本库-创建数据训练任务
    def create_data_training_tasks(self, defectName, taskName):
        url = f"{env}/miai/brainstorm/datalg/dataalgorithmtraintask/create"
        payload = {"imgName": "", "endTime": None, "startTime": None, "globalDatasetType": 0, "visualGrade": [],
                   "bashSampleType": [],
                   "productId": [self.product_info_id], "defectName": defectName, "photoId": [],
                   "classifyType": [], "imageDefinition": [], "sampleType": [], "dataAlgorithmSampleType": [],
                   "deepModelSampleType": [], "classifyTypeOther": [None, "mozha", "未知", "yakedian"],
                   "defectNameOther": ["mozha", "yakedian"], "selectIds": [], "notSelectIds": [],
                   "taskName": taskName, "deepModel": "1878990922328797185", "remark": "接口自动化",
                   "modelManageId": "1878990922328797185", "deepModelName": "仿真5个分割模型组合",
                   "deepModelVersion": 23,
                   "combineType": "DetS V2 实例分割+DetS V2 实例分割+DetS V2 实例分割+DetS V2 实例分割+DetS V2 实例分割",
                   "isCombine": True,
                   "tritonPath": "/miai_mtl_repository/1873905652887785473/triton/1878990922328797185",
                   "deepModelSource": "4", "isAllinPhoto": False,
                   "classNamesList": "[\"shang\", \"fabaimian\", \"neilie\", \"mozha\", \"fabai\", \"tuomo\", \"yimo\", \"liangxian\", \"moqian3\", \"moqian\", \"liebian\", \"dahen\", \"pobian\", \"seban\", \"shanghen\"]",
                   "checkScope": "JHOCT001:1,2,3,4,5,8,10",
                   "inferenceLabel": "伤,发白面,内裂,磨渣,发白,脱模,溢墨,亮线,墨欠3,墨欠,裂边,打痕,破边,色斑,伤痕",
                   "displayName": "仿真5个分割模型组合 V23 组合"}

        response = self.client.post_with_retry(url, json=payload)
        return response


if __name__ == '__main__':
    api = ApiComprehensiveSampleLibrary(global_client)
    # api.comprehensive_sample_query(None, ["shang"], ["1", "2", "3"])
    api.create_deep_training_tasks(["dahenxian"], [], 1024, "测试集01", [], "detection", "目标检测/分割", 1, True, "")
    # api.append_deep_training_tasks(["yimo"], ["1", "2"], None)
    # api.append_deep_training_tasks2(None, ["3"], ["ok"], None, 1)
