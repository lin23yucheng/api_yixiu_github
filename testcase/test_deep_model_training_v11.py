"""
深度YoloV11模型训练接口自动化流程
"""
import pytest
import allure
import time
import os
import ast
import random
from configparser import ConfigParser
from common.Request_Response import ApiClient
from common import Assert
import configparser
from api import api_login, api_comprehensive_sample_library, api_deep_training_tasks, api_model_base
from common.monitor_utils import MonitorUtils

assertions = Assert.Assertions()
time_str = time.strftime("%Y%m%d%H%M%S", time.localtime())

# 初始化全局客户端
base_headers = {
    "Authorization": api_login.ApiLogin().login(),
    "Miai-Product-Code": api_login.code,
    "Miaispacemanageid": api_login.manageid
}
global_client = ApiClient(base_headers=base_headers)


@allure.feature("场景：综合-目标检测YoloV11训练全流程")
class TestDeepModelTraining:
    @classmethod
    def setup_class(cls):
        """初始化接口封装实例"""
        cls.api_comprehensive = api_comprehensive_sample_library.ApiComprehensiveSampleLibrary(global_client)
        cls.api_deep = api_deep_training_tasks.ApiDeepTrainTasks(global_client)
        cls.api_model = api_deep_training_tasks.ApiModelTrain(global_client)
        cls.api_process = api_deep_training_tasks.ApiPostProcess(global_client)
        cls.api_base = api_model_base.ApiModelBase(global_client)
        cls.task_name = f"接口自动化-{time_str}-目标检测V11"  # 统一任务名称格式
        cls.max_wait_seconds = 1800  # 最大等待30分钟
        cls.poll_interval = 10  # 轮询间隔10秒
        cls.start_timestamp = None  # 新增时间记录点
        cls.trainTaskId = None
        cls.modelTrainId = None
        cls.verifyId = None
        cls.modelManageId = None
        cls.monitor = MonitorUtils(api_deep=cls.api_deep, api_model=cls.api_model)
        # 读取配置文件
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'env_config.ini')
        config = configparser.ConfigParser()
        config.read(config_path, encoding='utf-8')

        # 获取当前环境并从对应环境节读取
        env = config.get("environment", "execution_env", fallback="").strip().lower()
        if env not in {"fat", "prod"}:
            raise ValueError(f"execution_env 配置错误: {env}，仅支持 fat 或 prod")

        env_section = f"{env}-yixiu"
        cls.defectName = ast.literal_eval(config.get(env_section, 'defect_name'))
        # 使用 ast.literal_eval 将字符串转换为列表
        cls.photoId_ng = ast.literal_eval(config.get(env_section, 'photo_id_ng'))
        cls.photoId_ok = ast.literal_eval(config.get(env_section, 'photo_id_ok'))
        cls.machine_name = config.get(env_section, 'machine_name')

    # 分析状态监控方法
    def _monitor_analysis_progress(self, analysis_type, api_call):
        """通用的状态监控方法"""
        start_time = time.time()
        attempt = 0
        last_status_info = ""  # 用于避免重复打印相同信息

        # 状态颜色映射
        color_mapping = {
            1: "\033[93m",  # 分析中 - 黄色
            2: "\033[92m",  # 分析完成 - 绿色
            "default": "\033[91m"  # 其他状态 - 红色
        }

        with allure.step(f"监控{analysis_type}状态"):
            while True:
                attempt += 1
                with allure.step(f"第{attempt}次状态检查"):
                    # 发送查询请求
                    response = api_call(self.verifyId)
                    assertions.assert_code(response.status_code, 200)

                    # 解析响应数据
                    response_data = response.json()
                    data = response_data.get('data')
                    if not isinstance(data, dict):
                        allure.attach(f"响应中data字段格式错误: {response_data}", name="错误详情")
                        pytest.fail("接口返回data字段格式不符合预期")

                    # 获取subStatus
                    subStatus = data.get('subStatus')

                    # 记录原始响应到Allure
                    allure.attach(
                        str(response_data),
                        name=f"{analysis_type}响应数据",
                        attachment_type=allure.attachment_type.JSON
                    )

                    # 时间统计
                    current_duration = int(time.time() - start_time)
                    mins, secs = divmod(current_duration, 60)

                    # 构建状态信息
                    status_text = "分析中" if subStatus == 1 else "分析完成" if subStatus == 2 else f"未知({subStatus})"
                    status_info = f"{analysis_type}状态: {status_text} | 耗时: {mins}分{secs}秒"

                    # 仅当状态信息变化时更新控制台（避免频繁刷新）
                    if status_info != last_status_info:
                        # 选择颜色
                        color_code = color_mapping.get(subStatus,
                                                       color_mapping["default"]) if subStatus is not None else \
                            color_mapping["default"]

                        # 单行更新（使用回车符覆盖上一行）
                        print(f"\r{color_code}{status_info}\033[0m", end="", flush=True)
                        last_status_info = status_info

                    # 状态判断
                    if subStatus == 2:
                        # 最终完成时换行
                        print(f"\n", flush=True)
                        return True
                    elif subStatus != 1:  # 非分析中状态
                        pytest.fail(f"未知状态码: {subStatus}")

                    # 超时检查（30分钟）
                    elapsed = time.time() - start_time
                    if elapsed > self.max_wait_seconds:
                        pytest.fail(f"{analysis_type}超时: 等待{self.max_wait_seconds}秒未完成")

                    # 间隔等待
                    time.sleep(self.poll_interval)

    # 模型库状态监控方法
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

    @allure.story("深度(目标检测)YoloV11模型训练&后处理&部署测试")
    def test_deep_task_workflow_v11(self):
        total_start = time.time()  # 记录总开始时间

        with allure.step("步骤1：创建深度训练任务"):
            self.cut_value = 1024
            response = self.api_comprehensive.create_deep_training_tasks(
                defectName=self.defectName,
                photoId=self.photoId_ng,
                cut=self.cut_value,
                taskName=self.task_name,
                classifyType=[],
                caseId="detection",
                caseName="目标检测/分割",
                create_type=1,
                iscut=True,
                remark="1024-YoloV11模型训练"
            )

            # 验证初始响应
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            # 记录任务信息
            allure.attach(
                f"任务名称: {self.task_name}",
                name="任务创建信息",
                attachment_type=allure.attachment_type.TEXT
            )
            self.creation_time = time.time()  # 记录任务创建完成时间

        with allure.step("步骤2：监控创建数据处理进度"):
            self.trainTaskId, success = self.monitor.monitor_cut_progress(
                self.task_name,
                "目标检测/分割切图处理"
            )
            self.__class__.trainTaskId = self.trainTaskId

        with allure.step("步骤3：追加ok图"):
            if not self.trainTaskId:
                pytest.fail("trainTaskId未被正确获取，请检查监控方法")
            response = self.api_comprehensive.append_deep_training_tasks2(
                photoId=self.photoId_ok,
                sampleType="ok",
                trainId=self.trainTaskId,
                datasetType=1
            )

            # 验证初始响应
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

        with allure.step("步骤4：监控追加数据处理进度"):
            self.trainTaskId, success = self.monitor.monitor_cut_progress(
                self.task_name,
                "目标检测/分割追加OK图处理"
            )
            self.__class__.trainTaskId = self.trainTaskId

        with allure.step("步骤5：开始目标检测YoloV11模型训练"):
            with allure.step("子步骤1：查询模型方案获取caseId"):
                model_response = self.api_model.query_model()
                assertions.assert_code(model_response.status_code, 200)
                model_data = model_response.json()
                assertions.assert_in_text(model_data['msg'], '操作成功')

                # 解析case映射关系
                cut_case_mapping = {
                    768: "实例分割",
                    1024: "目标检测"
                }
                if self.cut_value not in cut_case_mapping:
                    pytest.fail(f"无效的裁剪值: {self.cut_value}, 预期值为1024/768")
                target_case_name = cut_case_mapping[self.cut_value]

                # 查找匹配的模型数据
                matched_model = None
                case_id = None
                modelCaseTemplateId = None

                for model_item in model_data['data']:
                    # 查找name与目标case名称匹配的数据
                    if model_item.get('name') == target_case_name:
                        matched_model = model_item
                        break

                if not matched_model:
                    pytest.fail(f"模型 '{target_case_name}' 在响应中未找到")

                # 在匹配的模型中查找modelVersionList中caseName为"Det V4"的项
                model_version_list = matched_model.get('modelVersionList', [])
                for version in model_version_list:
                    if version.get('caseName') == "Det V4":
                        case_id = version.get('caseId')
                        modelCaseTemplateId = version.get('modelCaseTemplateId')
                        break

                if not case_id or not modelCaseTemplateId:
                    pytest.fail(f"在模型 '{target_case_name}' 中未找到caseName为'Det V4'的版本")

                allure.attach(
                    f"找到 caseId: {case_id}, modelCaseTemplateId: {modelCaseTemplateId} (cut={self.cut_value})",
                    name="模型案例",
                    attachment_type=allure.attachment_type.TEXT
                )

            with allure.step("子步骤2：查询训练机器获取computingPowerId"):
                machine_response = self.api_model.query_machine()
                assertions.assert_code(machine_response.status_code, 200)
                machine_data = machine_response.json()
                assertions.assert_in_text(machine_data['msg'], '操作成功')

                # 查找指定的训练机器
                test_machine = next(
                    (machine for machine in machine_data['data'] if machine['name'] == self.machine_name),
                    None
                )
                if not test_machine:
                    pytest.fail(f"{self.machine_name}在机器列表中未找到")
                computing_power_id = test_machine['computingPowerId']

                allure.attach(
                    f"找到训练机器ID: {computing_power_id}",
                    name="训练机器ID",
                    attachment_type=allure.attachment_type.TEXT
                )

            with allure.step("子步骤3：组装参数并开始YoloV11训练"):
                train_response = self.api_model.start_train("", "", case_id, -1, computing_power_id, 30, 16, 0.0002,
                                                            self.trainTaskId, modelCaseTemplateId)
                assertions.assert_code(train_response.status_code, 200)
                train_data = train_response.json()
                assertions.assert_in_text(train_data['msg'], '操作成功')

        with allure.step("步骤6：监控训练进度"):
            self.modelTrainId, success = self.monitor.monitor_train_progress(self.trainTaskId, "YoloV11目标检测训练")
            self.__class__.modelTrainId = self.modelTrainId
            time.sleep(3)

        with allure.step("步骤7：提交模型"):

            with allure.step("子步骤1：发起模型提交"):
                submit_response = self.api_model.submit_model(
                    modelName=self.task_name,
                    modelTrainId=self.modelTrainId
                )
                assertions.assert_code(submit_response.status_code, 200)
                submit_data = submit_response.json()
                assertions.assert_in_text(submit_data['msg'], '操作成功')

                allure.attach(
                    f"提交的模型名称: {self.task_name}",
                    name="模型提交信息",
                    attachment_type=allure.attachment_type.TEXT
                )

            with allure.step("子步骤2：监控模型提交状态"):
                success = self.monitor.monitor_commit_progress(self.trainTaskId, "YoloV11目标检测模型提交")

        with allure.step("步骤8：训练记录查询获取验证集的verifyId"):
            # 使用配置中的train_task_id发起请求
            response = self.api_model.query_train_records(
                trainTaskId=TestDeepModelTraining.trainTaskId
            )

            # 响应断言
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            # 提取验证集verify_id
            verify_id = None
            for task in response_data.get('data', {}).get('list', []):
                # 遍历verifyRecord查找包含'验证集'的条目
                for record in task.get('verifyRecord', []):
                    if '验证集' in record.get('name', ''):
                        verify_id = record.get('id')
                        self.__class__.verifyId = verify_id  # 关键：赋值给类变量
                        break
                if verify_id:
                    break

            # 提取taskName值
            train_list = response_data.get('data', {}).get('list', [])
            if not train_list:
                pytest.fail("未找到训练记录")

            first_sample = train_list[0]
            task_name = first_sample.get('taskName')
            self.__class__.task_name = task_name  # 关键：赋值给类变量

            # 确保找到有效ID
            assertions.assert_is_not_none(
                self.verifyId,
                f"未找到验证集verifyRecordID，响应数据：{response_data}"
            )

            allure.attach(
                f"验证集验证id: {self.verifyId}",
                name="验证集-verifyId",
                attachment_type=allure.attachment_type.TEXT
            )

        with allure.step("步骤9：报表分析"):
            with allure.step("子步骤1：提交报表分析"):
                response = self.api_process.report_analysis(
                    verifyId=self.verifyId
                )

                # 响应断言
                assertions.assert_code(response.status_code, 200)
                response_data = response.json()
                assertions.assert_in_text(response_data['msg'], '成功')

                allure.attach(
                    f"提交报表分析id: {self.verifyId}",
                    name="报表分析信息",
                    attachment_type=allure.attachment_type.TEXT
                )

            with allure.step("子步骤2：监控报表分析状态"):
                self._monitor_analysis_progress("报表分析", self.api_process.report_analysis_status)

        with allure.step("步骤10：样本分析"):
            with allure.step("子步骤1：提交样本分析"):
                response = self.api_process.sample_analysis(
                    verifyId=self.verifyId
                )

                # 响应断言
                assertions.assert_code(response.status_code, 200)
                response_data = response.json()
                assertions.assert_in_text(response_data['msg'], '成功')

                allure.attach(
                    f"提交样本分析id: {self.verifyId}",
                    name="样本分析信息",
                    attachment_type=allure.attachment_type.TEXT
                )

            with allure.step("子步骤2：监控样本分析状态"):
                self._monitor_analysis_progress("样本分析", self.api_process.sample_analysis_status)

        with allure.step("步骤11: 过检样本-拷贝增广"):
            with allure.step("子步骤1：查询过检样本"):
                # 调用query_over_samples方法查询过检样本
                response = self.api_process.query_over_samples(
                    verifyId=self.verifyId
                )

                # 响应断言
                assertions.assert_code(response.status_code, 200)
                response_data = response.json()
                assertions.assert_in_text(response_data['msg'], '成功')

                # 提取第一条记录的id和imgName
                over_samples_list = response_data.get('data', {}).get('list', [])
                if not over_samples_list:
                    pytest.fail("未找到过检样本数据")

                first_sample = over_samples_list[0]
                sample_id = first_sample.get('id')
                img_name = first_sample.get('imgName')

                # 断言提取的id和imgName不为空
                assertions.assert_is_not_none(sample_id, "过检样本id不能为空")
                assertions.assert_is_not_none(img_name, "过检样本imgName不能为空")

                # 记录日志到Allure报告
                allure.attach(
                    f"过检样本id: {sample_id}, imgName: {img_name}",
                    name="过检样本信息",
                    attachment_type=allure.attachment_type.TEXT
                )

                # 控制台打印
                print(f"过检样本id: {sample_id}, imgName: {img_name}")

            with allure.step("子步骤2：查询过检图片GT/PRE"):
                # 调用query_gt_pre_data方法查询图片GT/PRE数据
                response = self.api_process.query_gt_pre_data(
                    image_id=sample_id,
                    verifyId=self.verifyId
                )

                # 响应断言
                assertions.assert_code(response.status_code, 200)
                response_data = response.json()
                assertions.assert_in_text(response_data['msg'], '成功')

                # 提取GT和PRE数据
                gt_pre_data = response_data.get('data', {}).get('gtAndPre', {}).get('shapes', [])

                # 确保gt_pre_data是一个列表
                if not isinstance(gt_pre_data, list):
                    pytest.fail(f"gt_pre_data不是一个列表: {gt_pre_data}")

                # 找到type字段等于0的第一条数据的id
                defect_id = None
                for item in gt_pre_data:
                    if item.get('type') == "0":  # 注意引号
                        defect_id = item.get('id')
                        break

                # 断言提取的defect_id不为空
                assertions.assert_is_not_none(defect_id, "未找到type为0的缺陷ID")

                # 记录日志到Allure报告
                allure.attach(
                    f"缺陷ID: {defect_id}",
                    name="缺陷ID",
                    attachment_type=allure.attachment_type.TEXT
                )

            with allure.step("子步骤3：标记空过杀"):
                postprocess_label = "kongguosha"
                response = self.api_process.batch_mark(
                    defect_id=defect_id,
                    postprocess_label=postprocess_label,
                    verifyId=self.verifyId,
                    image_id=sample_id,
                    img_name=img_name
                )

                # 响应断言
                assertions.assert_code(response.status_code, 200)
                response_data = response.json()
                assertions.assert_in_text(response_data['msg'], '成功')

                # 记录日志到Allure报告
                allure.attach(
                    f"标记空过杀响应: {response_data}",
                    name="标记空过杀信息",
                    attachment_type=allure.attachment_type.JSON
                )

            with allure.step("子步骤4: 过检样本拷贝增广"):
                num = random.randint(1, 5)  # 随机选择1到5之间的数字
                response = self.api_process.copy_to_trainset(
                    train_task_id=self.trainTaskId,
                    num=num,
                    verifyId=self.verifyId,
                    image_id=sample_id,
                    copy_type=0
                )

                # 响应断言
                assertions.assert_code(response.status_code, 200)
                response_data = response.json()
                assertions.assert_in_text(response_data['msg'], '成功')

                # 记录日志到Allure报告
                allure.attach(
                    f"拷贝到训练集响应: {response_data}",
                    name="过检样本拷贝增广信息",
                    attachment_type=allure.attachment_type.JSON
                )

            with allure.step("子步骤5: 监控过检拷贝进度"):
                _, success = self.monitor.monitor_cut_progress(self.task_name, "过检样本-拷贝增广处理")

        with allure.step("步骤12: 漏检样本-拷贝增广"):
            with allure.step("子步骤1：查询漏检样本"):
                response = self.api_process.query_miss_samples(
                    verifyId=self.verifyId
                )

                # 响应断言
                assertions.assert_code(response.status_code, 200)
                response_data = response.json()
                assertions.assert_in_text(response_data['msg'], '成功')

                # 提取第一条记录的id和imgName
                over_samples_list = response_data.get('data', {}).get('list', [])
                if not over_samples_list:
                    pytest.fail("未找到漏检样本数据")

                first_sample = over_samples_list[0]
                sample_id = first_sample.get('id')
                img_name = first_sample.get('imgName')

                # 断言提取的id和imgName不为空
                assertions.assert_is_not_none(sample_id, "漏检样本id不能为空")
                assertions.assert_is_not_none(img_name, "漏检样本imgName不能为空")

                # 记录日志到Allure报告
                allure.attach(
                    f"漏检样本id: {sample_id}, imgName: {img_name}",
                    name="漏检样本信息",
                    attachment_type=allure.attachment_type.TEXT
                )

                # 控制台打印
                print(f"漏检样本id: {sample_id}, imgName: {img_name}")

            with allure.step("子步骤2：查询漏检图片GT/PRE"):
                response = self.api_process.query_gt_pre_data(
                    image_id=sample_id,
                    verifyId=self.verifyId
                )

                # 响应断言
                assertions.assert_code(response.status_code, 200)
                response_data = response.json()
                assertions.assert_in_text(response_data['msg'], '成功')

                # 提取GT和PRE数据
                gt_pre_data = response_data.get('data', {}).get('gtAndPre', {}).get('shapes', [])

                # 确保gt_pre_data是一个列表
                if not isinstance(gt_pre_data, list):
                    pytest.fail(f"gt_pre_data不是一个列表: {gt_pre_data}")

                # 找到type字段等于1的第一条数据的id
                defect_id = None
                for item in gt_pre_data:
                    if item.get('type') == "1":  # 注意引号
                        defect_id = item.get('id')
                        break

                # 断言提取的defect_id不为空
                assertions.assert_is_not_none(defect_id, "未找到type为1的缺陷ID")

                # 记录日志到Allure报告
                allure.attach(
                    f"缺陷ID: {defect_id}",
                    name="缺陷ID",
                    attachment_type=allure.attachment_type.TEXT
                )

                # 控制台打印
                # print(f"缺陷ID: {defect_id}")

            with allure.step("子步骤3：标记漏检增强"):
                postprocess_label = "loujianzengqiang"
                response = self.api_process.batch_mark(
                    defect_id=defect_id,
                    postprocess_label=postprocess_label,
                    verifyId=self.verifyId,
                    image_id=sample_id,
                    img_name=img_name
                )

                # 响应断言
                assertions.assert_code(response.status_code, 200)
                response_data = response.json()
                assertions.assert_in_text(response_data['msg'], '成功')

                # 记录日志到Allure报告
                allure.attach(
                    f"标记漏检增强响应: {response_data}",
                    name="标记漏检增强信息",
                    attachment_type=allure.attachment_type.JSON
                )

                # 控制台打印
                # print(f"标记漏检增强响应: {response_data}")

            with allure.step("子步骤4: 漏检样本拷贝增广"):
                num = random.randint(1, 5)  # 随机选择1到5之间的数字
                response = self.api_process.copy_to_trainset(
                    train_task_id=self.trainTaskId,
                    num=num,
                    verifyId=self.verifyId,
                    image_id=sample_id,
                    copy_type=1
                )

                # 响应断言
                assertions.assert_code(response.status_code, 200)
                response_data = response.json()
                assertions.assert_in_text(response_data['msg'], '成功')

                # 记录日志到Allure报告
                allure.attach(
                    f"拷贝到训练集响应: {response_data}",
                    name="漏检样本拷贝增广信息",
                    attachment_type=allure.attachment_type.JSON
                )

                # 控制台打印
                # print(f"漏检样本拷贝增广响应: {response_data}")

            with allure.step("子步骤5: 监控漏检拷贝进度"):
                _, success = self.monitor.monitor_cut_progress(self.task_name, "漏检样本-拷贝增广处理")

        with allure.step("步骤13: 错检样本-拷贝增广"):
            with allure.step("子步骤1：查询错检样本"):
                response = self.api_process.query_error_samples(
                    verifyId=self.verifyId
                )

                # 响应断言
                assertions.assert_code(response.status_code, 200)
                response_data = response.json()
                assertions.assert_in_text(response_data['msg'], '成功')

                # 提取第一条记录的id和imgName
                over_samples_list = response_data.get('data', {}).get('list', [])
                if not over_samples_list:
                    pytest.fail("未找到错检样本数据")

                first_sample = over_samples_list[0]
                sample_id = first_sample.get('id')
                img_name = first_sample.get('imgName')

                # 断言提取的id和imgName不为空
                assertions.assert_is_not_none(sample_id, "错检样本id不能为空")
                assertions.assert_is_not_none(img_name, "错检样本imgName不能为空")

                # 记录日志到Allure报告
                allure.attach(
                    f"错检样本id: {sample_id}, imgName: {img_name}",
                    name="错检样本信息",
                    attachment_type=allure.attachment_type.TEXT
                )

                # 控制台打印
                print(f"错检样本id: {sample_id}, imgName: {img_name}")

            with allure.step("子步骤2：查询错检图片GT/PRE"):
                response = self.api_process.query_gt_pre_data(
                    image_id=sample_id,
                    verifyId=self.verifyId
                )

                # 响应断言
                assertions.assert_code(response.status_code, 200)
                response_data = response.json()
                assertions.assert_in_text(response_data['msg'], '成功')

                # 提取GT和PRE数据
                gt_pre_data = response_data.get('data', {}).get('gtAndPre', {}).get('shapes', [])

                # 确保gt_pre_data是一个列表
                if not isinstance(gt_pre_data, list):
                    pytest.fail(f"gt_pre_data不是一个列表: {gt_pre_data}")

                # 找到type字段等于2的第一条数据的id
                defect_id = None
                for item in gt_pre_data:
                    if item.get('type') == "2":  # 注意引号
                        defect_id = item.get('id')
                        break

                # 断言提取的defect_id不为空
                assertions.assert_is_not_none(defect_id, "未找到type为2的缺陷ID")

                # 记录日志到Allure报告
                allure.attach(
                    f"缺陷ID: {defect_id}",
                    name="缺陷ID",
                    attachment_type=allure.attachment_type.TEXT
                )

                # 控制台打印
                # print(f"缺陷ID: {defect_id}")

            with allure.step("子步骤3：标记错检增强"):
                postprocess_label = "cuojianzengqiang"
                response = self.api_process.batch_mark(
                    defect_id=defect_id,
                    postprocess_label=postprocess_label,
                    verifyId=self.verifyId,
                    image_id=sample_id,
                    img_name=img_name
                )

                # 响应断言
                assertions.assert_code(response.status_code, 200)
                response_data = response.json()
                assertions.assert_in_text(response_data['msg'], '成功')

                # 记录日志到Allure报告
                allure.attach(
                    f"标记错检增强响应: {response_data}",
                    name="标记错检增强信息",
                    attachment_type=allure.attachment_type.JSON
                )

                # 控制台打印
                # print(f"标记错检增强响应: {response_data}")

            with allure.step("子步骤4: 错检样本拷贝增广"):
                num = random.randint(1, 5)
                response = self.api_process.copy_to_trainset(
                    train_task_id=self.trainTaskId,
                    num=num,
                    verifyId=self.verifyId,
                    image_id=sample_id,
                    copy_type=2
                )

                # 响应断言
                assertions.assert_code(response.status_code, 200)
                response_data = response.json()
                assertions.assert_in_text(response_data['msg'], '成功')

                # 记录日志到Allure报告
                allure.attach(
                    f"拷贝到训练集响应: {response_data}",
                    name="错检样本拷贝增广信息",
                    attachment_type=allure.attachment_type.JSON
                )

                # 控制台打印
                # print(f"错检样本拷贝增广响应: {response_data}")

            with allure.step("子步骤5: 监控错检拷贝进度"):
                _, success = self.monitor.monitor_cut_progress(self.task_name, "错检样本-拷贝增广处理")

        with allure.step("步骤14：通过modelTrainId获取modelManageId"):
            self.__class__.modelManageId = self._get_model_manage_id(
                model_train_id=self.__class__.modelTrainId
            )
            allure.attach(
                f"modelManageId: {self.modelManageId}",
                name="目标检测模型ManageID",
                attachment_type=allure.attachment_type.TEXT
            )

        with allure.step("步骤15：部署测试"):
            response = self.api_base.deploy_test(self.__class__.modelManageId)

            # 响应断言
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

        with allure.step("步骤16：监控部署测试状态"):
            # 定义状态提取函数
            def get_deployment_status(response_data):
                model_list = response_data.get('data', {}).get('list', [])
                for model in model_list:
                    if model.get('modelManageId') == self.__class__.modelManageId:
                        return model.get('status')
                return None

            # 调用监控方法
            self._monitor_generic_progress(
                api_call=self.api_base.query_model_base,
                get_status_func=get_deployment_status,
                in_progress_status=1,  # 测试中
                success_status=3,  # 测试完成
                step_name="部署测试",
                status_mapping={
                    0: "已提交",
                    1: "测试中",
                    2: "测试失败",
                    3: "测试完成"
                }
            )

        with allure.step("步骤17：目标检测Yolov11模型撤回"):
            response = self.api_base.model_withdraw(self.modelManageId, 1)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

        with allure.step("步骤18：目标检测训练任务删除"):
            response = self.api_deep.delete_train_tasks(TestDeepModelTraining.trainTaskId)

            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

        allure.dynamic.description(
            "深度（目标检测）Yolov11模型训练&后处理&部署测试完成！\n"
            f"总耗时: {time.strftime('%H:%M:%S', time.gmtime(time.time() - total_start))}"
        )
        print("\n\n\033[92m深度（目标检测）-自动化Yolov11模型训练&后处理&部署测试完成！\033[0m")
        print(f"总耗时: {time.strftime('%H:%M:%S', time.gmtime(time.time() - total_start))}")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--alluredir=./allure-results'])
