"""
模型库相关接口
"""

from api import api_login, api_space
from common.Request_Response import ApiClient

env = api_login.url


class ApiModelBase:
    def __init__(self, client: ApiClient):
        self.client = client
        self.product_info_id = api_space.ApiSpace().product_query()

    # 模型库查询
    def query_model_base(self):
        url = f"{env}/miai/brainstorm/newmodelmanage/modelManagePage"
        payload = {"data": {"showSelf": True}, "page": {"pageIndex": 1, "pageSize": 10}}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 部署测试
    def deploy_test(self, modelManageId):
        url = f"{env}/miai/brainstorm/newmodelmanage/test/{modelManageId}"

        response = self.client.post_with_retry(url, json=None)
        return response

    # 模型撤回1/删除2
    def model_withdraw(self, modelManageId, flag):
        url = f"{env}/miai/brainstorm/newmodelmanage/withdrawAndDelete"
        payload = {"flag": flag, "modelManageId": modelManageId}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 模型验证
    def model_verify(self, modelManageId, photo_id):
        url = f"{env}/miai/brainstorm/newmodelmanage/test/global/sample"
        payload = {"modelManageIdList": [modelManageId], "remark": "", "endTime": "", "startTime": "",
                   "photoId": photo_id, "sampleType": ["ok"], "productId": [self.product_info_id], "defectName": [],
                   "classifyType": [], "keepLabels": []}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 模型提交
    def model_submit(self, modelManageId):
        url = f"{env}/miai/brainstorm/combine/model/submit/{modelManageId}"
        payload = None

        response = self.client.post_with_retry(url, json=payload)
        return response
