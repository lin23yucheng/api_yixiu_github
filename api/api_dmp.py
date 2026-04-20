"""
DMP系统相关接口
"""
import os
import shutil
import zipfile
import requests
from common.Request_Response import ApiClient
from api import api_login

space_name = api_login.space_name
miaispacemanageid = api_login.manageid
manage_url = api_login.url


class ApiDmp:
    def __init__(self, client: ApiClient):
        self.client = client

    # 查询项目管理
    def query_project_manage(self):
        url = f"{manage_url}/pms/dmp/spacemanage/page"
        payload = {
            "data": {
                "spaceName": space_name,
                "spaceStatus": "",
                "spaceType": ""
            },
            "page": {
                "pageSize": 8,
                "pageIndex": 1
            }
        }
        return self.client.post_with_retry(url, json=payload)

    # 查询机器管理
    def query_machine_manage(self):
        url = f"{manage_url}/pms/dmp/machine/page"
        payload = {
            "data": {
                "deviceNo": "",
                "spaceId": miaispacemanageid
            },
            "page": {
                "pageIndex": 1,
                "pageSize": 100
            }
        }
        return self.client.post_with_retry(url, json=payload)

    # 获取可选机器列表
    def query_optional_machine_list(self):
        url = f"{manage_url}/pms/dmp/machine/page"
        payload = {
            "data": {
                "deviceNo": "",
                "status": 0,
                "spaceId": None
            },
            "page": {
                "pageIndex": 1,
                "pageSize": 9999
            }
        }
        return self.client.post_with_retry(url, json=payload)

    # 添加机器
    def add_machine(self, machine_id):
        url = f"{manage_url}/pms/dmp/machine/add"
        payload = {
            "machineId": machine_id,
            "spaceId": miaispacemanageid
        }
        return self.client.post_with_retry(url, json=payload)

    # 下载机台token并保存为accessToken.txt
    def machine_token_download(self, machine_id, save_dir=None):
        """
        通过DMP接口下载机台token并保存为accessToken.txt
        :param machine_id: 机台ID
        :param save_dir: 保存目录，默认项目根目录下testdata
        :return: token文件路径
        """
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if save_dir is None:
            save_dir = os.path.join(project_root, "testdata")

        os.makedirs(save_dir, exist_ok=True)
        prepare_url = f"{manage_url}/pms/dmp/machine/prepareDownload/{machine_id}"

        try:
            prepare_response = self.client.post_with_retry(prepare_url, json=None)
            prepare_data = prepare_response.json()
        except Exception as e:
            raise RuntimeError(f"获取下载地址失败，machine_id={machine_id}") from e

        if not prepare_data.get("success", False):
            raise RuntimeError(
                f"获取下载地址失败，machine_id={machine_id}，msg={prepare_data.get('msg', '未知错误')}"
            )

        download_url = prepare_data.get("data")
        if not download_url:
            raise RuntimeError(f"下载地址为空，machine_id={machine_id}")

        zip_path = os.path.join(save_dir, f"machine_{machine_id}_token.zip")
        extract_dir = os.path.join(save_dir, f"machine_{machine_id}_extracted")

        try:
            # 下载链接通常是临时签名地址，直接请求即可
            download_response = requests.get(download_url, stream=True, timeout=30)
            download_response.raise_for_status()
            with open(zip_path, "wb") as f:
                for chunk in download_response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            if not zipfile.is_zipfile(zip_path):
                raise RuntimeError(f"下载文件不是有效ZIP，machine_id={machine_id}")

            os.makedirs(extract_dir, exist_ok=True)
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(extract_dir)

            token_file = None
            for root, _, files in os.walk(extract_dir):
                if "accessToken.txt" in files:
                    token_file = os.path.join(root, "accessToken.txt")
                    break

            if not token_file:
                raise RuntimeError(f"ZIP中未找到accessToken.txt，machine_id={machine_id}")

            target_path = os.path.join(save_dir, "accessToken.txt")
            if os.path.exists(target_path):
                os.remove(target_path)
            shutil.move(token_file, target_path)
            return target_path
        finally:
            if os.path.isdir(extract_dir):
                shutil.rmtree(extract_dir, ignore_errors=True)
            if os.path.isfile(zip_path):
                os.remove(zip_path)

