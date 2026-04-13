"""
验证bash系统挑图
"""
import configparser
import allure
import hashlib
from api import api_bash
from api.api_space import ApiSpace
from common import Assert
from datetime import datetime
from common.Request_Response import ApiClient

assertions = Assert.Assertions()

# 读取配置
config = configparser.ConfigParser()
config.read("./config/env_config.ini")
section_one = "Inspection"
section_two = "bash"
space_name = config.get(section_one, "space_name")
miai_product_code = config.get(section_one, "miai-product-code")
miaispacemanageid = config.get(section_one, "miaispacemanageid")
admin_account = config.get(section_two, "admin_account")
myself_name = config.get(section_two, "myself_name")

# 获取明文密码并进行MD5加密
plain_password = config.get(section_two, "admin_password")
admin_password = hashlib.md5(plain_password.encode()).hexdigest()  # 加密处理

# 格式化时间
current_date = datetime.now().strftime("%Y-%m-%d")
end_time = f"{current_date}T23:59:00.000Z"
start_time = f"{current_date}T00:00:00.000Z"

# 管理员账号
base_headers = {"Authorization": api_bash.ApiBashSample.bash_login(admin_account, admin_password)}
global_client = ApiClient(base_headers=base_headers)


@allure.feature("场景：Bash系统检查配置信息")
class TestBash:

    @classmethod
    def setup_class(cls):
        cls.api_bash = api_bash.ApiBashSample(global_client)
        cls.myself_id = None
        cls.bash_space_id = None
        cls.bash_product_id = None
        cls.shiftid = None

    @allure.story("登录管理员账号验证配置信息")
    def test_verify_product(self):
        with allure.step("步骤1：查看项目空间是否存在"):
            response = self.api_bash.query_project_manage(space_name)
            assertions.assert_code(response.status_code, 200)
            data = response.json()
            assertions.assert_in_text(data['msg'], '操作成功')

            # 检查是否有数据
            if 'data' not in data or not data['data'].get('list'):
                error_msg = "bash项目管理中没有对应的项目空间"
                allure.attach(error_msg, name="项目空间缺失错误", attachment_type=allure.attachment_type.TEXT)
                raise AssertionError(error_msg)

            # 获取第一个项目空间
            first_product = data['data']['list'][0]
            bash_space_id = first_product.get('id')
            TestBash.bash_space_id = bash_space_id

        with allure.step("步骤2：查看产品是否存在/修改处理模式为全量"):
            response = self.api_bash.query_product_manage(miaispacemanageid, miai_product_code)
            assertions.assert_code(response.status_code, 200)
            data = response.json()
            assertions.assert_in_text(data['msg'], '操作成功')

            # 检查是否有数据
            if 'data' not in data or not data['data'].get('list'):
                error_msg = "bash产品管理中没有对应的产品"
                allure.attach(error_msg, name="产品缺失错误", attachment_type=allure.attachment_type.TEXT)
                raise AssertionError(error_msg)

            # 获取第一个产品
            first_product = data['data']['list'][0]

            # 获取状态
            setting_status = first_product.get('settingStatus')

            # 获取bash产品id
            bash_product_id = first_product.get('id')
            TestBash.bash_product_id = bash_product_id

            # 检查产品状态
            if setting_status != 1:
                error_msg = f"产品状态异常（当前状态: {setting_status}），请登录bash系统查看"
                allure.attach(error_msg, name="产品状态错误", attachment_type=allure.attachment_type.TEXT)
                allure.attach(str(first_product), name="产品详情", attachment_type=allure.attachment_type.JSON)
                raise AssertionError(error_msg)

            # 调用更新接口修改处理模式为全量
            update_response = self.api_bash.update_product_manage(TestBash.bash_space_id, space_name,
                                                                  TestBash.bash_product_id, miai_product_code)
            update_data = update_response.json()
            if update_data.get('msg') != '操作成功':
                error_msg = f"更新产品处理模式失败: {update_data.get('msg')}"
                allure.attach(error_msg, name="更新产品错误", attachment_type=allure.attachment_type.TEXT)
                raise AssertionError(error_msg)
            else:
                allure.attach("成功更新产品处理模式为全量", name="产品更新成功",
                              attachment_type=allure.attachment_type.TEXT)

        with allure.step("步骤3：查看bash人员是否存在"):
            response = self.api_bash.query_personnel_id()
            assertions.assert_code(response.status_code, 200)
            data = response.json()
            assertions.assert_in_text(data['msg'], '操作成功')

            # 新增人员存在性检查
            if 'data' not in data or not data['data'].get('list'):
                error_msg = "人员列表为空"
                allure.attach(error_msg, name="人员列表为空错误", attachment_type=allure.attachment_type.TEXT)
                raise AssertionError(error_msg)

            # 在人员列表中查找指定用户名的人员
            target_person = None
            for person in data['data']['list']:
                # 假设人员对象中有 'username' 字段
                if person.get('username') == myself_name:  # 使用配置文件中读取的 myself_name
                    target_person = person
                    break

            if not target_person:
                error_msg = f"bash分拣账号的人员 {myself_name} 不存在"
                allure.attach(error_msg, name="人员不存在错误", attachment_type=allure.attachment_type.TEXT)
                allure.attach(str(data['data']['list']), name="人员列表详情",
                              attachment_type=allure.attachment_type.JSON)
                raise AssertionError(error_msg)

            # 获取人员ID
            person_id = target_person.get('id')
            if not person_id:
                error_msg = f"找到人员 {myself_name} 但未获取到ID"
                allure.attach(error_msg, name="ID缺失错误", attachment_type=allure.attachment_type.TEXT)
                raise AssertionError(error_msg)

            # 记录人员ID到Allure报告
            allure.attach(f"人员 {myself_name} 的ID: {person_id}",
                          name="人员ID信息",
                          attachment_type=allure.attachment_type.TEXT)

            # 将人员ID存储到类属性中
            self.myself_id = person_id

        with allure.step("步骤4：查看人员与产品是否关联"):
            response = self.api_bash.query_product_manage_person(self.myself_id)
            assertions.assert_code(response.status_code, 200)
            data = response.json()
            assertions.assert_in_text(data['msg'], '操作成功')

            # 检查是否有数据
            if 'data' not in data or not data['data'].get('list'):
                error_msg = "坐席人员列表为空"
                allure.attach(error_msg, name="人员列表为空错误", attachment_type=allure.attachment_type.TEXT)
                raise AssertionError(error_msg)

            # 遍历人员列表，查找是否存在目标产品代码
            found = False
            for person in data['data']['list']:
                if person.get('productCode') == miai_product_code:
                    found = True
                    break

            if not found:
                with allure.step("子步骤1：关联人员与产品（优先级递减重试）"):
                    # 从100到1尝试优先级
                    for priority in range(100, 0, -1):
                        response = self.api_bash.add_personnel_product(
                            TestBash.bash_product_id,
                            priority,
                            self.myself_id
                        )
                        res_data = response.json()

                        # 成功情况
                        if res_data.get('msg') == '操作成功':
                            allure.attach(f"成功关联产品，优先级: {priority}",
                                          name="关联成功",
                                          attachment_type=allure.attachment_type.TEXT)
                            break

                        # 优先级重复情况
                        elif "坐席产品优先级已存在" in res_data.get('msg', ''):
                            allure.attach(f"优先级 {priority} 已存在，尝试 {priority - 1}",
                                          name="优先级冲突",
                                          attachment_type=allure.attachment_type.TEXT)

                            # 最后一个优先级尝试失败
                            if priority == 1:
                                error_msg = "该用户产品优先级已满（1-100均被占用）"
                                allure.attach(error_msg,
                                              name="优先级耗尽错误",
                                              attachment_type=allure.attachment_type.TEXT)
                                raise AssertionError(error_msg)

                        # 其他错误情况
                        else:
                            error_msg = f"关联失败: {res_data.get('msg')}"
                            allure.attach(error_msg,
                                          name="关联错误",
                                          attachment_type=allure.attachment_type.TEXT)
                            raise AssertionError(error_msg)

        with allure.step("步骤5：查询班次管理"):
            response = self.api_bash.query_shift_management()
            assertions.assert_code(response.status_code, 200)
            data = response.json()
            assertions.assert_in_text(data['msg'], '操作成功')

            # 检查是否有数据
            if 'data' not in data or not data['data']:
                error_msg = "班次列表为空"
                allure.attach(error_msg, name="班次数据为空错误", attachment_type=allure.attachment_type.TEXT)
                raise AssertionError(error_msg)

            # 查找满足条件的班次
            target_shift = None
            for shift in data['data']:
                if (shift.get('startTime') == "00:00:00" and
                        shift.get('endTime') == "23:59:00"):
                    target_shift = shift
                    break

            if not target_shift:
                error_msg = "未找到白班班次（00:00:00 - 23:59:00）"
                allure.attach(error_msg, name="班次缺失错误", attachment_type=allure.attachment_type.TEXT)
                raise AssertionError(error_msg)

            # 获取班次ID并保存到类属性
            shift_id = target_shift.get('id')
            if not shift_id:
                error_msg = "找到班次但未获取到ID"
                allure.attach(error_msg, name="ID缺失错误", attachment_type=allure.attachment_type.TEXT)
                raise AssertionError(error_msg)

            TestBash.shiftid = shift_id
            allure.attach(f"白班班次ID: {shift_id}",
                          name="班次ID信息",
                          attachment_type=allure.attachment_type.TEXT)

        with allure.step("步骤6：查看人员计划"):
            response = self.api_bash.query_personnel_plan()
            assertions.assert_code(response.status_code, 200)
            data = response.json()
            assertions.assert_in_text(data['msg'], '操作成功')

            # 检查是否存在当日数据（合并无数据和有数据但无当日数据的情况）
            target_date = f"{current_date}T00:00:00"

            # 初始化标志
            has_today_plan = False

            # 只有当有数据时才检查
            if 'data' in data and data['data'].get('list'):
                for plan in data['data']['list']:
                    if plan.get('startTime') == target_date:
                        has_today_plan = True
                        break

            # 如果没有当日数据（包括无数据的情况），执行生成操作
            if not has_today_plan:
                with allure.step("子步骤1：生成人员计划（无当日数据时触发）"):
                    # 调用生成人员计划方法
                    response = self.api_bash.create_personnel_plan(end_time, start_time, self.shiftid)
                    assertions.assert_code(response.status_code, 200)
                    data = response.json()
                    assertions.assert_in_text(data['msg'], '操作成功')

                    # 记录操作信息到报告
                    allure.attach(f"已生成当日({current_date})人员计划",
                                  name="生成人员计划成功",
                                  attachment_type=allure.attachment_type.TEXT)

        with allure.step("步骤7：查看人员排班"):
            response = self.api_bash.query_personnel_schedule(end_time, start_time)
            assertions.assert_code(response.status_code, 200)
            data = response.json()
            assertions.assert_in_text(data['msg'], '操作成功')

            # 初始化标志
            found_user = False

            # 检查是否存在指定人员（即使数据为空也会执行）
            if 'data' in data and data['data'].get('selectedUserListVos'):
                for user in data['data']['selectedUserListVos']:
                    if user.get('userName') == myself_name:
                        found_user = True
                        break

            if not found_user:
                with allure.step("子步骤1：修改人员排班（缺少指定人员时触发）"):
                    # 获取toBeSelectedUserListVos中的所有ID
                    to_be_selected = data['data'].get('toBeSelectedUserListVos', [])
                    userid_list = [str(user.get('id')) for user in to_be_selected if user.get('id')]

                    # 拼接ID列表为字符串格式
                    userid_list_str = "[" + ", ".join(f'"{id}"' for id in userid_list) + "]"

                    # 记录ID列表到Allure报告
                    allure.attach(f"待选用户ID列表: {userid_list_str}",
                                  name="待选用户ID",
                                  attachment_type=allure.attachment_type.TEXT)

                    # 调用修改人员排班方法
                    response = self.api_bash.update_personnel_schedule(end_time, start_time, userid_list, self.shiftid)
                    assertions.assert_code(response.status_code, 200)
                    data = response.json()
                    assertions.assert_in_text(data['msg'], '操作成功')

                    # 记录操作信息到报告
                    allure.attach("已将指定人员添加到当日排班",
                                  name="修改人员排班",
                                  attachment_type=allure.attachment_type.TEXT)

        with allure.step("步骤8：验证排班状态"):
            response = self.api_bash.query_personnel_plan()
            assertions.assert_code(response.status_code, 200)
            data = response.json()
            assertions.assert_in_text(data['msg'], '操作成功')

            # 检查是否有数据
            if 'data' not in data or not data['data'].get('list'):
                error_msg = "人员计划数据为空"
                allure.attach(error_msg, name="计划数据为空错误", attachment_type=allure.attachment_type.TEXT)
                raise AssertionError(error_msg)

            # 查找当日计划
            today_plan = None
            for plan in data['data']['list']:
                if plan.get('startTime') == start_time.replace('.000Z', ''):
                    today_plan = plan
                    break

            if not today_plan:
                error_msg = f"未找到当日({current_date})人员计划"
                allure.attach(error_msg, name="计划缺失错误", attachment_type=allure.attachment_type.TEXT)
                raise AssertionError(error_msg)

            # 检查发布状态
            is_release = today_plan.get('isRelease')
            if is_release == 0:
                with allure.step("子步骤1：发布排班（未发布时触发）"):
                    # 调用发布排班方法
                    response = self.api_bash.release_personnel_schedule(end_time.replace('.000Z', ''),
                                                                        start_time.replace('.000Z', ''))
                    assertions.assert_code(response.status_code, 200)
                    data = response.json()
                    assertions.assert_in_text(data['msg'], '操作成功')

                    # 记录操作信息到报告
                    allure.attach(f"已发布当日({current_date})排班",
                                  name="发布排班成功",
                                  attachment_type=allure.attachment_type.TEXT)
            elif is_release == 1:
                with allure.step("排班已发布，结束测试"):
                    allure.attach(f"当日({current_date})排班已发布",
                                  name="排班状态",
                                  attachment_type=allure.attachment_type.TEXT)
            else:
                error_msg = f"未知的排班状态: {is_release}"
                allure.attach(error_msg, name="排班状态错误", attachment_type=allure.attachment_type.TEXT)
                raise AssertionError(error_msg)

        # with allure.step("步骤9：验证一休机台管理"):
        #     # 初始化一休云空间API
        #     api_space = ApiSpace()
        #     device_id = None  # 用于存储设备ID
        #
        #     # 第一次查询机台列表
        #     response = api_space.machine_query()
        #     assertions.assert_code(response.status_code, 200)
        #     data = response.json()
        #
        #     # 检查响应是否成功
        #     if not data.get("success", False):
        #         error_msg = f"查询机台失败: {data.get('msg', '未知错误')}"
        #         allure.attach(error_msg, name="机台查询错误", attachment_type=allure.attachment_type.TEXT)
        #         raise AssertionError(error_msg)
        #
        #     # 判断是否有数据
        #     has_data = 'data' in data and data['data'].get('list') is not None and len(data['data']['list']) > 0
        #     found_device = False
        #
        #     # 如果有数据，检查是否有目标设备
        #     if has_data:
        #         for machine in data['data']['list']:
        #             if (machine.get('spaceName') == space_name and
        #                     machine.get('localDeviceNo') == miai_product_code):
        #                 # 提取cloudDeviceNo值
        #                 device_id = machine.get('cloudDeviceNo')
        #                 if device_id:
        #                     found_device = True
        #                     allure.attach(f"找到匹配机台: {machine}",
        #                                   name="机台详情",
        #                                   attachment_type=allure.attachment_type.JSON)
        #                     allure.attach(f"提取机台ID: {device_id}",
        #                                   name="机台ID",
        #                                   attachment_type=allure.attachment_type.TEXT)
        #                     break
        #
        #     # 如果没有数据或没有找到目标设备，添加机台并再次查询
        #     if not has_data or not found_device:
        #         with allure.step("子步骤1：添加机台"):
        #             response = api_space.machine_add()
        #             assertions.assert_code(response.status_code, 200)
        #             add_data = response.json()
        #
        #             if not add_data.get("success", False):
        #                 error_msg = f"添加机台失败: {add_data.get('msg', '未知错误')}"
        #                 allure.attach(error_msg, name="添加机台错误", attachment_type=allure.attachment_type.TEXT)
        #                 raise AssertionError(error_msg)
        #
        #             allure.attach("已添加新机台",
        #                           name="添加机台成功",
        #                           attachment_type=allure.attachment_type.TEXT)
        #
        #         with allure.step("子步骤2：再次查询机台列表"):
        #             response = api_space.machine_query()
        #             assertions.assert_code(response.status_code, 200)
        #             data = response.json()
        #
        #             if not data.get("success", False):
        #                 error_msg = f"再次查询机台失败: {data.get('msg', '未知错误')}"
        #                 allure.attach(error_msg, name="机台查询错误", attachment_type=allure.attachment_type.TEXT)
        #                 raise AssertionError(error_msg)
        #
        #             # 检查是否有数据
        #             if 'data' not in data or not data['data'].get('list'):
        #                 error_msg = "机台列表仍为空，添加机台后未找到机台"
        #                 allure.attach(error_msg, name="机台数据为空错误", attachment_type=allure.attachment_type.TEXT)
        #                 raise AssertionError(error_msg)
        #
        #             # 在机台列表中查找目标设备
        #             found_device = False
        #             for machine in data['data']['list']:
        #                 if (machine.get('spaceName') == space_name and
        #                         machine.get('localDeviceNo') == miai_product_code):
        #                     # 提取cloudDeviceNo值
        #                     device_id = machine.get('cloudDeviceNo')
        #                     if device_id:
        #                         found_device = True
        #                         allure.attach(f"找到新添加机台: {machine}",
        #                                       name="机台详情",
        #                                       attachment_type=allure.attachment_type.JSON)
        #                         allure.attach(f"提取机台ID: {device_id}",
        #                                       name="机台ID",
        #                                       attachment_type=allure.attachment_type.TEXT)
        #                         break
        #
        #             # 如果第二次查询后仍未找到设备ID
        #             if not found_device:
        #                 error_msg = "添加机台后仍未找到目标机台"
        #                 allure.attach(error_msg, name="机台缺失错误", attachment_type=allure.attachment_type.TEXT)
        #                 raise AssertionError(error_msg)
        #
        # with allure.step("步骤10：下载设备Token"):
        #     # 确保设备ID存在
        #     if not device_id:
        #         error_msg = "机台ID缺失，无法下载Token"
        #         allure.attach(error_msg, name="机台ID缺失错误", attachment_type=allure.attachment_type.TEXT)
        #         raise AssertionError(error_msg)
        #
        #     # 下载机台Token
        #     token_path = api_space.machine_token_download(device_id)
        #     if not token_path:
        #         error_msg = "下载机台Token失败"
        #         allure.attach(error_msg, name="Token下载错误", attachment_type=allure.attachment_type.TEXT)
        #         raise AssertionError(error_msg)
        #
        #     # 记录下载成功信息
        #     allure.attach(f"Token文件路径: {token_path}",
        #                   name="Token下载成功",
        #                   attachment_type=allure.attachment_type.TEXT)
        #
        #     # 读取并记录Token内容
        #     try:
        #         with open(token_path, 'r') as f:
        #             token_content = f.read()
        #             allure.attach(f"机台Token: {token_content}",
        #                           name="Token内容",
        #                           attachment_type=allure.attachment_type.TEXT)
        #     except Exception as e:
        #         error_msg = f"读取Token文件失败: {str(e)}"
        #         allure.attach(error_msg, name="Token读取错误", attachment_type=allure.attachment_type.TEXT)
