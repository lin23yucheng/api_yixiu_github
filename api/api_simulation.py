"""
仿真测试相关接口
"""
from api import api_login
from common.Request_Response import ApiClient

env = api_login.url


class ApiSimulation:
    def __init__(self, client: ApiClient):
        self.client = client
        self.miai_product_code = api_login.miai_product_code

    # 查询测试图集
    def query_test_atlas(self):
        url = f"{env}/miai/brainstorm/datalg/dataalgorithmtestdataset/page"
        payload = {"data": {"onlySelf": True, "productInfoId": ""}, "page": {"pageIndex": 1, "pageSize": 10}}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 创建测试图集
    def create_test_atlas(self, test_atlas_name):
        url = f"{env}/miai/brainstorm/datalg/dataalgorithmtestdataset/create"
        payload = {"name": test_atlas_name, "productCode": self.miai_product_code, "searchPhotoId": "", "imgNum": 50,
                   "workpieceSetNum": 10,
                   "remark": "", "startTime": "", "endTime": "", "workpieceSetTargetOkRate": 50, "labelRatioList": [],
                   "photoIdList": [1]}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 查询仿真测试任务
    def query_test_task(self, test_atlas_id):
        url = f"{env}/miai/brainstorm/datalg/dataalgorithmtest/page"
        payload = {"data": {"onlySelf": True, "dataAlgorithmTestDatasetId": test_atlas_id},
                   "page": {"pageIndex": 1, "pageSize": 10}}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 创建仿真测试任务
    def create_test_task(self, test_atlas_id):
        url = f"{env}/miai/brainstorm/datalg/dataalgorithmtest/create"
        payload = {"modelManageId": "1000000000000000005",
                   "modelInfo": {"modelManageId": "1000000000000000005", "deepModelName": "仿真5个分割模型组合",
                                 "deepModelVersion": 23,
                                 "combineType": "DetS V2 实例分割+DetS V2 实例分割+DetS V2 实例分割+DetS V2 实例分割+DetS V2 实例分割",
                                 "isCombine": True,
                                 "tritonPath": "/miai_mtl_repository/1000000000000000003/triton/1000000000000000005",
                                 "deepModelSource": "4", "isAllinPhoto": False,
                                 "classNamesList": "[\"shang\", \"fabaimian\", \"neilie\", \"mozha\", \"fabai\", \"tuomo\", \"yimo\", \"liangxian\", \"moqian3\", \"moqian\", \"liebian\", \"dahen\", \"pobian\", \"seban\", \"shanghen\"]",
                                 "checkScope": "DEMO001:1,2,3,4,5,8,10",
                                 "inferenceLabel": "伤,发白面,内裂,磨渣,发白,脱模,溢墨,亮线,墨欠3,墨欠,裂边,打痕,破边,色斑,伤痕"},
                   "dataAlgorithmModelId": "1000000000000000007", "cpu": "10", "gpu": "4090-24GB-1",
                   "deepModelName": "仿真5个分割模型组合", "deepModelVersion": 23,
                   "combineType": "DetS V2 实例分割+DetS V2 实例分割+DetS V2 实例分割+DetS V2 实例分割+DetS V2 实例分割",
                   "isCombine": True,
                   "tritonPath": "/miai_mtl_repository/1000000000000000003/triton/1000000000000000005",
                   "deepModelSource": "4", "isAllinPhoto": False,
                   "classNamesList": "[\"shang\", \"fabaimian\", \"neilie\", \"mozha\", \"fabai\", \"tuomo\", \"yimo\", \"liangxian\", \"moqian3\", \"moqian\", \"liebian\", \"dahen\", \"pobian\", \"seban\", \"shanghen\"]",
                   "checkScope": "DEMO001:1,2,3,4,5,8,10",
                   "inferenceLabel": "伤,发白面,内裂,磨渣,发白,脱模,溢墨,亮线,墨欠3,墨欠,裂边,打痕,破边,色斑,伤痕",
                   "deepModelPath": "/miai_mtl_repository/1000000000000000003/triton/1000000000000000005",
                   "dataAlgorithmTestDatasetId": test_atlas_id
                   }

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 查看数据算法评估报告（模型综合评估）
    def query_test_report(self, test_task_id):
        url = f"{env}/miai/brainstorm/datalg/dataalgorithmtestreport/dataModel/compReport/{test_task_id}"
        payload = None

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 查看数据算法评估报告（缺陷图模型检出评估（缺陷级））
    def query_test_detailReport(self, test_task_id):
        url = f"{env}/miai/brainstorm/datalg/dataalgorithmtestreport/dataModel/detailReport"
        payload = {"data": {"dataAlgorithmTestId": test_task_id, "dimensionList": ["optical_side_id"],
                            "filter": {"labelNameList": [], "opticalSideAreaList": None}},
                   "page": {"pageSize": 10, "pageIndex": 1, "total": 0}}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 删除仿真测试任务
    def delete_test_task(self, test_task_id):
        url = f"{env}/miai/brainstorm/datalg/dataalgorithmtest/delete/{test_task_id}"
        payload = None

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 删除测试图集
    def delete_test_atlas(self, test_atlas_id):
        url = f"{env}/miai/brainstorm/datalg/dataalgorithmtestdataset/delete/{test_atlas_id}"
        payload = None

        response = self.client.post_with_retry(url, json=payload)
        return response
