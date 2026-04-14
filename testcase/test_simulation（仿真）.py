"""
仿真测试流程
"""
import pytest
import allure
import time
from common.Request_Response import ApiClient
from common import Assert
from api import api_login, api_simulation

assertions = Assert.Assertions()
time_str = time.strftime("%Y%m%d%H%M%S", time.localtime())

# 初始化全局客户端
base_headers = {
    "Authorization": api_login.ApiLogin().login(),
    "Miai-Product-Code": api_login.code,
    "Miaispacemanageid": api_login.manageid
}
global_client = ApiClient(base_headers=base_headers)


@allure.feature("场景：综合-仿真测试全流程")
class TestSimulation:
    @classmethod
    def setup_class(cls):
        """初始化接口封装实例"""
        cls.api_simulation = api_simulation.ApiSimulation(global_client)
        cls.test_atlas_name = f"接口自动化-{time_str}-仿真测试"
        cls.start_time = time.time()  # 记录类开始时间
        cls.max_wait_seconds = 1800
        cls.poll_interval = 10
        cls.test_atlas_id = None
        cls.test_task_id = None

    @classmethod
    def teardown_class(cls):
        """计算并输出总耗时"""
        total_duration = time.time() - cls.start_time
        mins, secs = divmod(total_duration, 60)
        duration_info = f"仿真测试流程总耗时: {int(mins)}分{int(secs)}秒"

        # 控制台输出
        print(f"\n\033[92m{duration_info}\033[0m")

        # 添加到Allure报告
        allure.dynamic.title(duration_info)
        allure.attach(
            duration_info,
            name="仿真测试流程总耗时",
            attachment_type=allure.attachment_type.TEXT
        )

    def _monitor_test_atlas_progress(self):
        """监控测试图集处理状态并获取ID"""
        start_time = time.time()
        attempt = 0
        id_acquired = False  # 标记ID是否已获取

        # 状态映射表
        status_mapping = {
            1: "处理中",
            2: "已完成",
            3: "处理失败",
            4: "已使用"
        }

        with allure.step("监控测试图集处理状态"):
            while True:
                attempt += 1
                step_start = time.time()

                with allure.step(f"第{attempt}次状态检查"):
                    # 调用查询接口
                    response = self.api_simulation.query_test_atlas()
                    assertions.assert_code(response.status_code, 200)

                    response_data = response.json()
                    test_atlases = response_data['data']['list']

                    # 将响应数据附加到Allure报告
                    allure.attach(
                        str(response_data),
                        name="测试图集查询响应",
                        attachment_type=allure.attachment_type.JSON
                    )

                    if not test_atlases:
                        pytest.fail("未找到任何测试图集数据")

                    # 查找指定名称的图集
                    target_atlas = next(
                        (a for a in test_atlases if a.get('name') == self.test_atlas_name),
                        None
                    )

                    if not target_atlas:
                        pytest.fail(f"未找到测试图集: {self.test_atlas_name}")

                    # 提取图集ID（如果尚未获取）
                    if not id_acquired:
                        atlas_id = target_atlas.get('dataAlgorithmTestDatasetId')
                        if atlas_id:
                            self.__class__.test_atlas_id = atlas_id
                            id_acquired = True
                            allure.attach(
                                f"获取到测试图集ID: {atlas_id}",
                                name="测试图集ID",
                                attachment_type=allure.attachment_type.TEXT
                            )

                    status = target_atlas.get('status')
                    if status is None:
                        pytest.fail("状态字段缺失")

                    # 计算耗时
                    current_duration = int(time.time() - start_time)
                    mins, secs = divmod(current_duration, 60)
                    status_info = (
                        f"创建测试图集状态: {status} ({status_mapping.get(status, '未知状态')}) | "
                        f"总耗时: {mins}分{secs}秒"
                    )

                    # 控制台输出带颜色标识
                    if status == 1:
                        print(f"\r\033[93m{status_info}\033[0m", end="", flush=True)
                    elif status == 2:
                        print(f"\r\033[92m{status_info}\033[0m", flush=True)
                    else:
                        print(f"\r\033[91m{status_info}\033[0m", flush=True)

                    # Allure报告记录状态
                    allure.attach(status_info, name="状态详情")

                    # 状态判断逻辑
                    if status == 2:  # 已完成
                        allure.attach("测试图集处理已完成", name="最终状态")
                        return
                    elif status in [3, 4]:  # 失败或已使用
                        error_msg = target_atlas.get('errorMsg', '无错误信息')
                        pytest.fail(f"测试图集处理异常: {error_msg}")

                    # 超时检查
                    elapsed = time.time() - start_time
                    if elapsed > self.max_wait_seconds:
                        pytest.fail(f"处理超时: 等待{self.max_wait_seconds}秒未完成")

                time.sleep(self.poll_interval)

    def _monitor_test_task_progress(self):
        """监控仿真测试任务状态"""
        start_time = time.time()
        attempt = 0

        # 状态映射表
        status_mapping = {
            1: "准备中",
            2: "排队中",
            3: "测试中",
            4: "测试完成",
            5: "测试失败"
        }

        # 需要轮询的状态
        polling_statuses = [1, 2, 3]

        with allure.step("监控仿真测试任务状态"):
            while True:
                attempt += 1
                step_start = time.time()

                with allure.step(f"第{attempt}次状态检查"):
                    # 调用查询接口
                    response = self.api_simulation.query_test_task(self.test_atlas_id)
                    assertions.assert_code(response.status_code, 200)

                    response_data = response.json()
                    test_tasks = response_data['data']['list']

                    # 将响应数据附加到Allure报告
                    allure.attach(
                        str(response_data),
                        name="仿真测试任务查询响应",
                        attachment_type=allure.attachment_type.JSON
                    )

                    if not test_tasks:
                        pytest.fail("未找到任何仿真测试任务")

                    # 查找指定ID的任务
                    target_task = next(
                        (t for t in test_tasks if t.get('dataAlgorithmTestId') == self.test_task_id),
                        None
                    )

                    if not target_task:
                        pytest.fail(f"未找到测试任务ID: {self.test_task_id}")

                    status = target_task.get('status')
                    if status is None:
                        pytest.fail("状态字段缺失")

                    # 计算耗时
                    current_duration = int(time.time() - start_time)
                    mins, secs = divmod(current_duration, 60)
                    status_info = (
                        f"仿真测试状态: {status} ({status_mapping.get(status, '未知状态')}) | "
                        f"总耗时: {mins}分{secs}秒"
                    )

                    # 控制台输出带颜色标识
                    if status in polling_statuses:
                        print(f"\r\033[93m{status_info}\033[0m", end="", flush=True)
                    elif status == 4:
                        print(f"\r\033[92m{status_info}\033[0m", flush=True)
                    else:
                        print(f"\r\033[91m{status_info}\033[0m", flush=True)

                    # Allure报告记录状态
                    allure.attach(status_info, name="状态详情")

                    # 状态判断逻辑
                    if status == 4:  # 测试完成
                        allure.attach("仿真测试已完成", name="最终状态")
                        return
                    elif status == 5:  # 测试失败
                        error_msg = target_task.get('errorMsg', '无错误信息')
                        pytest.fail(f"仿真测试失败: {error_msg}")

                    # 超时检查
                    elapsed = time.time() - start_time
                    if elapsed > self.max_wait_seconds:
                        pytest.fail(f"测试超时: 等待{self.max_wait_seconds}秒未完成")

                time.sleep(self.poll_interval)

    @pytest.mark.order(1)
    @allure.story("测试图集")
    def test_atlas_workflow(self):
        total_start = time.time()
        step_durations = {}  # 存储每个步骤的耗时

        with allure.step("步骤1：创建测试图集") as step1:
            step_start = time.time()
            response = self.api_simulation.create_test_atlas(self.test_atlas_name)

            # 验证响应
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            # 记录任务信息
            allure.attach(
                f"测试图集名称: {self.test_atlas_name}",
                name="测试图集创建信息",
                attachment_type=allure.attachment_type.TEXT
            )

            # 记录步骤耗时
            step_duration = time.time() - step_start
            step_durations["步骤1"] = step_duration

            # 使用 allure.dynamic.title 更新步骤名称
            allure.dynamic.title(f"步骤1：创建测试图集 (耗时: {step_duration:.2f}秒)")

        with allure.step("步骤2：监控创建测试图集状态") as step2:
            step_start = time.time()
            self._monitor_test_atlas_progress()

            # 记录步骤耗时
            step_duration = time.time() - step_start
            step_durations["步骤2"] = step_duration

            # 使用 allure.dynamic.title 更新步骤名称
            allure.dynamic.title(f"步骤2：监控创建测试图集状态 (耗时: {step_duration:.2f}秒)")
            # print(f"✅ 测试图集处理完成 - 耗时: {step_duration:.2f}秒")

    @pytest.mark.order(2)
    @allure.story("仿真测试")
    def test_simulation_workflow(self):
        total_start = time.time()
        step_durations = {}

        with allure.step("步骤1：创建仿真测试任务") as step1:
            step_start = time.time()
            response = self.api_simulation.create_test_task(self.test_atlas_id)

            # 验证响应
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            # 提取测试任务ID
            test_task_id = response_data.get('data')
            if test_task_id:
                self.__class__.test_task_id = test_task_id
                allure.attach(
                    f"获取到仿真测试任务ID: {test_task_id}",
                    name="测试任务ID",
                    attachment_type=allure.attachment_type.TEXT
                )
            else:
                pytest.fail("创建测试任务失败：未返回任务ID")

            # 记录步骤耗时
            step_duration = time.time() - step_start
            step_durations["步骤1"] = step_duration
            allure.dynamic.title(f"步骤1：创建仿真测试任务 (耗时: {step_duration:.2f}秒)")

        with allure.step("步骤2：监控仿真测试状态") as step2:
            step_start = time.time()
            self._monitor_test_task_progress()

            # 记录步骤耗时
            step_duration = time.time() - step_start
            step_durations["步骤2"] = step_duration
            allure.dynamic.title(f"步骤2：监控仿真测试状态 (耗时: {step_duration:.2f}秒)")
            # print(f"✅ 仿真测试完成 - 耗时: {step_duration:.2f}秒")

        with allure.step("步骤3：查看数据算法评估报告（模型综合评估）") as step3:
            step_start = time.time()
            response = self.api_simulation.query_test_report(self.test_task_id)

            # 验证响应
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            step_duration = time.time() - step_start
            step_durations["步骤3"] = step_duration
            allure.dynamic.title(f"步骤3：查看模型综合评估报告 (耗时: {step_duration:.2f}秒)")
            print(f"✅ 查看模型综合评估完成 - 耗时: {step_duration:.2f}秒")

        with allure.step("步骤4：查看数据算法评估报告（缺陷图模型检出评估）") as step4:
            step_start = time.time()
            response = self.api_simulation.query_test_detailReport(self.test_task_id)

            # 验证响应
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            step_duration = time.time() - step_start
            step_durations["步骤4"] = step_duration
            allure.dynamic.title(f"步骤4：查看缺陷图模型检出评估 (耗时: {step_duration:.2f}秒)")
            print(f"✅ 查看缺陷图模型检出评估完成 - 耗时: {step_duration:.2f}秒")

    @pytest.mark.order(3)
    @allure.story("测试数据清除")
    def test_cleanup(self):
        # 删除仿真测试任务（如果存在）
        if self.test_task_id:
            with allure.step("步骤1：删除仿真测试任务"):
                response = self.api_simulation.delete_test_task(self.test_task_id)
                assertions.assert_code(response.status_code, 200)
                response_data = response.json()
                assertions.assert_in_text(response_data['msg'], '成功')
        else:
            print("⚠️ 跳过删除测试任务：test_task_id为空")
            allure.attach("跳过删除测试任务：test_task_id为空", name="清理提示")

        # 删除测试图集（如果存在）
        if self.test_atlas_id:
            with allure.step("步骤2：删除测试图集"):
                response = self.api_simulation.delete_test_atlas(self.test_atlas_id)
                assertions.assert_code(response.status_code, 200)
                response_data = response.json()
                assertions.assert_in_text(response_data['msg'], '成功')
        else:
            print("⚠️ 跳过删除测试图集：test_atlas_id为空")
            allure.attach("跳过删除测试图集：test_atlas_id为空", name="清理提示")
