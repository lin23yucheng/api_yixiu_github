"""
模型库功能
"""
import json
import os
import time
import pytest
import allure
import requests
import ast
import configparser
from common import Assert
from common.Request_Response import ApiClient
from api.api_login import ApiLogin
from api import api_login, api_deep_training_tasks, api_model_base

assertions = Assert.Assertions()
env = api_login.url
time_str = time.strftime("%Y%m%d%H%M%S", time.localtime())
manageid = api_login.miaispacemanageid
login = ApiLogin()
token = login.login()

# 初始化全局客户端
base_headers = {
    "Authorization": api_login.ApiLogin().login(),
    "Miai-Product-Code": api_login.code,
    "Miaispacemanageid": api_login.manageid
}
global_client = ApiClient(base_headers=base_headers)


@allure.feature("场景：综合-模型库流程")
class TestModelBase:
    @classmethod
    def setup_class(cls):
        cls.api_deep = api_deep_training_tasks.ApiDeepTrainTasks(global_client)
        cls.api_model = api_deep_training_tasks.ApiModelTrain(global_client)
        cls.api_process = api_deep_training_tasks.ApiPostProcess(global_client)
        cls.api_base = api_model_base.ApiModelBase(global_client)
        cls.max_wait_seconds = 1800  # 最大等待30分钟
        cls.poll_interval = 10  # 轮询间10秒
        cls.modelTrainId = None
        cls.class_cut_modelTrainId = None
        cls.class_original_modelTrainId = None
        cls.modelManageId = None
        cls.combination_modelManageId = None
        cls.class_cut_modelManageId = None
        cls.class_original_modelManageId = None
        cls.trainTaskId = None
        cls.class_cut_trainTaskId = None
        cls.class_original_trainTaskId = None
        # 读取配置文件
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'env_config.ini')
        config = configparser.ConfigParser()
        config.read(config_path)
        cls.photoId_ok = ast.literal_eval(config.get('persistent_ids', 'photo_id_ok'))

    def get_testdata_path(self, filename):
        """获取测试数据文件路径"""
        # 获取当前测试文件所在目录
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # 构建到testdata目录的路径
        testdata_dir = os.path.join(current_dir, "..", "testdata")
        # 返回完整文件路径
        return os.path.join(testdata_dir, filename)

    def _get_model_manage_id(self, model_train_id=None, model_name=None):
        """通用方法：根据modelTrainId或模型名称获取modelManageId"""
        response = self.api_base.query_model_base()
        assertions.assert_code(response.status_code, 200)
        response_data = response.json()

        model_list = response_data.get('data', {}).get('list', [])
        for model in model_list:
            if model_train_id and model.get('modelTrainId') == model_train_id:
                return model.get('modelManageId')
            if model_name and model.get('name') == model_name:
                return model.get('modelManageId')

        pytest.fail(f"未找到匹配的modelManageId: {model_train_id or model_name}")

    def _monitor_generic_progress(self, api_call, get_status_func,
                                  in_progress_status, success_status,
                                  step_name, status_mapping=None):
        """
        模型库通用状态监控方法
        """
        start_time = time.time()
        total_start = time.time()  # 总开始时间
        attempt = 0

        # 默认状态映射
        if status_mapping is None:
            status_mapping = {
                0: "已提交",
                1: "测试中",
                2: "测试失败",
                3: "测试完成",
                4: "已发布",
                5: "组合中",
                6: "组合失败",
                7: "未提交"
            }

        # 状态跟踪变量
        prev_status = None
        status_start_time = None
        status_durations = {}  # 存储各状态持续时间
        last_status_info = ""  # 存储上一个状态的信息

        with allure.step(f"监控{step_name}状态"):
            while True:
                attempt += 1
                with allure.step(f"第{attempt}次状态检查"):
                    # 发送查询请求
                    response = api_call()
                    assertions.assert_code(response.status_code, 200)

                    # 解析响应数据
                    response_data = response.json()

                    # 获取当前状态
                    current_status = get_status_func(response_data)

                    # 确保找到状态值
                    assertions.assert_is_not_none(
                        current_status,
                        f"未找到状态信息"
                    )

                    # 记录原始响应到Allure
                    allure.attach(
                        str(response_data),
                        name=f"{step_name}响应数据",
                        attachment_type=allure.attachment_type.JSON
                    )

                    # 状态变更检测
                    if current_status != prev_status:
                        # 记录上一个状态的持续时间
                        if prev_status is not None and status_start_time is not None:
                            status_duration = time.time() - status_start_time
                            status_key = status_mapping.get(prev_status, f"未知({prev_status})")
                            status_durations[status_key] = status_duration

                            # 打印状态变更信息（保留在控制台）
                            status_duration_mins, status_duration_secs = divmod(int(status_duration), 60)
                            print(
                                f"\n{step_name}状态变更: {status_key} 耗时 {status_duration_mins}分{status_duration_secs}秒")

                            allure.attach(
                                f"状态 '{status_key}' 耗时: {status_duration:.1f}秒",
                                name="状态变更记录"
                            )

                        # 重置新状态开始时间
                        status_start_time = time.time()
                        prev_status = current_status

                    # 时间统计
                    total_duration = int(time.time() - total_start)
                    total_mins, total_secs = divmod(total_duration, 60)
                    current_status_duration = int(time.time() - status_start_time) if status_start_time else 0

                    # 构建状态信息
                    status_desc = status_mapping.get(current_status, f"未知状态({current_status})")
                    status_info = (
                        f"{step_name}状态: {status_desc} | "
                        f"当前状态耗时: {current_status_duration}秒 | "
                        f"总耗时: {total_mins}分{total_secs}秒"
                    )

                    # 获取颜色代码 - 基于状态描述
                    if "完成" in status_desc or "成功" in status_desc or "已发布" in status_desc:
                        color_code = "\033[92m"  # 绿色
                    elif "中" in status_desc or "进行" in status_desc:
                        color_code = "\033[93m"  # 黄色
                    elif "失败" in status_desc or "错误" in status_desc:
                        color_code = "\033[91m"  # 红色
                    else:
                        color_code = "\033[0m"  # 默认

                    # 仅当状态信息变化时更新控制台（避免频繁刷新）
                    if status_info != last_status_info:
                        # 单行更新（使用回车符覆盖上一行）
                        print(f"\r{color_code}{status_info}\033[0m", end="", flush=True)
                        last_status_info = status_info

                    # 状态判断
                    if current_status == in_progress_status:  # 进行中状态
                        # 检查是否超时
                        elapsed = time.time() - start_time
                        if elapsed > self.max_wait_seconds:
                            pytest.fail(f"{step_name}超时: 等待{self.max_wait_seconds}秒未完成")

                        # 等待下一次轮询
                        time.sleep(self.poll_interval)
                        continue

                    elif current_status == success_status:  # 成功状态
                        # 记录最终状态持续时间
                        if prev_status is not None and status_start_time is not None:
                            final_duration = time.time() - status_start_time
                            final_status = status_mapping.get(current_status, f"未知({current_status})")
                            status_durations[final_status] = final_duration

                        # 生成状态耗时报告（仅记录到Allure，不在控制台打印）
                        report_lines = [f"{step_name}状态耗时统计:"]
                        for status, duration in status_durations.items():
                            duration_mins, duration_secs = divmod(int(duration), 60)
                            report_lines.append(f"- {status}: {duration_mins}分{duration_secs}秒")
                        report_lines.append(f"总耗时: {total_mins}分{total_secs}秒")
                        report = "\n".join(report_lines)

                        allure.attach(report, name=f"{step_name}耗时统计")

                        # 打印最终状态信息（带颜色）
                        status_desc = status_mapping.get(current_status, f"未知状态({current_status})")
                        final_info = f"{step_name}状态: {status_desc} | 总耗时: {total_mins}分{total_secs}秒"

                        # 再次确定颜色（确保成功状态显示绿色）
                        if "完成" in status_desc or "成功" in status_desc or "已发布" in status_desc:
                            color_code = "\033[92m"  # 绿色
                        else:
                            color_code = "\033[0m"  # 默认

                        print(f"\r{color_code}{final_info}\033[0m")

                        return True

                    elif current_status in [2, 6]:  # 失败状态
                        pytest.fail(f"{step_name}失败，请检查日志（状态{current_status}）")

                    else:  # 其他状态
                        pytest.fail(f"{step_name}遇到未知状态: {current_status}")

    @allure.story("模型库测试流程")
    @allure.title("模型组合测试全流程")
    def test_deployment(self):

        with allure.step("步骤1：模型组合"):
            # 读取组合模型JSON
            json_path = self.get_testdata_path("组合模型.json")
            with open(json_path, "r", encoding="utf-8") as f:
                combine_json = json.load(f)

            # 更新组合名称（保持唯一性）
            combine_json["name"] = f"自动化模型组合-{time_str}"

            response = requests.post(
                headers={"content-type": "application/json", "Authorization": token, "Miaispacemanageid": manageid},
                url=f"{env}/miai/brainstorm/combine/model/start",
                json=combine_json
            )

            # 响应断言
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

        with allure.step("步骤2：提取组合模型的modelManageId"):
            self.__class__.combination_modelManageId = self._get_model_manage_id(
                model_name=f"自动化模型组合-{time_str}"
            )
            allure.attach(
                f"combination_modelManageId: {self.combination_modelManageId}",
                name="组合模型ManageID",
                attachment_type=allure.attachment_type.TEXT
            )

        with allure.step("步骤3：监控模型组合状态"):
            # 定义状态提取函数（根据实际API响应调整）
            def get_combine_status(response_data):
                model_list = response_data.get('data', {}).get('list', [])
                for model in model_list:
                    if model.get('modelManageId') == self.__class__.combination_modelManageId:
                        return model.get('status')
                return None

            # 调用监控方法
            self._monitor_generic_progress(
                api_call=self.api_base.query_model_base,
                get_status_func=get_combine_status,
                in_progress_status=5,  # 组合中
                success_status=7,  # 组合完成（未提交）
                step_name="模型组合",
                status_mapping={
                    5: "组合中",
                    6: "组合失败",
                    7: "组合完成（未提交）"
                }
            )

        with allure.step("步骤4：组合模型验证"):
            response = self.api_base.model_verify(
                self.__class__.combination_modelManageId,
                self.photoId_ok
            )

            # 响应断言
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

        with allure.step("步骤5：监控组合模型的验证状态"):
            # 定义状态提取函数（根据实际API响应调整）
            def get_combine_status(response_data):
                model_list = response_data.get('data', {}).get('list', [])
                for model in model_list:
                    if model.get('modelManageId') == self.__class__.combination_modelManageId:
                        return model.get('verifyStatus')
                return None

            # 调用监控方法
            self._monitor_generic_progress(
                api_call=self.api_base.query_model_base,
                get_status_func=get_combine_status,
                in_progress_status=1,  # 验证中
                success_status=2,  # 验证完成
                step_name="组合模型验证",
                status_mapping={
                    0: "未验证",
                    1: "验证中",
                    2: "验证完成",
                    3: "验证失败"
                }
            )

        with allure.step("步骤6：组合模型提交"):
            response = self.api_base.model_submit(self.__class__.combination_modelManageId)

            # 响应断言
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

        with allure.step("步骤7：组合模型删除"):
            response = self.api_base.model_withdraw(self.__class__.combination_modelManageId, 2)

            # 响应断言
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')
