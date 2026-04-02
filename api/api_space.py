"""
空间的相关接口
"""
import os
import zipfile
import shutil
import requests
from api import api_login
from api.api_login import ApiLogin

env = api_login.url
product_code = api_login.miai_product_code
manageid = api_login.miaispacemanageid
space_name = api_login.space_name
login = ApiLogin()
token = login.login()


# 代码推送
# git push gitlab main
# git push origin main
# git push github main

class ApiSpace:
    # 项目空间查询
    def space_query(self, spaceName):
        url = env + "/miai/brainstorm/spacemanage/page"
        data = {"data": {"spaceName": spaceName, "showUnsettle": False}, "page": {"pageIndex": 1, "pageSize": 100}}
        header = {"content-type": "application/json", "Authorization": token}

        rep_product_query = requests.post(url=url, json=data, headers=header)
        rep_json = rep_product_query.json()

        if rep_json.get("success"):
            space_list = rep_json["data"]["list"]

            # 如果列表不为空，返回第一条数据的spaceManageId
            if space_list:
                first_space = space_list[0]
                return first_space["spaceManageId"]
            else:
                print("空间列表为空")
                return None
        else:
            print("请求失败：", rep_json.get("msg"))
            return None

    # 产品查询
    def product_query(self):
        url = env + "/miai/brainstorm/productinfo/page"
        data = {"data": {"spaceManageId": manageid}, "page": {"pageIndex": 1, "pageSize": 100}}
        header = {"content-type": "application/json", "Authorization": token, "Miaispacemanageid": manageid}

        rep_product_query = requests.post(url=url, json=data, headers=header)
        rep_json = rep_product_query.json()
        # print(rep_product_query.text)
        if rep_json.get("success"):
            product_list = rep_json["data"]["list"]
            # 遍历查找目标产品
            for product in product_list:
                if product["productName"] == product_code:
                    return product["productInfoId"]
            return None  # 未找到返回None
        else:
            print("请求失败：", rep_json.get("msg"))
            return None

    # 机台查询
    def machine_query(self):
        url = env + "/miai/brainstorm/clouddevice/page"
        data = {"data": {"deviceNo": "", "spaceManageId": manageid}, "page": {"pageIndex": 1, "pageSize": 100}}
        header = {"content-type": "application/json", "Authorization": token}

        rep = requests.post(url=url, json=data, headers=header)
        return rep

    # 添加机器
    def machine_add(self):
        url = env + "/miai/brainstorm/clouddevice/add"
        data = {"localDeviceNo": product_code, "spaceManageId": manageid, "useStatus": 1}
        header = {"content-type": "application/json", "Authorization": token}

        rep = requests.post(url=url, json=data, headers=header)
        return rep

    # 机台token下载
    def machine_token_download(self, device_id, save_dir=None):
        """
        下载机台token并解压到指定目录
        :param device_id: 设备ID
        :param save_dir: 保存目录，默认为项目根目录下的testdata
        :return: 解压后的token文件路径
        """
        # 获取项目根目录的路径
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        # 如果未指定保存目录，使用项目根目录下的testdata
        if save_dir is None:
            save_dir = os.path.join(project_root, "testdata")

        print(f"文件将保存到: {save_dir}")

        # 步骤1: 获取预下载URL
        prepare_url = f"{env}/miai/brainstorm/clouddevice/prepareDownload/{device_id}"
        prepare_header = {"content-type": "application/json", "Authorization": token}

        try:
            # 请求预下载接口
            prepare_response = requests.post(prepare_url, headers=prepare_header)
            prepare_response.raise_for_status()
            prepare_data = prepare_response.json()

            # 检查请求是否成功
            if not prepare_data.get("success", False):
                error_msg = prepare_data.get('msg', '未知错误')
                print(f"获取下载URL失败: {error_msg}")
                return None

            # 获取实际下载URL
            download_url = prepare_data.get("data")
            if not download_url:
                print("获取的下载URL为空")
                return None

            print(f"获取到下载URL: {download_url}")

        except requests.exceptions.RequestException as e:
            print(f"请求预下载URL失败: {e}")
            return None

        # 步骤2: 下载实际文件
        # 注意：这个URL可能是不同域名的，所以不需要添加env前缀
        # 确保保存目录存在
        os.makedirs(save_dir, exist_ok=True)
        zip_path = os.path.join(save_dir, f"device_{device_id}_token.zip")

        try:
            # 下载实际文件
            # 注意：这里不需要添加额外的header
            response = requests.get(download_url, stream=True)
            response.raise_for_status()

            # 保存文件
            with open(zip_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            print(f"文件下载成功: {zip_path}")

        except requests.exceptions.RequestException as e:
            print(f"下载ZIP文件失败: {e}")
            return None

        # 后续解压和查找token文件的逻辑保持不变...
        # 验证是否为ZIP文件
        if not zipfile.is_zipfile(zip_path):
            # 尝试读取文件内容查看错误信息
            try:
                with open(zip_path, 'r', encoding='utf-8') as f:
                    content = f.read(200)  # 读取前200个字符
                    print(f"文件内容: {content}")
            except:
                print("下载的文件不是有效的ZIP格式且无法读取内容")
            os.remove(zip_path)
            return None

        # 解压ZIP文件
        extract_dir = os.path.join(save_dir, f"device_{device_id}_extracted")
        os.makedirs(extract_dir, exist_ok=True)

        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            print(f"文件解压到: {extract_dir}")
        except zipfile.BadZipFile as e:
            print(f"解压失败: {e}")
            return None
        except Exception as e:
            print(f"解压过程中发生错误: {e}")
            return None

        # 查找accessToken.txt文件
        token_file = None
        for root, dirs, files in os.walk(extract_dir):
            if "accessToken.txt" in files:
                token_file = os.path.join(root, "accessToken.txt")
                break

        if not token_file:
            print("在下载文件中未找到accessToken.txt")
            # 列出解压后的文件帮助调试
            print("解压后的文件列表:")
            for root, dirs, files in os.walk(extract_dir):
                for file in files:
                    print(os.path.join(root, file))
            return None

        # 将token文件移动到目标目录
        target_path = os.path.join(save_dir, "accessToken.txt")
        shutil.move(token_file, target_path)

        # 清理临时文件
        shutil.rmtree(extract_dir)
        os.remove(zip_path)

        print(f"Token文件已保存到: {target_path}")
        return target_path

    # 新增镜像
    def add_image(self, imageType, imagePath):
        url = f"{env}/miai/brainstorm/modelimage/create"
        data = {"imageType": imageType, "imagePath": imagePath}
        header = {"content-type": "application/json", "Authorization": token}

        rep = requests.post(url=url, json=data, headers=header)
        return rep

    # 光源类型新增
    def add_light_source_type(self):
        url = f"{env}/miai/brainstorm/opticalsourcetype/add"
        data = {"opticalSourceTypeName": "接口自动化-光源类型", "opticalSourceTypeId": "111",
                "opticalSourceTypeRemark": "111"}
        header = {"content-type": "application/json", "Authorization": token}

        rep = requests.post(url=url, json=data, headers=header)
        return rep

    # 光源配方新增
    def add_light_source_formula(self):
        url = f"{env}/miai/brainstorm/opticalformula/add"
        data = {"formulaName": "接口自动化-光源配方", "opticalFormulaId": "222", "formulaRemark": "222",
                "opticalSourceTypeList": [{"opticalSourceTypeId": "111"}]}
        header = {"content-type": "application/json", "Authorization": token}

        rep = requests.post(url=url, json=data, headers=header)
        return rep

    # 光学方案新增
    def add_optical_scheme(self):
        url = f"{env}/miai/brainstorm/opticalscheme/add"
        data = {"schemeName": "接口自动化-光学方案", "opticalSchemeId": "333", "opticalFormulaId": "222",
                "recommendExposure": "", "recommendGain": "", "recommendGamma": "", "opticalSourceBrightness": "",
                "remark": ""}
        header = {"content-type": "application/json", "Authorization": token}

        rep = requests.post(url=url, json=data, headers=header)
        return rep

    # 光学方案查询
    def optical_scheme_query(self):
        url = f"{env}/miai/brainstorm/opticalscheme/all"
        header = {"content-type": "application/json", "Authorization": token}

        rep = requests.post(url=url, json=None, headers=header)
        return rep

    # 标签库新增
    def add_tag_library(self, labelCnName, labelName, dictionaryOptionId):
        url = f"{env}/miai/brainstorm/labelDefinition/add"
        data = {"labelType": 0, "labelCnName": labelCnName, "labelName": labelName, "labelRemarks": "",
                "labelSimilarName": "", "defectType": 1, "labelEnName": "", "sampleImages": "",
                "labelDictOptionList": [{"dictionaryId": 5, "dictionaryOptionId": dictionaryOptionId}],
                "dictionaryId5": [dictionaryOptionId], "labelDefinitionId": None}

        header = {"content-type": "application/json", "Authorization": token}

        rep = requests.post(url=url, json=data, headers=header)
        return rep

    # 标签库查询
    def tag_library_query(self,label_name):
        url = f"{env}/miai/brainstorm/labelDefinition/page"
        data = {
            "data": {"searchText": label_name, "materialGroupId": "", "productMaterialId": "", "productionProcessId": "",
                     "surfaceTreatmentId": "", "labelType": 0}, "page": {"pageIndex": 1, "pageSize": 10}}

        header = {"content-type": "application/json", "Authorization": token}

        rep = requests.post(url=url, json=data, headers=header)
        return rep

    # 标签库发布
    def tag_library_publish(self, labelDefinitionId):
        url = f"{env}/miai/brainstorm/labelDefinition/publish/{labelDefinitionId}"
        header = {"content-type": "application/json", "Authorization": token}

        rep = requests.post(url=url, json=None, headers=header)
        return rep

if __name__ == '__main__':
    api = ApiSpace()
    # space_name = api.space_query()
    # product_info_id = api.product_query()
    test01 = api.machine_query()
    # test02 = api.machine_add()
    token_path = api.machine_token_download(1876176907833774082)
    if token_path:
        print(f"成功获取token文件: {token_path}")
        # 读取token内容
        with open(token_path, 'r') as f:
            token_content = f.read()
            print(f"设备Token: {token_content}")
    # print("空间ID：", space_name)
    # print("产品ID：", product_info_id)
