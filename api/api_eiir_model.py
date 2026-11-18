"""
EIIR模型库相关接口
"""

from api import api_login
from common.Request_Response import ApiClient

env = api_login.url


class ApiEiirModel:
    def __init__(self, client: ApiClient):
        self.client = client

    # 查询目标检测模型库
    def query_eiir_model(self):
        url = f"{env}/miai/brainstorm/eiir/modelmanage/page"
        payload = {"data": {"showSelf": True, "status": None, "startTime": "", "endTime": ""},
                   "page": {"pageIndex": 1, "pageSize": 10}}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # EIIR模型撤回
    def rollback_eiir_model(self, modelManageId):
        url = f"{env}/miai/brainstorm/eiir/modelmanage/rollback"
        payload = {"modelManageId": modelManageId}

        response = self.client.post_with_retry(url, json=payload)
        return response
