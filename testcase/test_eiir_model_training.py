"""
EIIR模型训练接口自动化流程
"""
import pytest
import allure
import time
import os
import ast
from common.Request_Response import ApiClient
from common import Assert
import configparser
from api import api_login, api_eiir_samples, api_deep_training_tasks, api_eiir_training_tasks, api_space, api_eiir_model
from datetime import datetime, timedelta

assertions = Assert.Assertions()
time_str = time.strftime("%Y%m%d%H%M%S", time.localtime())

# 读取配置文件
config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'env_config.ini')
config = configparser.ConfigParser()
config.read(config_path, encoding='utf-8')

# 获取当前环境并从对应环境节读取
env = config.get("environment", "execution_env", fallback="").strip().lower()
if env not in {"fat", "prod"}:
    raise ValueError(f"execution_env 配置错误: {env}，仅支持 fat 或 prod")

env_eiir_section = f"{env}-EIIR"
space_name = config.get(env_eiir_section, 'space_name')
machine_name = config.get(env_eiir_section, 'machine_name')
# 使用 ast.literal_eval 将字符串转换为列表
machineId = ast.literal_eval(config.get(env_eiir_section, 'machineId'))
componentLabel = ast.literal_eval(config.get(env_eiir_section, 'componentLabel'))
append_componentLabel = ast.literal_eval(config.get(env_eiir_section, 'append_componentLabel'))

# 获取空间ID - 添加错误检查
miaispacemanageid = None
try:
    miaispacemanageid = api_space.ApiSpace().space_query(space_name)
    if not miaispacemanageid:
        raise ValueError(f"无法获取空间 '{space_name}' 的 spaceManageId")
except Exception as e:
    pytest.fail(f"空间ID获取失败: {str(e)}", pytrace=False)

# 初始化全局客户端
base_headers = {
    "Authorization": api_login.ApiLogin().login(),
    "Miaispacemanageid": miaispacemanageid
}
global_client = ApiClient(base_headers=base_headers)

# 计算日期参数
current_date = datetime.now()
endDateTime = current_date.strftime("%Y-%m-%d")
startDateTime = (current_date - timedelta(days=1)).strftime("%Y-%m-%d")
start_time = "2025-06-01"
end_time = "2025-08-01"


@allure.feature("场景：EIIR模型训练全流程")
class TestEiirModelTraining:
    @classmethod
    def setup_class(cls):
        """初始化接口封装实例"""
        cls.api_eiir_samples = api_eiir_samples.ApiEiirSamples(global_client)
        cls.api_eiir_training = api_eiir_training_tasks.ApiEiirTraining(global_client)
        cls.api_model = api_deep_training_tasks.ApiModelTrain(global_client)
        cls.api_eiir_model = api_eiir_model.ApiEiirModel(global_client)
        cls.task_name = f"接口自动化_{time_str}_EIIR"  # 统一任务名称格式
        cls.max_wait_seconds = 1800  # 最大等待30分钟
        cls.poll_interval = 10  # 轮询间隔10秒
        cls.start_timestamp = None  # 新增时间记录点
        cls.trainTaskId = None
        cls.modelTrainId = None
        cls.modelManageId = None

    def _monitor_eiir_data_progress(self, task_name, step_name):
        """
        监控EIIR数据处理进度的通用方法
        """
        start_time = time.time()
        attempt = 0

        # 状态映射
        status_mapping = {
            0: "数据准备中",
            1: "数据正常",
            2: "数据异常"
        }

        # 用于标记是否已提取trainTaskId
        train_task_id_extracted = False

        with allure.step(f"监控{step_name}状态"):
            while True:
                attempt += 1
                with allure.step(f"第{attempt}次状态检查"):
                    # 发送查询请求
                    response = self.api_eiir_training.query_eiir_task(task_name)
                    assertions.assert_code(response.status_code, 200)

                    # 解析响应数据
                    response_data = response.json()
                    data_list = response_data.get('data', {}).get('list', [])

                    # 记录原始响应到Allure
                    allure.attach(
                        str(response_data),
                        name=f"{step_name}响应数据",
                        attachment_type=allure.attachment_type.JSON
                    )

                    # 查找匹配的任务
                    target_task = None
                    for task in data_list:
                        if task.get('taskName') == task_name:
                            target_task = task
                            break

                    if not target_task:
                        pytest.fail(f"未找到任务名称为 '{task_name}' 的任务")

                    # 提取trainTaskId（仅提取一次）
                    if not train_task_id_extracted:
                        train_task_id = target_task.get('trainTaskId')
                        if train_task_id:
                            self.__class__.trainTaskId = train_task_id
                            train_task_id_extracted = True
                            allure.attach(
                                f"提取到trainTaskId: {train_task_id}",
                                name="trainTaskId提取",
                                attachment_type=allure.attachment_type.TEXT
                            )

                    # 获取dataStatus
                    data_status = target_task.get('dataStatus')

                    # 时间统计
                    current_duration = int(time.time() - start_time)
                    mins, secs = divmod(current_duration, 60)

                    # 构建状态信息
                    status_desc = status_mapping.get(data_status, f"未知状态({data_status})")
                    status_info = f"{step_name}状态: {status_desc} | 耗时: {mins}分{secs}秒"

                    # 根据状态描述选择颜色
                    if data_status == 1:  # 处理完成 - 绿色
                        color_code = "\033[92m"
                    elif data_status == 0:  # 处理中 - 黄色
                        color_code = "\033[93m"
                    else:  # 异常状态 - 红色
                        color_code = "\033[91m"

                    # 输出状态信息
                    print(f"\r{color_code}{status_info}\033[0m", end="", flush=True)

                    # 状态判断
                    if data_status == 1:  # 处理完成
                        print(f"\n", flush=True)
                        return True
                    elif data_status == 2:  # 处理异常
                        pytest.fail(f"{step_name}失败: 数据处理异常")
                    elif data_status != 0:  # 其他未知状态
                        pytest.fail(f"{step_name}遇到未知状态: {data_status}")

                    # 超时检查
                    elapsed = time.time() - start_time
                    if elapsed > self.max_wait_seconds:
                        pytest.fail(f"{step_name}超时: 等待{self.max_wait_seconds}秒未完成")

                    # 间隔等待
                    time.sleep(self.poll_interval)

    def _monitor_eiir_train_progress(self, step_name, success_train_status=4, success_test_status=3,
                                     success_commit_status=2):
        """
        监控EIIR训练进度的通用方法
        """
        start_time = time.time()
        attempt = 0

        # 状态映射
        train_status_mapping = {
            1: "排队中",
            2: "准备中",
            3: "训练中",
            4: "训练完成",
            5: "训练失败"
        }

        test_status_mapping = {
            0: "未验证",
            1: "验证中",
            2: "验证失败",
            3: "验证完成"
        }

        commit_status_mapping = {
            0: "未提交",
            1: "打包中",
            2: "已提交",
            3: "提交失败"
        }

        # 用于标记是否已提取modelTrainId
        model_train_id_extracted = False

        with allure.step(f"监控{step_name}状态"):
            while True:
                attempt += 1
                with allure.step(f"第{attempt}次状态检查"):
                    # 发送查询请求，需要传入trainTaskId参数
                    response = self.api_eiir_training.query_train_record(TestEiirModelTraining.trainTaskId)
                    assertions.assert_code(response.status_code, 200)

                    # 解析响应数据
                    response_data = response.json()
                    data_list = response_data.get('data', {}).get('list', [])

                    # 记录原始响应到Allure
                    allure.attach(
                        str(response_data),
                        name=f"{step_name}响应数据",
                        attachment_type=allure.attachment_type.JSON
                    )

                    if not data_list:
                        pytest.fail(f"{step_name}失败: 未查询到训练记录")

                    # 获取第一条数据的状态
                    first_record = data_list[0]
                    train_status = first_record.get('trainStatus')
                    test_status = first_record.get('testStatus')
                    commit_status = first_record.get('commitStatus')

                    # 提取modelTrainId（仅提取一次）
                    if not model_train_id_extracted:
                        model_train_id = first_record.get('modelTrainId')
                        if model_train_id:
                            self.__class__.modelTrainId = model_train_id
                            model_train_id_extracted = True
                            allure.attach(
                                f"提取到modelTrainId: {model_train_id}",
                                name="modelTrainId提取",
                                attachment_type=allure.attachment_type.TEXT
                            )

                    # 时间统计
                    current_duration = int(time.time() - start_time)
                    mins, secs = divmod(current_duration, 60)

                    # 构建状态信息
                    train_desc = train_status_mapping.get(train_status, f"未知({train_status})")
                    test_desc = test_status_mapping.get(test_status, f"未知({test_status})")
                    commit_desc = commit_status_mapping.get(commit_status, f"未知({commit_status})")

                    status_info = (f"{step_name}状态 | "
                                   f"训练: {train_desc} | "
                                   f"验证: {test_desc} | "
                                   f"提交: {commit_desc} | "
                                   f"耗时: {mins}分{secs}秒")

                    # 根据状态选择颜色
                    # 如果有任何失败状态，显示红色
                    if train_status == 5 or test_status == 2 or commit_status == 3:
                        color_code = "\033[91m"  # 红色
                    # 如果所有需要检查的状态都成功，显示绿色
                    elif ((success_train_status is None or train_status == success_train_status) and
                          (success_test_status is None or test_status == success_test_status) and
                          (success_commit_status is None or commit_status == success_commit_status)):
                        color_code = "\033[92m"  # 绿色
                    # 如果有任何"中"状态，显示黄色
                    elif train_status in [1, 2, 3] or test_status in [1] or commit_status in [1]:
                        color_code = "\033[93m"  # 黄色
                    else:
                        color_code = "\033[0m"  # 默认颜色

                    # 输出状态信息
                    print(f"\r{color_code}{status_info}\033[0m", end="", flush=True)

                    # 状态判断 - 检查是否所有需要检查的状态都达到成功状态
                    train_success = success_train_status is None or train_status == success_train_status
                    test_success = success_test_status is None or test_status == success_test_status
                    commit_success = success_commit_status is None or commit_status == success_commit_status

                    if train_success and test_success and commit_success:
                        print(f"\n", flush=True)
                        return True

                    # 检查失败状态
                    if train_status == 5:  # 训练失败
                        pytest.fail(f"{step_name}失败: 训练失败")
                    elif test_status == 2:  # 验证失败
                        pytest.fail(f"{step_name}失败: 验证失败")
                    elif commit_status == 3:  # 提交失败
                        pytest.fail(f"{step_name}失败: 提交失败")

                    # 检查未知状态
                    if train_status not in [1, 2, 3, 4, 5]:
                        pytest.fail(f"{step_name}遇到未知训练状态: {train_status}")
                    if test_status not in [0, 1, 2, 3]:
                        pytest.fail(f"{step_name}遇到未知验证状态: {test_status}")
                    if commit_status not in [0, 1, 2, 3]:
                        pytest.fail(f"{step_name}遇到未知提交状态: {commit_status}")

                    # 超时检查
                    elapsed = time.time() - start_time
                    if elapsed > self.max_wait_seconds:
                        pytest.fail(f"{step_name}超时: 等待{self.max_wait_seconds}秒未完成")

                    # 间隔等待
                    time.sleep(self.poll_interval)

    @allure.story("EIIR模型训练&提交")
    def test_eiir_task_workflow(self):
        total_start = time.time()  # 记录总开始时间

        with allure.step("步骤1：创建EIIR训练任务"):
            allure.attach(
                f"任务名称: {TestEiirModelTraining.task_name}\n"
                f"开始时间: {start_time}\n"
                f"结束时间: {end_time}\n"
                f"机器ID: {machineId}\n"
                f"组件标签: {componentLabel}",
                name="创建任务参数",
                attachment_type=allure.attachment_type.TEXT
            )

            response = self.api_eiir_samples.create_train_task(TestEiirModelTraining.task_name, start_time, end_time,
                                                               machineId, componentLabel)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            allure.attach(
                str(response_data),
                name="创建任务响应",
                attachment_type=allure.attachment_type.JSON
            )

        with allure.step("步骤2：监控创建数据处理进度"):
            self._monitor_eiir_data_progress(TestEiirModelTraining.task_name, "EIIR创建数据处理")

        with allure.step("步骤3：追加EIIR训练任务"):
            allure.attach(
                f"训练任务ID: {TestEiirModelTraining.trainTaskId}\n"
                f"开始时间: {start_time}\n"
                f"结束时间: {end_time}\n"
                f"机器ID: {machineId}\n"
                f"追加组件标签: {append_componentLabel}",
                name="追加任务参数",
                attachment_type=allure.attachment_type.TEXT
            )

            response = self.api_eiir_samples.append_train_task(TestEiirModelTraining.trainTaskId, start_time, end_time,
                                                               machineId, append_componentLabel)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            allure.attach(
                str(response_data),
                name="追加任务响应",
                attachment_type=allure.attachment_type.JSON
            )

        with allure.step("步骤4：监控追加数据处理进度"):
            self._monitor_eiir_data_progress(TestEiirModelTraining.task_name, "EIIR追加数据处理")

        with allure.step("步骤5：开始EIIR模型训练"):
            with allure.step("子步骤1：查询训练机器获取computingPowerId"):
                machine_response = self.api_model.query_machine()
                assertions.assert_code(machine_response.status_code, 200)
                machine_data = machine_response.json()
                assertions.assert_in_text(machine_data['msg'], '操作成功')

                # 查找指定的训练机器
                test_machine = next(
                    (machine for machine in machine_data['data'] if machine['name'] == machine_name),
                    None
                )
                if not test_machine:
                    pytest.fail(f"{machine_name}在机器列表中未找到")
                computing_power_id = test_machine['computingPowerId']

                allure.attach(
                    f"找到训练机器ID: {computing_power_id}",
                    name="训练机器ID",
                    attachment_type=allure.attachment_type.TEXT
                )
                machine_response = self.api_eiir_training.query_eiir_machine()
                assertions.assert_code(machine_response.status_code, 200)
                machine_data = machine_response.json()
                assertions.assert_in_text(machine_data['msg'], '操作成功')

            with allure.step("子步骤2：组装参数并开始EIIR模型训练"):
                allure.attach(
                    f"训练机器ID: {computing_power_id}\n"
                    f"训练任务ID: {TestEiirModelTraining.trainTaskId}",
                    name="模型训练参数",
                    attachment_type=allure.attachment_type.TEXT
                )

                train_response = self.api_eiir_training.create_train_task(computing_power_id,
                                                                          TestEiirModelTraining.trainTaskId)
                assertions.assert_code(train_response.status_code, 200)
                train_data = train_response.json()
                assertions.assert_in_text(train_data['msg'], '操作成功')

                allure.attach(
                    str(train_data),
                    name="开始训练响应",
                    attachment_type=allure.attachment_type.JSON
                )

        with allure.step("步骤6：监控EIIR模型训练进度"):
            self._monitor_eiir_train_progress(
                "EIIR模型训练",
                success_train_status=4,  # 训练完成
                success_test_status=3,  # 验证完成
                success_commit_status=None  # 不检查提交状态
            )
        with allure.step("步骤7：提交EIIR模型"):
            with allure.step("子步骤1：发起EIIR模型提交"):
                allure.attach(
                    f"训练任务名称: {TestEiirModelTraining.task_name}\n"
                    f"模型训练ID: {TestEiirModelTraining.modelTrainId}",
                    name="模型提交参数",
                    attachment_type=allure.attachment_type.TEXT
                )
                response = self.api_eiir_training.submit_eiir_model(TestEiirModelTraining.task_name,
                                                                    TestEiirModelTraining.modelTrainId)
                assertions.assert_code(response.status_code, 200)
                response_data = response.json()
                assertions.assert_in_text(response_data['msg'], '成功')

                allure.attach(
                    str(response_data),
                    name="模型提交响应",
                    attachment_type=allure.attachment_type.JSON
                )

            with allure.step("子步骤2：监控模型提交状态"):
                self._monitor_eiir_train_progress(
                    "EIIR模型提交",
                    success_train_status=None,
                    success_test_status=None,
                    success_commit_status=2
                )

        with allure.step("步骤8：查询目标检测模型库"):
            response = self.api_eiir_model.query_eiir_model()
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            # 从响应数据中提取modelManageId
            data_list = response_data.get('data', {}).get('list', [])
            target_model = None

            for model in data_list:
                if model.get('modelTrainId') == TestEiirModelTraining.modelTrainId:
                    target_model = model
                    break

            if target_model:
                self.__class__.modelManageId = target_model.get('modelManageId')
                allure.attach(
                    f"提取到modelManageId: {self.__class__.modelManageId}",
                    name="modelManageId提取",
                    attachment_type=allure.attachment_type.TEXT
                )
            else:
                pytest.fail(f"未找到modelTrainId为'{TestEiirModelTraining.modelTrainId}'的模型记录")

        with allure.step("步骤9：EIIR模型撤回"):
            allure.attach(
                f"模型管理ID: {TestEiirModelTraining.modelManageId}",
                name="撤回模型参数",
                attachment_type=allure.attachment_type.TEXT
            )
            response = self.api_eiir_model.rollback_eiir_model(TestEiirModelTraining.modelManageId)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            allure.attach(
                str(response_data),
                name="模型撤回响应",
                attachment_type=allure.attachment_type.JSON
            )

        with allure.step("步骤10：删除EIIR训练任务"):
            allure.attach(
                f"训练任务ID: {TestEiirModelTraining.trainTaskId}",
                name="删除任务参数",
                attachment_type=allure.attachment_type.TEXT
            )

            response = self.api_eiir_training.delete_eiir_task(TestEiirModelTraining.trainTaskId)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            allure.attach(
                str(response_data),
                name="删除任务响应",
                attachment_type=allure.attachment_type.JSON
            )

            # 总结信息
            total_duration = time.time() - total_start
            allure.attach(
                f"测试总耗时: {time.strftime('%H:%M:%S', time.gmtime(total_duration))}\n"
                f"任务名称: {TestEiirModelTraining.task_name}\n"
                f"训练任务ID: {TestEiirModelTraining.trainTaskId}\n"
                f"模型训练ID: {TestEiirModelTraining.modelTrainId}\n"
                f"模型管理ID: {TestEiirModelTraining.modelManageId}",
                name="测试总结",
                attachment_type=allure.attachment_type.TEXT
            )

        allure.dynamic.description(
            "EIIR模型训练测试完成！\n"
            f"总耗时: {time.strftime('%H:%M:%S', time.gmtime(time.time() - total_start))}"
        )
        print("\n\n\033[92mEIIR模型训练测试完成！\033[0m")
        print(f"总耗时: {time.strftime('%H:%M:%S', time.gmtime(time.time() - total_start))}")

        if __name__ == '__main__':
            pytest.main([__file__, '-v', '--alluredir=./allure-results'])
