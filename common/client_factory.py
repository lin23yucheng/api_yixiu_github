"""HTTP 客户端工厂辅助工具。

懒加载客户端使模块导入无副作用：仅在测试或 API 封装层实际发送请求时才进行认证。
"""

from api import api_login
from common.Request_Response import ApiClient


def create_yixiu_headers(space_manage_id=None, product_code=None):
    return {
        "Authorization": api_login.ApiLogin().login(),
        "Miai-Product-Code": product_code or api_login.code,
        "Miaispacemanageid": space_manage_id or api_login.manageid,
    }


def create_yixiu_client(space_manage_id=None, product_code=None):
    return ApiClient(base_headers=create_yixiu_headers(space_manage_id=space_manage_id, product_code=product_code))


class LazyApiClient:
    def __init__(self, factory):
        self._factory = factory
        self._client = None

    def get_client(self):
        if self._client is None:
            self._client = self._factory()
        return self._client

    def __getattr__(self, name):
        return getattr(self.get_client(), name)


def create_lazy_yixiu_client(space_manage_id=None, product_code=None):
    def factory():
        return create_yixiu_client(space_manage_id=space_manage_id, product_code=product_code)

    return LazyApiClient(factory)
