"""
产品标签相关接口
"""
from api import api_login, api_space
from common.Request_Response import ApiClient

env = api_login.url
product_code = api_login.miai_product_code
manageid = api_login.miaispacemanageid
space_name = api_login.space_name


class ApiProductLabel:
    def __init__(self, client: ApiClient):
        self.client = client
        self.product_info_id = api_space.ApiSpace().product_query()
        self.api_space = api_space.ApiSpace()

    # 查询产品标签
    def query_product_label(self):
        url = f"{env}/miai/brainstorm/labelinfo/page"
        payload = {"data": {"productCode": ""}, "page": {"pageIndex": 1, "pageSize": 100}}

        response = self.client.post_with_retry(url, json=payload)
        return response

    # 添加产品标签
    def add_product_label(self):
        # 先处理"毛刺"标签
        # 先检查标签库中是否存在"毛刺"标签
        tag_response = self.api_space.tag_library_query("maoci")
        tag_response_data = tag_response.json()

        # 检查是否存在labelCnName等于"毛刺"且labelName等于"maoci"的数据
        target_label_data = None
        if tag_response_data.get('success') and 'data' in tag_response_data and 'list' in tag_response_data['data']:
            for item in tag_response_data['data']['list']:
                if item.get('labelCnName') == '毛刺' and item.get('labelName') == 'maoci':
                    target_label_data = item
                    break

        if target_label_data:
            # 如果找到了标签，检查其状态
            if target_label_data.get('status') == 1:
                # 状态已经是1，直接添加产品标签
                maoci_success = True
            else:
                # 状态不是1，需要发布后再添加产品标签
                label_definition_id = target_label_data.get('labelDefinitionId')
                if label_definition_id:
                    # 调用标签库发布
                    publish_response = self.api_space.tag_library_publish(label_definition_id)
                    if publish_response.status_code == 200 and 'success' in publish_response.json():
                        # 发布成功
                        maoci_success = True
                    else:
                        # 发布失败
                        maoci_success = False
                else:
                    # 没有获取到labelDefinitionId
                    maoci_success = False
        else:
            # 没有找到"毛刺"标签，需要先创建
            # 先调用光学方案查询
            optical_response = self.api_space.optical_scheme_query()
            optical_data = optical_response.json()

            dictionary_option_id = None
            if optical_data.get('success') and 'data' in optical_data:
                # 如果有数据，提取第一个id
                if len(optical_data['data']) > 0:
                    dictionary_option_id = optical_data['data'][0].get('id')

            # 如果没有光学方案数据，则按顺序创建光源类型、光源配方、光学方案
            if not dictionary_option_id:
                # 调用光源类型新增
                light_source_type_response = self.api_space.add_light_source_type()

                # 调用光源配方新增
                light_source_formula_response = self.api_space.add_light_source_formula()

                # 调用光学方案新增
                optical_scheme_response = self.api_space.add_optical_scheme()

                # 再次调用光学方案查询
                optical_response = self.api_space.optical_scheme_query()
                optical_data = optical_response.json()

                if optical_data.get('success') and 'data' in optical_data:
                    # 找到schemeName等于"接口自动化-光学方案"的数据
                    for item in optical_data['data']:
                        if item.get('schemeName') == '接口自动化-光学方案':
                            dictionary_option_id = item.get('id')
                            break

            # 现在有了dictionary_option_id，可以添加标签库
            if dictionary_option_id:
                # 调用标签库新增
                add_tag_response = self.api_space.add_tag_library("毛刺", "maoci", dictionary_option_id)

                # 添加成功后，再次查询标签库获取新创建的标签信息
                import time
                time.sleep(1)  # 等待标签创建完成

                tag_response = self.api_space.tag_library_query("maoci")
                tag_response_data = tag_response.json()

                # 再次查找新创建的标签
                target_label_data = None
                if tag_response_data.get('success') and 'data' in tag_response_data and 'list' in tag_response_data[
                    'data']:
                    for item in tag_response_data['data']['list']:
                        if item.get('labelCnName') == '毛刺' and item.get('labelName') == 'maoci':
                            target_label_data = item
                            break

                if target_label_data:
                    # 获取labelDefinitionId并发布
                    label_definition_id = target_label_data.get('labelDefinitionId')
                    if label_definition_id:
                        # 调用标签库发布
                        publish_response = self.api_space.tag_library_publish(label_definition_id)
                        if publish_response.status_code == 200 and 'success' in publish_response.json():
                            # 发布成功
                            maoci_success = True
                        else:
                            # 发布失败
                            maoci_success = False
                    else:
                        # 创建标签失败
                        maoci_success = False
                else:
                    # 创建标签失败
                    maoci_success = False
            else:
                # 没有获得dictionary_option_id，抛错
                raise Exception("Failed to obtain dictionary_option_id for adding 'maoci' label")

        # 然后处理"缩孔"标签
        # 先检查标签库中是否存在"缩孔"标签
        tag_response = self.api_space.tag_library_query("suokong")
        tag_response_data = tag_response.json()

        # 检查是否存在labelCnName等于"缩孔"且labelName等于"suokong"的数据
        target_label_data = None
        if tag_response_data.get('success') and 'data' in tag_response_data and 'list' in tag_response_data['data']:
            for item in tag_response_data['data']['list']:
                if item.get('labelCnName') == '缩孔' and item.get('labelName') == 'suokong':
                    target_label_data = item
                    break

        if target_label_data:
            # 如果找到了标签，检查其状态
            if target_label_data.get('status') == 1:
                # 状态已经是1，直接添加产品标签
                suokong_success = True
            else:
                # 状态不是1，需要发布后再添加产品标签
                label_definition_id = target_label_data.get('labelDefinitionId')
                if label_definition_id:
                    # 调用标签库发布
                    publish_response = self.api_space.tag_library_publish(label_definition_id)
                    if publish_response.status_code == 200 and 'success' in publish_response.json():
                        # 发布成功
                        suokong_success = True
                    else:
                        # 发布失败
                        suokong_success = False
                else:
                    # 没有获取到labelDefinitionId
                    suokong_success = False
        else:
            # 没有找到"缩孔"标签，需要先创建
            # 先调用光学方案查询
            optical_response = self.api_space.optical_scheme_query()
            optical_data = optical_response.json()

            dictionary_option_id = None
            if optical_data.get('success') and 'data' in optical_data:
                # 如果有数据，提取第一个id
                if len(optical_data['data']) > 0:
                    dictionary_option_id = optical_data['data'][0].get('id')

            # 如果没有光学方案数据，则按顺序创建光源类型、光源配方、光学方案
            if not dictionary_option_id:
                # 调用光源类型新增
                light_source_type_response = self.api_space.add_light_source_type()

                # 调用光源配方新增
                light_source_formula_response = self.api_space.add_light_source_formula()

                # 调用光学方案新增
                optical_scheme_response = self.api_space.add_optical_scheme()

                # 再次调用光学方案查询
                optical_response = self.api_space.optical_scheme_query()
                optical_data = optical_response.json()

                if optical_data.get('success') and 'data' in optical_data:
                    # 找到schemeName等于"接口自动化-光学方案"的数据
                    for item in optical_data['data']:
                        if item.get('schemeName') == '接口自动化-光学方案':
                            dictionary_option_id = item.get('id')
                            break

            # 现在有了dictionary_option_id，可以添加标签库
            if dictionary_option_id:
                # 调用标签库新增
                add_tag_response = self.api_space.add_tag_library("缩孔", "suokong", dictionary_option_id)

                # 添加成功后，再次查询标签库获取新创建的标签信息
                import time
                time.sleep(1)  # 等待标签创建完成

                tag_response = self.api_space.tag_library_query("suokong")
                tag_response_data = tag_response.json()

                # 再次查找新创建的标签
                target_label_data = None
                if tag_response_data.get('success') and 'data' in tag_response_data and 'list' in tag_response_data[
                    'data']:
                    for item in tag_response_data['data']['list']:
                        if item.get('labelCnName') == '缩孔' and item.get('labelName') == 'suokong':
                            target_label_data = item
                            break

                if target_label_data:
                    # 获取labelDefinitionId并发布
                    label_definition_id = target_label_data.get('labelDefinitionId')
                    if label_definition_id:
                        # 调用标签库发布
                        publish_response = self.api_space.tag_library_publish(label_definition_id)
                        if publish_response.status_code == 200 and 'success' in publish_response.json():
                            # 发布成功
                            suokong_success = True
                        else:
                            # 发布失败
                            suokong_success = False
                    else:
                        # 创建标签失败
                        suokong_success = False
                else:
                    # 创建标签失败
                    suokong_success = False
            else:
                # 没有获得dictionary_option_id，抛错
                raise Exception("Failed to obtain dictionary_option_id for adding 'suokong' label")

        # 现在构建最终的标签列表
        label_name_list = []
        if maoci_success:
            label_name_list.append("maoci")
        if suokong_success:
            label_name_list.append("suokong")

        # 执行添加产品标签接口
        url = f"{env}/miai/brainstorm/labelinfo/add"
        payload = {"labelNameList": label_name_list, "productCode": product_code, "spaceType": 1}
        response = self.client.post_with_retry(url, json=payload)
        return response

    # 修改产品标签
    def modify_product_label(self, priority, labelId):
        url = f"{env}/miai/brainstorm/labelinfo/update"
        payload = {"labelCnName": "缩孔", "hotKey": None, "labelName": "suokong", "markMethod": "多边形",
                   "labelColor": "#FF0000", "lableType": "polygon", "productCode": product_code, "priority": priority,
                   "spaceManageId": manageid, "labelId": labelId, "status": 1}

        response = self.client.post_with_retry(url, json=payload)
        return response
