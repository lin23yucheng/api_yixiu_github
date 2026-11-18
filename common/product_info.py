"""用于 API 封装的产品元数据懒加载辅助模块。"""

from api import api_login


env = api_login.url


def _get_client_headers(client):
    try:
        return getattr(client, "base_headers", {}) or {}
    except AttributeError:
        return {}


def resolve_product_info_id(client, space_manage_id=None, product_code=None):
    headers = _get_client_headers(client)
    resolved_space_manage_id = space_manage_id or headers.get("Miaispacemanageid") or api_login.manageid
    resolved_product_code = product_code or headers.get("Miai-Product-Code") or api_login.miai_product_code

    url = f"{env}/miai/brainstorm/productinfo/page"
    payload = {
        "data": {"spaceManageId": resolved_space_manage_id},
        "page": {"pageIndex": 1, "pageSize": 100},
    }
    request_headers = {
        "Miaispacemanageid": resolved_space_manage_id,
        "Miai-Product-Code": resolved_product_code,
    }

    response = client.post_with_retry(url, json=payload, headers=request_headers)
    response_data = response.json()
    if not response_data.get("success"):
        raise RuntimeError(f"产品查询失败: {response_data.get('msg')}")

    product_list = response_data.get("data", {}).get("list", [])
    for product in product_list:
        if product.get("productName") == resolved_product_code or product.get("productCode") == resolved_product_code:
            return product.get("productInfoId")

    raise LookupError(f"未找到产品: {resolved_product_code}")


class ProductInfoResolverMixin:
    @property
    def product_info_id(self):
        if getattr(self, "_product_info_id", None) is None:
            self._product_info_id = resolve_product_info_id(
                self.client,
                space_manage_id=getattr(self, "space_manage_id", None),
                product_code=getattr(self, "product_code", None),
            )
        return self._product_info_id
