"""
产品样例相关接口
"""
import time
from api import api_login
from common.path_utils import get_testdata_path
from common.Request_Response import ApiClient

env = api_login.url
time_str = time.strftime("%Y%m%d%H%M%S", time.localtime())


class ApiProductSamples:
    def __init__(self, client: ApiClient):
        self.client = client

    # 上传图片
    def upload_pictures(self):
        url = env + "/miai/brainstorm/knowledgeproductsample/upload"
        file_path = get_testdata_path("上传图片.jpg")

        with open(file_path, 'rb') as file:
            # 构造文件上传参数，键名需与接口期望的键一致
            files = {'file': file}
            response = self.client.post_with_retry(url, files=files)

        print(f"响应内容: {response.text}")

        assert response.status_code == 200, f"接口返回状态码异常，期望 200，实际 {response.status_code}"

        # 验证响应并提取 data
        response_data = response.json()

        # 直接提取 data（断言通过后执行）
        data_value = response_data['data']
        print(f"提取的文件路径: {data_value}")

        return data_value

    # 新增产品样例
    def samples_add(self, data_value,name):
        url = f"{env}/miai/brainstorm/knowledgeproductsample/add"
        payload = {"name": name, "detail": f"接口自动化-{time_str}", "sampleType": 2, "file": [],
                   "imgPath": data_value,
                   "photoId": 9, "type": 2}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 查询产品样例
    def samples_query(self):
        url = f"{env}/miai/brainstorm/knowledgeproductsample/page"
        payload = {"data": {"name": "", "type": 2}, "page": {"pageIndex": 1, "pageSize": 10}}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 修改产品样例
    def samples_update(self, productCode, Miaispacemanageid, productSampleId, data_value,update_name):
        url = f"{env}/miai/brainstorm/knowledgeproductsample/update/{productSampleId}"
        payload = {
            "productSampleId": productSampleId, "spaceManageId": Miaispacemanageid,
            "productCode": productCode, "name": update_name, "sampleType": 1,
            "detail": f"接口自动化update_{time_str}",
            "imgPath": data_value,
            "photoId": 8,
            "type": 2, "version": 0, "jsonInfo": None, "frameNum": None, "grid_order": 1, "file": [{}]}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 删除产品样例
    def samples_delete(self, productSampleId):
        url = f"{env}/miai/brainstorm/knowledgeproductsample/delete/{productSampleId}"

        response = self.client.post_with_retry(url, json=None)
        return response


if __name__ == '__main__':
    pass
