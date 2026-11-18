import time
import pytest
import allure
import threading

from common import Assert

assertions = Assert.Assertions()


class MonitorUtils:
    def __init__(self, api_deep=None, api_model=None):
        """
        初始化监控工具类
        :param api_deep: 用于数据处理监控的API实例
        :param api_model: 用于训练/提交监控的API实例
        """
        self.api_deep = api_deep
        self.api_model = api_model
        self.max_wait_seconds = 1800  # 最大等待30分钟
        self.poll_interval = 10  # 轮询间隔10秒
        self.lock = threading.Lock()  # 线程锁用于Allure附件操作

    def safe_attach(self, content, name, attachment_type=allure.attachment_type.TEXT):
        """线程安全的Allure附件添加"""
        with self.lock:
            allure.attach(content, name=name, attachment_type=attachment_type)

    def monitor_cut_progress(self, task_name, process_name="数据处理"):
        """
        监控数据处理状态
        :param task_name: 任务名称
        :param process_name: 流程名称（如"目标检测/分割"、"过检样本"等）
        :return: (trainTaskId, 是否成功)
        """
        start_time = time.time()
        attempt = 0
        trainTaskId = None

        # 状态映射表
        status_mapping = {
            0: "处理中",
            1: "已完成",
            2: "异常"
        }

        with allure.step(f"监控{process_name}任务进度"):
            while True:
                attempt += 1
                with allure.step(f"第{attempt}次状态检查"):
                    # 发送查询请求
                    response = self.api_deep.query_train_tasks(task_name)
                    assertions.assert_code(response.status_code, 200)

                    # 解析响应数据
                    response_data = response.json()
                    tasks = response_data['data']['list']

                    # 线程安全的附件记录
                    self.safe_attach(
                        str(response_data),
                        name="原始响应数据",
                        attachment_type=allure.attachment_type.JSON
                    )

                    # 验证任务存在
                    if not tasks:
                        pytest.fail(f"未找到任务: {task_name}")

                    # 获取任务状态
                    current_task = next(
                        (t for t in tasks if t['taskName'] == task_name),
                        None
                    )
                    if not current_task:
                        pytest.fail(f"任务列表匹配失败: {task_name}")

                    status = current_task['dataStatus']
                    trainTaskId = current_task['trainTaskId']

                    # 状态和时间信息
                    status_text = status_mapping.get(status, f"未知({status})")
                    status_info = f"当前状态: {status_text}"
                    self.safe_attach(status_info, name="状态解析")
                    self.safe_attach(f"trainTaskId: {trainTaskId}", name="任务ID")

                    # 时间统计
                    current_duration = int(time.time() - start_time)
                    mins, secs = divmod(current_duration, 60)
                    time_message = f"已等待: {mins}分{secs}秒"
                    self.safe_attach(time_message, name="耗时统计")

                    # 构建状态信息
                    status_display = (
                        f"{process_name}状态: {status_text} | "
                        f"耗时: {mins}分{secs}秒"
                    )

                    # 控制台实时打印（带颜色）
                    if status == 0:  # 处理中 - 黄色
                        print(f"\r\033[93m{status_display}\033[0m", end="", flush=True)
                    elif status == 1:  # 已完成 - 绿色
                        print(f"\r\033[92m{status_display}\033[0m", flush=True)
                    else:  # 异常 - 红色
                        print(f"\r\033[91m{status_display}\033[0m", flush=True)

                    # 状态判断
                    if status == 1:
                        self.safe_attach(f"{process_name}任务已完成", name="状态更新")
                        return trainTaskId, True
                    elif status == 2:
                        error_msg = current_task.get('errorMsg', '处理异常')
                        pytest.fail(f"{process_name}异常: {error_msg}")

                    # 超时检查
                    elapsed = time.time() - start_time
                    if elapsed > self.max_wait_seconds:
                        pytest.fail(f"{process_name}超时: 等待{self.max_wait_seconds}秒未完成")

                    # 间隔等待
                    time.sleep(self.poll_interval)

    def monitor_train_progress(self, trainTaskId, task_description="模型训练"):
        """
        监控模型训练状态（改进版：记录状态变更时间）
        :param trainTaskId: 训练任务ID
        :param task_description: 任务描述（如"目标检测/分割训练"）
        :return: (modelTrainId, 是否成功)
        """
        start_time = time.time()
        total_start = time.time()  # 总开始时间
        attempt = 0
        modelTrainId = None

        # 状态跟踪变量
        prev_status = None
        status_start_time = None
        status_durations = {}  # 存储各状态持续时间
        last_status_info = ""  # 存储上一个状态的信息

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

        # 验证状态映射表
        verify_mapping = {
            0: "未验证",
            1: "验证中",
            2: "验证失败",
            3: "验证成功"
        }

        with allure.step(f"监控{task_description}进度"):
            while True:
                attempt += 1
                with allure.step(f"第{attempt}次训练状态检查"):
                    # 发送查询请求
                    response = self.api_model.query_train_records(trainTaskId)
                    assertions.assert_code(response.status_code, 200)

                    # 解析响应数据
                    response_data = response.json()
                    records = response_data['data']['list']

                    # 线程安全的附件记录
                    self.safe_attach(
                        str(response_data),
                        name="训练记录响应数据",
                        attachment_type=allure.attachment_type.JSON
                    )

                    # 验证记录存在性
                    if not records:
                        pytest.fail(f"未找到trainTaskId={trainTaskId}的训练记录")

                    current_record = records[0]  # 取第一条记录
                    train_status = current_record['trainStatus']
                    verify_status = current_record.get('verifyStatus', None)
                    modelTrainId = current_record['modelTrainId']

                    # 状态变更检测
                    current_status = (train_status, verify_status)
                    if current_status != prev_status:
                        # 记录上一个状态的持续时间
                        if prev_status is not None and status_start_time is not None:
                            status_duration = time.time() - status_start_time
                            status_key = f"{status_mapping.get(prev_status[0], f'未知({prev_status[0]})')}" + \
                                         (f"|{verify_mapping.get(prev_status[1], f'未知({prev_status[1]})')}"
                                          if prev_status[1] is not None else "")
                            status_durations[status_key] = status_duration

                            # 打印状态变更信息（保留在控制台）
                            status_duration_mins, status_duration_secs = divmod(int(status_duration), 60)
                            print(
                                f"\n{task_description}状态变更: {status_key} 耗时 {status_duration_mins}分{status_duration_secs}秒")

                            self.safe_attach(
                                f"状态 '{status_key}' 耗时: {status_duration:.1f}秒",
                                name="状态变更记录"
                            )

                        # 重置新状态开始时间
                        status_start_time = time.time()
                        prev_status = current_status

                    # 时间统计
                    current_duration = int(time.time() - start_time)
                    mins, secs = divmod(current_duration, 60)
                    current_status_duration = int(time.time() - status_start_time) if status_start_time else 0

                    # 构建状态信息
                    status_info = (
                        f"{task_description}状态: {status_mapping.get(train_status, f'未知({train_status})')} | "
                        f"验证状态: {verify_mapping.get(verify_status, f'未知({verify_status})')} | "
                        f"当前状态耗时: {current_status_duration}秒 | "
                        f"总耗时: {mins}分{secs}秒"
                    )

                    # 仅当状态信息变化时更新控制台（避免频繁刷新）
                    if status_info != last_status_info:
                        print(f"\r{status_info}", end="", flush=True)
                        last_status_info = status_info

                    # 状态机判断
                    if train_status == 1:
                        pytest.fail("训练失败，请检查日志")
                    elif train_status == 2:
                        if verify_status == 2:
                            pytest.fail("验证失败，请检查日志")
                        elif verify_status == 3:
                            # 记录最终状态持续时间
                            final_status = f"{status_mapping[train_status]}|{verify_mapping[verify_status]}"
                            status_durations[final_status] = time.time() - status_start_time

                            # 记录总时间
                            total_duration = time.time() - total_start
                            total_mins, total_secs = divmod(int(total_duration), 60)

                            # 生成状态耗时报告
                            report_lines = [f"{task_description}状态耗时统计:"]
                            for status, duration in status_durations.items():
                                duration_mins, duration_secs = divmod(int(duration), 60)
                                report_lines.append(f"- {status}: {duration_mins}分{duration_secs}秒")
                            report_lines.append(f"总耗时: {total_mins}分{total_secs}秒")
                            report = "\n".join(report_lines)

                            self.safe_attach(report, name="训练耗时统计")
                            print(f"\n\033[92m{task_description}完成! 总耗时: {total_mins}分{total_secs}秒\033[0m")
                            return modelTrainId, True

                    # 超时检查
                    elapsed = time.time() - start_time
                    if elapsed > self.max_wait_seconds:
                        pytest.fail(f"训练卡住，请检查日志（等待超过{self.max_wait_seconds}秒）")

                    # 间隔等待
                    time.sleep(self.poll_interval)

    def monitor_commit_progress(self, trainTaskId, task_description="模型提交"):
        """
        监控模型提交状态（改进版：添加任务描述）
        :param trainTaskId: 训练任务ID
        :param task_description: 任务描述（如"目标检测模型提交"）
        :return: 是否成功
        """
        start_time = time.time()
        attempt = 0

        # 状态映射表
        status_mapping = {
            0: "未提交",
            1: "已提交",
            2: "提交中",
            3: "提交失败"
        }

        with allure.step(f"监控{task_description}状态"):
            while True:
                attempt += 1
                with allure.step(f"第{attempt}次提交状态检查"):
                    # 发送查询请求
                    response = self.api_model.query_train_records(trainTaskId)
                    assertions.assert_code(response.status_code, 200)

                    # 解析响应数据
                    response_data = response.json()
                    records = response_data['data']['list']

                    # 线程安全的附件记录
                    self.safe_attach(
                        str(response_data),
                        name="提交状态响应数据",
                        attachment_type=allure.attachment_type.JSON
                    )

                    # 验证记录存在性
                    if not records:
                        pytest.fail(f"未找到trainTaskId={trainTaskId}的提交记录")

                    current_record = records[0]  # 取第一条记录
                    commit_status = current_record.get('commitStatus')

                    # 时间统计
                    current_duration = int(time.time() - start_time)
                    mins, secs = divmod(current_duration, 60)

                    # 构建状态信息
                    status_info = (
                        f"{task_description}状态: {status_mapping.get(commit_status, f'未知({commit_status})')} | "
                        f"耗时: {mins}分{secs}秒"
                    )

                    # 控制台实时打印（带颜色）
                    if commit_status in [0, 2]:  # 未提交或提交中 - 黄色
                        print(f"\r\033[93m{status_info}\033[0m", end="", flush=True)
                    elif commit_status == 1:  # 已提交 - 绿色
                        print(f"\r\033[92m{status_info}\033[0m", flush=True)
                    else:  # 提交失败 - 红色
                        print(f"\r\033[91m{status_info}\033[0m", flush=True)

                    # 状态判断
                    if commit_status == 3:
                        pytest.fail(f"{task_description}失败，请检查日志")
                    elif commit_status == 1:
                        self.safe_attach(f"{task_description}已完成", name="最终状态")
                        # 使用绿色输出完成信息
                        print(f"\n\033[92m{task_description}完成! 总耗时: {mins}分{secs}秒\033[0m")
                        return True

                    # 超时检查
                    elapsed = time.time() - start_time
                    if elapsed > self.max_wait_seconds:
                        pytest.fail(f"{task_description}卡住，请检查日志（等待超过{self.max_wait_seconds}秒）")

                    # 间隔等待
                    time.sleep(self.poll_interval)