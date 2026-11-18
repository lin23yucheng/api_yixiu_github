"""
EIIR空间标注相关接口
"""
import time
from api import api_login
from common.Request_Response import ApiClient

env = api_login.url
time_str = time.strftime("%Y%m%d%H%M%S", time.localtime())


class ApiEiirLabel:
    def __init__(self, client: ApiClient):
        self.client = client

    # 查询标注任务
    def query_label_task(self):
        url = f"{env}/miai/brainstorm/eiir/dimensiontask/self/page"
        payload = {"data": {"taskStatus": "", "labelUser": "", "startTime": None, "endTime": None, "taskName": ""},
                   "page": {"pageIndex": 1, "pageSize": 10}}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 标注状态待开始-进行中
    def update_label_task_status(self, task_id):
        url = f"{env}/miai/brainstorm/eiir/dimensiontask/start/{task_id}"

        response = self.client.post_with_retry(url, json=None)
        return response

    # 获取标注样本的dataId
    def query_label_data_id(self, task_id):
        url = f"{env}/miai/brainstorm/eiir/dimensiontask/image/list"
        payload = {"dimensionTaskId": task_id, "labeled": False}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 获取标注标签
    def get_label(self, miaispacemanageid):
        url = f"{env}/miai/brainstorm/eiir/ComponentRmi/forLabel/{miaispacemanageid}"

        response = self.client.post_with_retry(url, json=None)
        return response

    # 保存标注
    def save_label(self, dataId, label):
        url = f"{env}/miai/brainstorm/eiir/dimensiontask/saveLabelJson"
        payload = {"dataId": dataId, "shapes": [{"label": label, "points": [[584, 300], [703, 426]]}],
                   "width": 1280, "height": 720}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 完成标注任务
    def complete_label_task(self, task_id):
        url = f"{env}/miai/brainstorm/eiir/dimensiontask/finish/{task_id}"

        response = self.client.post_with_retry(url, json=None)
        return response

    # 撤回标注任务
    def revoke_label_task(self, task_id):
        url = f"{env}/miai/brainstorm/eiir/dimensiontask/withdraw/{task_id}"

        response = self.client.post_with_retry(url, json=None)
        return response

    # 关闭标注任务
    def close_label_task(self, task_id):
        url = f"{env}/miai/brainstorm/eiir/dimensiontask/close/{task_id}"

        response = self.client.post_with_retry(url, json=None)
        return response
