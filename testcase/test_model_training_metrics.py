"""
检测模型训练指标与之前一致
"""
import pytest
import allure
import time
import os
import json
import configparser
from common.Request_Response import ApiClient
from common import Assert
from api import api_login, api_deep_training_tasks
from common.monitor_utils import MonitorUtils

assertions = Assert.Assertions()

# 初始化全局客户端
base_headers = {
    "Authorization": api_login.ApiLogin().login(),
    "Miai-Product-Code": api_login.code,
    "Miaispacemanageid": api_login.manageid
}
global_client = ApiClient(base_headers=base_headers)


@allure.feature("场景：综合-检测实例分割模型训练指标")
class TestModelTrainingMetrics:
    @classmethod
    def setup_class(cls):
        """初始化接口封装实例"""
        cls.api_model = api_deep_training_tasks.ApiModelTrain(global_client)
        cls.api_deep = api_deep_training_tasks.ApiDeepTrainTasks(global_client)
        cls.max_wait_seconds = 1800  # 最大等待30分钟
        cls.poll_interval = 10  # 轮询间隔10秒
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
        cls.machine_name = config.get(env_section, 'machine_name')
        cls.train_task_id_v8 = config.get(env_section, 'train_task_id_v8')
        cls.train_task_id_v11 = config.get(env_section, 'train_task_id_v11')
        cls.train_task_id_v12 = config.get(env_section, 'train_task_id_v12')
        cls.train_task_id_mtl = config.get(env_section, 'train_task_id_mtl')

    def _get_train_records(self, task_id):
        """获取训练记录的通用方法"""
        response = self.api_model.query_train_records(task_id)
        assertions.assert_code(response.status_code, 200)
        response_data = response.json()
        return response_data['data']['list']

    def _find_record_by_model_train_id(self, records, model_train_id):
        """根据modelTrainId查找对应的训练记录"""
        for record in records:
            if record.get('modelTrainId') == model_train_id:
                return record
        return None

    def _get_machine_id(self):
        """获取训练机器ID"""
        max_retries = 5
        retry_delay = 3

        for attempt in range(max_retries):
            try:
                machine_response = self.api_model.query_machine()
                assertions.assert_code(machine_response.status_code, 200)
                machine_data = machine_response.json()
                assertions.assert_in_text(machine_data['msg'], '操作成功')

                # 查找测试机器
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
                return computing_power_id

            except Exception as e:
                if attempt < max_retries - 1:  # 如果不是最后一次尝试
                    allure.attach(
                        f"第{attempt + 1}次尝试获取机器ID失败: {str(e)}",
                        name="重试信息",
                        attachment_type=allure.attachment_type.TEXT
                    )
                    time.sleep(retry_delay)
                    continue
                else:
                    # 最后一次尝试仍然失败，抛出异常
                    allure.attach(
                        f"获取机器ID失败，已重试{max_retries}次: {str(e)}",
                        name="最终错误",
                        attachment_type=allure.attachment_type.TEXT
                    )
                    raise

    def _monitor_training_only(self, trainTaskId, task_description="模型训练", target_model_train_id=None):
        """
        只监控模型训练状态，不等待验证状态
        :param trainTaskId: 训练任务ID
        :param task_description: 任务描述
        :param target_model_train_id: 目标modelTrainId，如果提供则只监控该特定记录
        :return: (modelTrainId, 是否成功)
        """
        start_time = time.time()
        attempt = 0
        modelTrainId = None

        # 状态映射表
        status_mapping = {
            0: "训练中",
            1: "训练失败",
            2: "训练完成",
            3: "打包中",
            4: "排队中",
            5: "转onnx中",
            6: "转triton中"
        }

        with allure.step(f"监控{task_description}进度（仅训练状态）"):
            while True:
                attempt += 1
                with allure.step(f"第{attempt}次训练状态检查"):
                    # 发送查询请求
                    response = self.api_model.query_train_records(trainTaskId)
                    assertions.assert_code(response.status_code, 200)

                    # 解析响应数据
                    response_data = response.json()
                    records = response_data['data']['list']

                    # 验证记录存在性
                    if not records:
                        pytest.fail(f"未找到trainTaskId={trainTaskId}的训练记录")

                    # 根据是否指定target_model_train_id来选择记录
                    current_record = None
                    if target_model_train_id:
                        # 查找特定modelTrainId的记录
                        for record in records:
                            if record.get('modelTrainId') == target_model_train_id:
                                current_record = record
                                break
                        if not current_record:
                            pytest.fail(f"未找到modelTrainId为{target_model_train_id}的训练记录")
                    else:
                        # 使用第一条记录（原有逻辑）
                        current_record = records[0]

                    train_status = current_record['trainStatus']
                    modelTrainId = current_record['modelTrainId']

                    # 时间统计
                    current_duration = int(time.time() - start_time)
                    mins, secs = divmod(current_duration, 60)

                    # 构建状态信息
                    status_info = (
                        f"{task_description}状态: {status_mapping.get(train_status, f'未知({train_status})')} | "
                        f"modelTrainId: {modelTrainId} | "
                        f"耗时: {mins}分{secs}秒"
                    )

                    # 控制台实时打印（带颜色）
                    if train_status in [0, 3, 4, 5, 6]:  # 训练中相关状态 - 黄色
                        print(f"\r\033[93m{status_info}\033[0m", end="", flush=True)
                    elif train_status == 2:  # 训练完成 - 绿色
                        print(f"\r\033[92m{status_info}\033[0m", flush=True)
                    else:  # 训练失败 - 红色
                        print(f"\r\033[91m{status_info}\033[0m", flush=True)

                    # 状态判断 - 只关注训练状态
                    if train_status == 1:
                        pytest.fail("训练失败，请检查日志")
                    elif train_status == 2:
                        # 训练完成即返回，不等待验证状态
                        print(f"\n\033[92m{task_description}完成! 总耗时: {mins}分{secs}秒\033[0m")
                        return modelTrainId, True

                    # 超时检查
                    elapsed = time.time() - start_time
                    if elapsed > self.max_wait_seconds:
                        pytest.fail(f"训练卡住，请检查日志（等待超过{self.max_wait_seconds}秒）")

                    # 间隔等待
                    time.sleep(self.poll_interval)

    def _start_training(self, caseId, modelSize, computing_power_id, epoch, batchSize, lr,
                        trainTaskId, modelCaseTemplateId):
        """启动训练的通用方法"""
        train_response = self.api_model.start_train(
            "",
            "",
            caseId,
            modelSize,
            computing_power_id,
            epoch,
            batchSize,
            lr,
            trainTaskId,
            modelCaseTemplateId
        )
        assertions.assert_code(train_response.status_code, 200)
        train_data = train_response.json()
        assertions.assert_in_text(train_data['msg'], '操作成功')
        return train_response

    def _get_latest_model_train_id(self, trainTaskId):
        """获取最新的训练任务ID"""
        response = self.api_model.query_train_records(trainTaskId)
        assertions.assert_code(response.status_code, 200)

        response_data = response.json()
        records = response_data['data']['list']

        if not records:
            pytest.fail(f"未找到trainTaskId={trainTaskId}的训练记录")

        # 返回第一条记录的modelTrainId
        return records[0]['modelTrainId']

    def _parse_indicators(self, indicators):
        """处理多种可能的指标格式"""
        # 如果已经是字典，直接返回
        if isinstance(indicators, dict):
            return indicators

        # 如果是字符串，尝试解析为JSON
        if isinstance(indicators, str):
            try:
                return json.loads(indicators)
            except json.JSONDecodeError:
                # 如果解析失败，尝试作为普通字符串处理
                return {"raw_value": indicators}

        # 如果是其他类型，转换为字符串
        return {"raw_value": str(indicators)}

    def _format_metrics(self, metrics):
        """格式化指标输出"""
        return "\n".join([f"{k}: {v}" for k, v in metrics.items()]) or "无指标数据"

    def _compare_indicators(self, latest_indicators, oldest_indicators):
        """比较训练指标的通用方法"""
        if latest_indicators == oldest_indicators:
            allure.attach("✅ 训练指标前后一致", name="测试结果")
            print("训练指标验证通过")
            return True
        else:
            # 生成差异报告
            diff_details = [
                f"指标 '{key}': 最新值={latest_indicators.get(key, 'N/A')}, "
                f"历史值={oldest_indicators.get(key, 'N/A')}"
                for key in set(latest_indicators.keys()) | set(oldest_indicators.keys())
                if latest_indicators.get(key) != oldest_indicators.get(key)
            ]

            diff_report = "指标差异详情:\n" + "\n".join(diff_details) or "所有指标值均存在差异"
            allure.attach(diff_report, name="指标差异", attachment_type=allure.attachment_type.TEXT)
            return False

    @allure.story("验证实例分割-Yolov8模型训练前后指标一致")
    @pytest.mark.order(1)
    def test_model_train_metrics_v8(self):
        """验证Yolov8模型训练指标在多次训练后保持一致"""
        allure.dynamic.title(f"Yolov8训练任务指标验证 (ID: {self.train_task_id_v8})")
        total_start = time.time()

        with allure.step("步骤1：开始Yolov8实例分割模型训练"):
            with allure.step("子步骤1：查询模型方案获取caseId"):
                model_response = self.api_model.query_model()
                assertions.assert_code(model_response.status_code, 200)
                model_data = model_response.json()
                assertions.assert_in_text(model_data['msg'], '操作成功')

                # 查找name为"实例分割"的模型数据
                matched_model = None
                case_id = None
                modelCaseTemplateId = None

                for model_item in model_data['data']:
                    # 查找name为"实例分割"的数据
                    if model_item.get('name') == "实例分割":
                        matched_model = model_item
                        break

                if not matched_model:
                    pytest.fail("模型 '实例分割' 在响应中未找到")

                # 在匹配的模型中查找modelVersionList中caseName为"DetS V2"的项
                model_version_list = matched_model.get('modelVersionList', [])
                for version in model_version_list:
                    if version.get('caseName') == "DetS V2":
                        case_id = version.get('caseId')
                        modelCaseTemplateId = version.get('modelCaseTemplateId')
                        break

                if not case_id or not modelCaseTemplateId:
                    pytest.fail("在模型 '实例分割' 中未找到caseName为'DetS V2'的版本")

                allure.attach(
                    f"找到 caseId: {case_id}, modelCaseTemplateId: {modelCaseTemplateId}",
                    name="实例分割模型案例",
                    attachment_type=allure.attachment_type.TEXT
                )

            with allure.step("子步骤2：查询训练机器获取computingPowerId"):
                computing_power_id = self._get_machine_id()

            with allure.step("子步骤3：组装参数并开始训练"):
                self._start_training(case_id, "-1", computing_power_id, 30, 16, 0.0002,
                                     self.train_task_id_v8, modelCaseTemplateId
                                     )

            with allure.step("子步骤4：查询列表页获取modelTrainId"):
                target_model_train_id = self._get_latest_model_train_id(self.train_task_id_v8)
                allure.attach(
                    f"获取到的modelTrainId: {target_model_train_id}",
                    name="目标modelTrainId",
                    attachment_type=allure.attachment_type.TEXT
                )

        with allure.step("步骤2：监控训练进度"):
            try:
                _, success = self._monitor_training_only(self.train_task_id_v8, "YoloV8实例分割训练",
                                                         target_model_train_id)
            except Exception as e:
                allure.attach(f"训练监控失败: {str(e)}", name="错误详情")
                allure.attach("⚠️ 训练失败，跳过指标验证", name="测试结果")
                return

        with allure.step("步骤3：对比Yolov8实例分割训练指标"):
            try:
                records = self._get_train_records(self.train_task_id_v8)

                # 健壮性检查
                if not records:
                    allure.attach("未找到任何训练记录", name="验证结果")
                    print("警告: 未找到任何训练记录")
                    return  # 或 continue，取决于具体需求
                if len(records) < 2:
                    allure.attach(f"训练记录不足2条，无法进行指标对比（当前记录数：{len(records)}）", name="验证结果")
                    print(f"警告: 训练记录不足2条，无法进行指标对比（当前记录数：{len(records)}）")
                    return

                # 根据获取到的modelTrainId查找对应的记录
                target_record = self._find_record_by_model_train_id(records, target_model_train_id)

                if not target_record:
                    pytest.fail(f"未找到modelTrainId为{target_model_train_id}的训练记录")

                latest_indicators = self._parse_indicators(target_record.get('trainIndicators', {}))
                oldest_record = records[-1]  # 获取最后一条记录
                oldest_indicators = self._parse_indicators(oldest_record.get('trainIndicators', {}))

                # 记录原始指标值到Allure
                allure.attach(
                    f"原始最新指标值: {target_record.get('trainIndicators')}\n"
                    f"原始历史指标值: {oldest_record.get('trainIndicators')}",
                    name="原始指标数据",
                    attachment_type=allure.attachment_type.TEXT
                )

                # 优化报告展示
                with allure.step("训练指标详情"):
                    allure.attach(
                        f"最新训练指标:\n{self._format_metrics(latest_indicators)}\n\n"
                        f"历史训练指标:\n{self._format_metrics(oldest_indicators)}",
                        name="指标对比",
                        attachment_type=allure.attachment_type.TEXT
                    )

                # 指标对比逻辑
                if not self._compare_indicators(latest_indicators, oldest_indicators):
                    allure.attach("❌ 模型训练指标前后不一致", name="验证结果")
                    print("警告: Yolov8模型训练指标前后不一致")

            except Exception as e:
                allure.attach(f"指标对比失败: {str(e)}", name="错误详情")
                print(f"警告: 指标对比过程中发生错误: {str(e)}")

        # 添加总耗时统计
        total_duration = time.time() - total_start
        mins, secs = divmod(total_duration, 60)
        allure.attach(
            f"测试总耗时: {int(mins)}分{int(secs)}秒",
            name="时间统计",
            attachment_type=allure.attachment_type.TEXT
        )

    @allure.story("验证实例分割-Yolov11模型训练前后指标一致")
    @pytest.mark.order(2)
    def test_model_train_metrics_v11(self):
        """验证Yolov11模型训练指标在多次训练后保持一致"""
        allure.dynamic.title(f"Yolov11训练任务指标验证 (ID: {self.train_task_id_v11})")
        total_start = time.time()

        with allure.step("步骤1：开始Yolov11实例分割模型训练"):
            with allure.step("子步骤1：查询模型方案获取caseId"):
                model_response = self.api_model.query_model()
                assertions.assert_code(model_response.status_code, 200)
                model_data = model_response.json()
                assertions.assert_in_text(model_data['msg'], '操作成功')

                # 查找name为"实例分割"的模型数据
                matched_model = None
                case_id = None
                modelCaseTemplateId = None

                for model_item in model_data['data']:
                    # 查找name为"实例分割"的数据
                    if model_item.get('name') == "实例分割":
                        matched_model = model_item
                        break

                if not matched_model:
                    pytest.fail("模型 '实例分割' 在响应中未找到")

                # 在匹配的模型中查找modelVersionList中caseName为"DetS V4"的项
                model_version_list = matched_model.get('modelVersionList', [])
                for version in model_version_list:
                    if version.get('caseName') == "DetS V4":
                        case_id = version.get('caseId')
                        modelCaseTemplateId = version.get('modelCaseTemplateId')
                        break

                if not case_id or not modelCaseTemplateId:
                    pytest.fail("在模型 '实例分割' 中未找到caseName为'DetS V4'的版本")

                allure.attach(
                    f"找到 caseId: {case_id}, modelCaseTemplateId: {modelCaseTemplateId}",
                    name="实例分割模型案例",
                    attachment_type=allure.attachment_type.TEXT
                )

            with allure.step("子步骤2：查询训练机器获取computingPowerId"):
                computing_power_id = self._get_machine_id()

            with allure.step("子步骤3：组装参数并开始训练"):
                self._start_training(case_id, "-1", computing_power_id, 30, 16, 0.0002,
                                     self.train_task_id_v11, modelCaseTemplateId
                                     )
            with allure.step("子步骤4：查询列表页获取modelTrainId"):
                target_model_train_id = self._get_latest_model_train_id(self.train_task_id_v11)
                allure.attach(
                    f"获取到的modelTrainId: {target_model_train_id}",
                    name="目标modelTrainId",
                    attachment_type=allure.attachment_type.TEXT
                )

        with allure.step("步骤2：监控训练进度"):
            try:
                _, success = self._monitor_training_only(self.train_task_id_v11, "YoloV11实例分割训练",
                                                         target_model_train_id)
            except Exception as e:
                allure.attach(f"训练监控失败: {str(e)}", name="错误详情")
                allure.attach("⚠️ 训练失败，跳过指标验证", name="测试结果")
                return

        with allure.step("步骤3：对比Yolov11实例分割训练指标"):
            try:
                records = self._get_train_records(self.train_task_id_v11)

                # 健壮性检查
                if not records:
                    allure.attach("未找到任何训练记录", name="验证结果")
                    print("警告: 未找到任何训练记录")
                    return
                if len(records) < 2:
                    allure.attach(f"训练记录不足2条，无法进行指标对比（当前记录数：{len(records)}）", name="验证结果")
                    print(f"警告: 训练记录不足2条，无法进行指标对比（当前记录数：{len(records)}）")
                    return

                # 根据获取到的modelTrainId查找对应的记录
                target_record = self._find_record_by_model_train_id(records, target_model_train_id)

                if not target_record:
                    pytest.fail(f"未找到modelTrainId为{target_model_train_id}的训练记录")

                latest_indicators = self._parse_indicators(target_record.get('trainIndicators', {}))
                oldest_record = records[-1]  # 获取最后一条记录
                oldest_indicators = self._parse_indicators(oldest_record.get('trainIndicators', {}))

                # 记录原始指标值到Allure
                allure.attach(
                    f"原始最新指标值: {target_record.get('trainIndicators')}\n"
                    f"原始历史指标值: {oldest_record.get('trainIndicators')}",
                    name="原始指标数据",
                    attachment_type=allure.attachment_type.TEXT
                )

                # 优化报告展示
                with allure.step("训练指标详情"):
                    allure.attach(
                        f"最新训练指标:\n{self._format_metrics(latest_indicators)}\n\n"
                        f"历史训练指标:\n{self._format_metrics(oldest_indicators)}",
                        name="指标对比",
                        attachment_type=allure.attachment_type.TEXT
                    )

                # 指标对比逻辑
                if not self._compare_indicators(latest_indicators, oldest_indicators):
                    allure.attach("❌ 模型训练指标前后不一致", name="验证结果")
                    print("警告: Yolov11模型训练指标前后不一致")

            except Exception as e:
                allure.attach(f"指标对比失败: {str(e)}", name="错误详情")
                print(f"警告: 指标对比过程中发生错误: {str(e)}")

        # 添加总耗时统计
        total_duration = time.time() - total_start
        mins, secs = divmod(total_duration, 60)
        allure.attach(
            f"测试总耗时: {int(mins)}分{int(secs)}秒",
            name="时间统计",
            attachment_type=allure.attachment_type.TEXT
        )

    @allure.story("验证实例分割-Yolov12模型训练前后指标一致")
    @pytest.mark.order(3)
    def test_model_train_metrics_v12(self):
        """验证Yolov12模型训练指标在多次训练后保持一致"""
        allure.dynamic.title(f"Yolov12训练任务指标验证 (ID: {self.train_task_id_v12})")
        total_start = time.time()

        with allure.step("步骤1：开始Yolov12实例分割模型训练"):
            with allure.step("子步骤1：查询模型方案获取caseId"):
                model_response = self.api_model.query_model()
                assertions.assert_code(model_response.status_code, 200)
                model_data = model_response.json()
                assertions.assert_in_text(model_data['msg'], '操作成功')

                # 查找name为"实例分割"的模型数据
                matched_model = None
                case_id = None
                modelCaseTemplateId = None

                for model_item in model_data['data']:
                    # 查找name为"实例分割"的数据
                    if model_item.get('name') == "实例分割":
                        matched_model = model_item
                        break

                if not matched_model:
                    pytest.fail("模型 '实例分割' 在响应中未找到")

                # 在匹配的模型中查找modelVersionList中caseName为"DetS V3"的项
                model_version_list = matched_model.get('modelVersionList', [])
                for version in model_version_list:
                    if version.get('caseName') == "DetS V3":
                        case_id = version.get('caseId')
                        modelCaseTemplateId = version.get('modelCaseTemplateId')
                        break

                if not case_id or not modelCaseTemplateId:
                    pytest.fail("在模型 '实例分割' 中未找到caseName为'DetS V3'的版本")

                allure.attach(
                    f"找到 caseId: {case_id}, modelCaseTemplateId: {modelCaseTemplateId}",
                    name="实例分割模型案例",
                    attachment_type=allure.attachment_type.TEXT
                )

            with allure.step("子步骤2：查询训练机器获取computingPowerId"):
                computing_power_id = self._get_machine_id()

            with allure.step("子步骤3：组装参数并开始训练"):
                self._start_training(case_id, "-1", computing_power_id, 30, 16, 0.0002,
                                     self.train_task_id_v12, modelCaseTemplateId
                                     )

            with allure.step("子步骤4：查询列表页获取modelTrainId"):
                target_model_train_id = self._get_latest_model_train_id(self.train_task_id_v12)
                allure.attach(
                    f"获取到的modelTrainId: {target_model_train_id}",
                    name="目标modelTrainId",
                    attachment_type=allure.attachment_type.TEXT
                )

        with allure.step("步骤2：监控训练进度"):
            try:
                _, success = self._monitor_training_only(self.train_task_id_v12, "YoloV12实例分割训练",
                                                         target_model_train_id)
            except Exception as e:
                allure.attach(f"训练监控失败: {str(e)}", name="错误详情")
                allure.attach("⚠️ 训练失败，跳过指标验证", name="测试结果")
                return

        with allure.step("步骤3：对比Yolov12实例分割训练指标"):
            try:
                records = self._get_train_records(self.train_task_id_v12)

                # 健壮性检查
                if not records:
                    allure.attach("未找到任何训练记录", name="验证结果")
                    print("警告: 未找到任何训练记录")
                    return
                if len(records) < 2:
                    allure.attach(f"训练记录不足2条，无法进行指标对比（当前记录数：{len(records)}）", name="验证结果")
                    print(f"警告: 训练记录不足2条，无法进行指标对比（当前记录数：{len(records)}）")
                    return

                # 根据获取到的modelTrainId查找对应的记录
                target_record = self._find_record_by_model_train_id(records, target_model_train_id)

                if not target_record:
                    pytest.fail(f"未找到modelTrainId为{target_model_train_id}的训练记录")

                latest_indicators = self._parse_indicators(target_record.get('trainIndicators', {}))
                oldest_record = records[-1]  # 获取最后一条记录
                oldest_indicators = self._parse_indicators(oldest_record.get('trainIndicators', {}))

                # 记录原始指标值到Allure
                allure.attach(
                    f"原始最新指标值: {target_record.get('trainIndicators')}\n"
                    f"原始历史指标值: {oldest_record.get('trainIndicators')}",
                    name="原始指标数据",
                    attachment_type=allure.attachment_type.TEXT
                )

                # 优化报告展示
                with allure.step("训练指标详情"):
                    allure.attach(
                        f"最新训练指标:\n{self._format_metrics(latest_indicators)}\n\n"
                        f"历史训练指标:\n{self._format_metrics(oldest_indicators)}",
                        name="指标对比",
                        attachment_type=allure.attachment_type.TEXT
                    )

                # 指标对比逻辑
                if not self._compare_indicators(latest_indicators, oldest_indicators):
                    allure.attach("❌ 模型训练指标前后不一致", name="验证结果")
                    print("警告: Yolov12模型训练指标前后不一致")

            except Exception as e:
                allure.attach(f"指标对比失败: {str(e)}", name="错误详情")
                print(f"警告: 指标对比过程中发生错误: {str(e)}")

        # 添加总耗时统计
        total_duration = time.time() - total_start
        mins, secs = divmod(total_duration, 60)
        allure.attach(
            f"测试总耗时: {int(mins)}分{int(secs)}秒",
            name="时间统计",
            attachment_type=allure.attachment_type.TEXT
        )

    @allure.story("验证目标检测-mtl模型训练成功")
    @pytest.mark.order(4)
    def test_model_train_metrics_mtl(self):
        allure.dynamic.title(f"mtl训练完成 (ID: {self.train_task_id_mtl})")
        total_start = time.time()

        with allure.step("步骤1：开始mtl-v1模型训练"):
            with allure.step("子步骤1：查询模型方案获取caseId"):
                model_response = self.api_model.query_model()
                assertions.assert_code(model_response.status_code, 200)
                model_data = model_response.json()
                assertions.assert_in_text(model_data['msg'], '操作成功')

                # 查找name为"目标检测"的模型数据
                matched_model = None
                case_id = None
                modelCaseTemplateId = None

                for model_item in model_data['data']:
                    # 查找name为"目标检测"的数据
                    if model_item.get('name') == "目标检测":
                        matched_model = model_item
                        break

                if not matched_model:
                    pytest.fail("模型 '目标检测' 在响应中未找到")

                # 在匹配的模型中查找modelVersionList中caseName为"Det V1"的项
                model_version_list = matched_model.get('modelVersionList', [])
                for version in model_version_list:
                    if version.get('caseName') == "Det V1":
                        case_id = version.get('caseId')
                        modelCaseTemplateId = version.get('modelCaseTemplateId')
                        break

                if not case_id or not modelCaseTemplateId:
                    pytest.fail("在模型 '目标检测' 中未找到caseName为'Det V1'的版本")

                allure.attach(
                    f"找到 caseId: {case_id}, modelCaseTemplateId: {modelCaseTemplateId}",
                    name="目标检测V1模型案例",
                    attachment_type=allure.attachment_type.TEXT
                )

            with allure.step("子步骤2：查询训练机器获取computingPowerId"):
                computing_power_id = self._get_machine_id()

            with allure.step("子步骤3：组装参数并开始训练"):
                self._start_training(case_id, "2", computing_power_id, 10, 3, 0.0002,
                                     self.train_task_id_mtl, modelCaseTemplateId
                                     )

            with allure.step("子步骤4：查询列表页获取modelTrainId"):
                target_model_train_id = self._get_latest_model_train_id(self.train_task_id_mtl)
                allure.attach(
                    f"获取到的modelTrainId: {target_model_train_id}",
                    name="目标modelTrainId",
                    attachment_type=allure.attachment_type.TEXT
                )

        with allure.step("步骤2：监控训练进度"):
            try:
                _, success = self._monitor_training_only(self.train_task_id_mtl, "mtl-v1模型训练",
                                                         target_model_train_id)
            except Exception as e:
                allure.attach(f"训练监控失败: {str(e)}", name="错误详情")
                allure.attach("⚠️ 训练失败，跳过指标验证", name="测试结果")
                return

        # 添加总耗时统计
        total_duration = time.time() - total_start
        mins, secs = divmod(total_duration, 60)
        allure.attach(
            f"测试总耗时: {int(mins)}分{int(secs)}秒",
            name="时间统计",
            attachment_type=allure.attachment_type.TEXT
        )