"""
产品资料相关接口
"""
import time
from api import api_login
from common.Log import MyLog
from common.path_utils import get_testdata_path
from common.Request_Response import ApiClient

env = api_login.url
time_str = time.strftime("%Y%m%d%H%M%S", time.localtime())


class ApiProductInformation:
    def __init__(self, client: ApiClient):
        self.client = client

    # 上传PDF文件
    def upload_pdf(self) -> str:
        url = env + "/miai/brainstorm/knowledgeproductdata/uploadData"
        file_path = get_testdata_path("pdf文件上传.PDF")

        try:
            with open(file_path, 'rb') as file:
                files = {'file': file}
                response = self.client.post_with_retry(url, files=files)
                response_data = response.json()

                # 直接返回data_value
                return response_data['data']

        except Exception as e:
            MyLog.error(f"文件上传失败: {str(e)}")
            return ""

    # 新增产品资料
    def information_add(self, information_dataPath, information_name):
        url = f"{env}/miai/brainstorm/knowledgeproductdata/addData"
        payload = {
            "name": information_name,
            "detail": "接口自动化",
            "seatIsUse": 1,
            "dataPath": information_dataPath,
            "type": "PDF"
        }

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 查询产品资料
    def information_query(self, information_name):
        url = f"{env}/miai/brainstorm/knowledgeproductdata/queryPage"
        payload = {
            "data": {"name": information_name},
            "page": {"pageIndex": 1, "pageSize": 100}
        }

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 修改产品资料
    def information_update(self, productDataId, information_dataPath, update_name):
        url = f"{env}/miai/brainstorm/knowledgeproductdata/updateData"
        payload = {
            "productDataId": productDataId,
            "name": update_name,
            "type": "PDF",
            "seatIsUse": 0,
            "detail": f"接口_修改_{time_str}",
            "dataPath": information_dataPath,
            "grid_order": 1
        }

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 删除产品资料
    def information_delete(self, productDataId):
        url = f"{env}/miai/brainstorm/knowledgeproductdata/delete/{productDataId}"

        response = self.client.post_with_retry(url, json=None)
        return response


if __name__ == '__main__':
    pass
