"""
其他样本库相关接口
"""
import time
from api import api_login
from common.Request_Response import ApiClient
from common.product_info import ProductInfoResolverMixin

env = api_login.url
time_str = time.strftime("%Y%m%d%H%M%S", time.localtime())


class ApiOtherSample(ProductInfoResolverMixin):
    def __init__(self, client: ApiClient):
        self.client = client
        self._product_info_id = None

    # 查询标准样本库
    def query_standard_sample(self, startDateTime, endDateTime, bashSampleType):
        url = f"{env}/miai/brainstorm/sampleproductsyncmanage/sample/page"
        payload = {"data": {"date": [f"{startDateTime}T16:00:00.000Z", f"{endDateTime}T15:59:59.000Z"],
                            "sortingSampleType": "",
                            "bashSampleType": bashSampleType, "sampleSource": 2, "taskId": "", "channelId": "",
                            "deviceId": "", "photoId": "", "opticsSchemeId": "", "workpieceId": "", "cameraId": "",
                            "status": 1, "labelNames": [], "productInfoId": self.product_info_id, "definitions": [],
                            "checkTypes": [], "grades": [], "confusionTypes": [], "statusList": [], "isUse": None,
                            "startDateTime": f"{startDateTime}T16:00:00.000Z",
                            "endDateTime": f"{endDateTime}T15:59:59.000Z"},
                   "page": {"pageIndex": 1, "pageSize": 15}}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 查询限度样本库
    def query_limit_sample(self):
        url = f"{env}/miai/brainstorm/samplelimitdata/page"
        payload = {
            "data": {"discardTimeList": [], "labelName": "", "level": "", "photoId": "", "rule": "", "sampleSource": 2,
                     "sampleTimeList": [], "sort": "", "status": ""}, "page": {"pageIndex": 1, "pageSize": 10}}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 查询抽检样本库
    def query_sample_check_sample(self,startDateTime,endDateTime):
        url = f"{env}/miai/brainstorm/spotchecksample/page"
        payload = {"data": {"taskId": "", "deviceId": "", "workpieceId": "", "photoId": "", "modelSampleType": "",
                            "arithmeticSampleType": "", "bashSampleType": "", "finalSampleType": "",
                            "startTime": f"{startDateTime}T16:00:00.000Z", "endTime": f"{endDateTime}T15:59:59.000Z",
                            "isUse": None, "status": 1}, "page": {"pageIndex": 1, "pageSize": 15}}

        response = self.client.post_with_retry(url, json=payload)
        return response
