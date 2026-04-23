"""
数据训练任务相关接口
"""
import os
import time
import requests
from api import api_login, api_space
from common.path_utils import get_testdata_path
from common.Request_Response import ApiClient

env = api_login.url
time_str = time.strftime("%Y%m%d%H%M%S", time.localtime())


class ApiDataTrainTasks:
    def __init__(self, client: ApiClient):
        self.client = client
        self.product_info_id = api_space.ApiSpace().product_query()

    # 查询数据训练任务
    def query_data_tasks(self):
        url = f"{env}/miai/brainstorm/datalg/dataalgorithmtraintask/page"
        payload = {"data": {"onlySelf": True}, "page": {"pageIndex": 1, "pageSize": 10}}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 拷贝数据训练任务
    def copy_data_tasks(self, modelManageId, deepModelName, deepModelVersion, tritonPath, TrainTaskId):
        url = f"{env}/miai/brainstorm/datalg/dataalgorithmtraintask/copy"
        payload = {"taskName": f"接口自动化-数据-{time_str}", "modelManageId": modelManageId,
                   "deepModelName": deepModelName, "deepModelVersion": deepModelVersion, "combineType": None,
                   "isCombine": False,
                   "tritonPath": tritonPath,
                   "deepModelSource": "2", "isAllinPhoto": True, "checkScope": "ALL",
                   "displayName": f"{deepModelName} V{deepModelVersion} ",
                   "dataAlgorithmTrainTaskId": TrainTaskId}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 删除数据训练任务
    def delete_data_tasks(self, data_task_id):
        url = f"{env}/miai/brainstorm/datalg/dataalgorithmtraintask/delete/{data_task_id}"

        response = self.client.post_with_retry(url, json=None)
        return response

    # 生成下载数据包
    def create_data_zip(self, data_task_id):
        url = f"{env}/miai/brainstorm/datalg/dataAlgorithmCollect/createCollectTask/{data_task_id}"

        response = self.client.post_with_retry(url, json=None)
        return response

    # 上传数据算法
    def upload_data_algorithm(self, data_task_id):
        url = f"{env}/miai/brainstorm/datalg/dataalgorithmmodel/uploadDataAlgorithm"
        model_file_path = get_testdata_path("数据模型.zip")

        # 验证文件
        if not os.path.exists(model_file_path):
            raise FileNotFoundError(f"模型文件不存在: {model_file_path}")
        if not model_file_path.lower().endswith('.zip'):
            raise ValueError("模型文件必须是zip格式")

        # 使用requests的标准files参数上传
        with open(model_file_path, 'rb') as model_file:
            # 准备表单数据
            data = {
                'remark': f"接口自动化_{time_str}",
                'dataAlgorithmTrainTaskId': str(data_task_id)
            }

            # 文件字段必须命名为'modelFile'
            files = {
                'modelFile': ('数据模型.zip', model_file, 'application/zip')
            }

            # 准备请求头（移除Content-Type）
            headers = self.client.base_headers.copy()
            if 'Content-Type' in headers:
                del headers['Content-Type']

            # 发送请求
            response = requests.post(
                url,
                headers=headers,
                data=data,  # 普通表单字段
                files=files  # 文件字段
            )

            # 添加详细的错误处理
            try:
                 
                return response
            except requests.exceptions.HTTPError as e:
                # 解析可能的错误信息
                error_info = f"状态码: {response.status_code}\n"
                try:
                    error_info += f"响应内容: {response.json()}"
                except:
                    error_info += f"响应文本: {response.text}"

                raise requests.exceptions.HTTPError(
                    f"上传失败: {e}\n{error_info}"
                ) from e

    # 查询上传记录
    def query_upload_record(self, data_task_id):
        url = f"{env}/miai/brainstorm/datalg/dataalgorithmmodel/page"
        payload = {"data": {"dataAlgorithmTrainTaskId": data_task_id}, "page": {"pageIndex": 1, "pageSize": 10}}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 查询下载记录
    def query_download_record(self, data_task_id):
        url = f"{env}/miai/brainstorm/datalg/dataAlgorithmCollect/page"
        payload = {"data": {"dataAlgorithmTrainTaskId": data_task_id}, "page": {"pageIndex": 1, "pageSize": 10}}

        response = self.client.post_with_retry(url, json=payload)
        return response
