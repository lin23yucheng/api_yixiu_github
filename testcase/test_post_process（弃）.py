import os
import random
import time
import pytest
import allure
from common import Assert
from configparser import ConfigParser
from common.Request_Response import ApiClient
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


@pytest.fixture(scope="function")
def get_persistent_ids():
    """从配置文件中读取ID"""
    # 构建配置文件路径
    config_path = os.path.abspath(os.path.join(
        os.path.dirname(os.path.dirname(__file__)),  # 向上一级，回到项目根目录
        'config/env_config.ini'  # 根目录下的 config 目录
    ))

    # 检查配置文件是否存在
    if not os.path.exists(config_path):
        pytest.skip("配置文件不存在")

    # 初始化ConfigParser并读取配置文件
    config = ConfigParser()
    config.read(config_path)

    # 获取配置文件中的ID值
    ids = {
        'train_task_id': config.get('persistent_ids', 'train_task_id', fallback=None),
        'model_train_id': config.get('persistent_ids', 'model_train_id', fallback=None),
        'class_cut_train_task_id': config.get('class_cut_ids', 'train_task_id', fallback=None),
        'class_cut_model_train_id': config.get('class_cut_ids', 'model_train_id', fallback=None),
        'class_original_train_task_id': config.get('class_original_ids', 'train_task_id', fallback=None),
        'class_original_model_train_id': config.get('class_original_ids', 'model_train_id', fallback=None)
    }

    # 检查是否有任何ID值为None
    if None in ids.values():
        pytest.skip("训练任务ID未就绪")
    return ids


@allure.feature("场景：综合-后处理全流程")
class TestPostProcess:
    @classmethod
    def setup_class(cls):
        """初始化接口封装实例"""
        cls.api_deep = api_deep_training_tasks.ApiDeepTrainTasks(global_client)
        cls.api_model = api_deep_training_tasks.ApiModelTrain(global_client)
        cls.api_process = api_deep_training_tasks.ApiPostProcess(global_client)
        cls.max_wait_seconds = 1800  # 最大等待30分钟
        cls.poll_interval = 5  # 轮询间隔5秒
        cls.start_timestamp = None  # 新增时间记录点
        cls.trainTaskId = None
        cls.verifyId = None
        cls.task_name = None
        cls.class_cut_trainTaskId = None
        cls.class_cut_verifyId = None
        cls.class_cut_task_name = None
        cls.class_original_trainTaskId = None
        cls.class_original_verifyId = None
        cls.class_original_task_name = None
        cls.monitor = MonitorUtils(api_deep=cls.api_deep, api_model=cls.api_model)

    def _monitor_analysis_progress(self, analysis_type, api_call):
        """通用的状态监控方法"""
        start_time = time.time()
        attempt = 0
        last_status_info = ""  # 用于避免重复打印相同信息

        # 状态颜色映射
        color_mapping = {
            1: "\033[93m",  # 分析中 - 黄色
            2: "\033[92m",  # 分析完成 - 绿色
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
                        # 处理None值和获取颜色
                        subStatus = subStatus if subStatus is not None else -1  # 将None转换为一个不会匹配的值
                        color_code = color_mapping.get(subStatus, "\033[91m")  # 默认红色

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

    @pytest.mark.order(1)
    @allure.story("深度模型报表样本分析")
    def test_analysis(self, get_persistent_ids):  # 注入fixture
        train_task_id = get_persistent_ids['train_task_id']  # 从配置获取ID
        self.__class__.trainTaskId = get_persistent_ids['train_task_id']  # 关键：赋值给类变量

        with allure.step("步骤1：训练记录查询获取训练集的verifyId"):
            # 使用配置中的train_task_id发起请求
            response = self.api_model.query_train_records(
                trainTaskId=train_task_id
            )

            # 响应断言
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            # 提取训练集verify_id
            verify_id = None
            for task in response_data.get('data', {}).get('list', []):
                # 遍历verifyRecord查找包含'训练集'的条目
                for record in task.get('verifyRecord', []):
                    if '训练集' in record.get('name', ''):
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
                f"未找到训练集verifyRecordID，响应数据：{response_data}"
            )

            allure.attach(
                f"训练集验证id: {self.verifyId}",
                name="训练集-verifyId",
                attachment_type=allure.attachment_type.TEXT
            )

        with allure.step("步骤2：报表分析"):
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

            # 监控报表分析状态
            with allure.step("子步骤2：监控报表分析状态"):
                self._monitor_analysis_progress("报表分析", self.api_process.report_analysis_status)

        with allure.step("步骤3：样本分析"):
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

            # 监控样本分析状态
            with allure.step("子步骤2：监控样本分析状态"):
                self._monitor_analysis_progress("样本分析", self.api_process.sample_analysis_status)

    @pytest.mark.order(2)
    @allure.story("过检样本标记&拷贝增广")
    def test_over_samples(self):
        with allure.step("步骤1: 标记过检样本"):
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

                # 控制台打印
                # print(f"缺陷ID: {defect_id}")

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

                # 控制台打印
                # print(f"标记空过杀响应: {response_data}")

        with allure.step("步骤2: 过检样本拷贝增广"):
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

            # 控制台打印
            # print(f"过检样本拷贝增广响应: {response_data}")

        with allure.step("步骤3: 监控过检拷贝进度"):
            _, success = self.monitor.monitor_cut_progress(self.task_name, "过检样本-拷贝增广处理")

    @pytest.mark.order(3)
    @allure.story("漏检样本标记&拷贝增广")
    def test_miss_samples(self):

        with allure.step("步骤1: 标记漏检样本"):
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

        with allure.step("步骤2: 漏检样本拷贝增广"):
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

        with allure.step("步骤3: 监控漏检拷贝进度"):
            _, success = self.monitor.monitor_cut_progress(self.task_name, "漏检样本-拷贝增广处理")

    @pytest.mark.order(4)
    @allure.story("错检样本标记&拷贝增广")
    def test_error_samples(self):
        with allure.step("步骤1: 标记错检样本"):
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
                    pytest.fail("未找到过检样本数据")

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

        with allure.step("步骤2: 错检样本拷贝增广"):
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

        with allure.step("步骤3: 监控错检拷贝进度"):
            _, success = self.monitor.monitor_cut_progress(self.task_name, "错检样本-拷贝增广处理")

    @pytest.mark.order(5)
    @allure.story("分类切图拷贝增广")
    def test_class_cut_copy(self, get_persistent_ids):  # 注入fixture
        class_cut_train_task_id = get_persistent_ids['class_cut_train_task_id']  # 从配置获取ID
        self.__class__.class_cut_trainTaskId = get_persistent_ids['class_cut_train_task_id']  # 关键：赋值给类变量

        with allure.step("步骤1：训练记录查询获取分类切图训练集验证的verifyId"):
            response = self.api_model.query_train_records(
                trainTaskId=class_cut_train_task_id
            )

            # 响应断言
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            # 提取训练集verify_id
            class_cut_verify_id = None
            for task in response_data.get('data', {}).get('list', []):
                # 遍历verifyRecord查找包含'训练集'的条目
                for record in task.get('verifyRecord', []):
                    if '训练集' in record.get('name', ''):
                        class_cut_verify_id = record.get('id')
                        self.__class__.class_cut_verifyId = class_cut_verify_id  # 关键：赋值给类变量
                        break
                if class_cut_verify_id:
                    break

            # 提取taskName值
            train_list = response_data.get('data', {}).get('list', [])
            if not train_list:
                pytest.fail("未找到训练记录")

            first_sample = train_list[0]
            class_cut_task_name = first_sample.get('taskName')
            self.__class__.class_cut_task_name = class_cut_task_name  # 关键：赋值给类变量

            # 确保找到有效ID
            assertions.assert_is_not_none(
                self.class_cut_verifyId,
                f"未找到分类切图训练集verifyRecordID，响应数据：{response_data}"
            )

            allure.attach(
                f"分类切图训练集验证id: {self.class_cut_verifyId}",
                name="分类切图训练集-verifyId",
                attachment_type=allure.attachment_type.TEXT
            )

        with allure.step("步骤2：分类切图后处理查看样本分析"):
            response = self.api_process.classify_cutting(
                class_verifyId=self.class_cut_verifyId
            )

            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            # 提取id值并拼接成list
            class_cut_id_list = response_data.get('data', {}).get('list', [])
            if len(class_cut_id_list) < 3:
                pytest.fail("响应数据中的list长度不足3")
            class_cut_id = [class_cut_id_list[0]['id'], class_cut_id_list[1]['id'], class_cut_id_list[2]['id']]

        with allure.step("步骤3：分类切图拷贝增广"):
            response = self.api_process.class_copy(
                class_trainTaskId=self.class_cut_trainTaskId,
                class_verifyId=self.class_cut_verifyId,
                copy_id=class_cut_id
            )

            # 响应断言
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

        with allure.step("步骤4：监控分类切图拷贝进度"):
            _, success = self.monitor.monitor_cut_progress(self.class_cut_task_name, "分类切图-拷贝增广处理")

    @pytest.mark.order(6)
    @allure.story("分类大图拷贝增广")
    def test_class_original_copy(self, get_persistent_ids):  # 注入fixture
        class_original_train_task_id = get_persistent_ids['class_original_train_task_id']  # 从配置获取ID
        self.__class__.class_original_trainTaskId = get_persistent_ids['class_original_train_task_id']  # 关键：赋值给类变量

        with allure.step("步骤1：训练记录查询获取分类大图训练集验证的verifyId"):
            response = self.api_model.query_train_records(
                trainTaskId=class_original_train_task_id
            )

            # 响应断言
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            # 提取训练集verify_id
            class_original_verify_id = None
            for task in response_data.get('data', {}).get('list', []):
                # 遍历verifyRecord查找包含'训练集'的条目
                for record in task.get('verifyRecord', []):
                    if '训练集' in record.get('name', ''):
                        class_original_verify_id = record.get('id')
                        self.__class__.class_original_verifyId = class_original_verify_id  # 关键：赋值给类变量
                        break
                if class_original_verify_id:
                    break

            # 提取taskName值
            train_list = response_data.get('data', {}).get('list', [])
            if not train_list:
                pytest.fail("未找到训练记录")

            first_sample = train_list[0]
            class_original_task_name = first_sample.get('taskName')
            self.__class__.class_original_task_name = class_original_task_name  # 关键：赋值给类变量

            # 确保找到有效ID
            assertions.assert_is_not_none(
                self.class_original_verifyId,
                f"未找到分类大图训练集verifyRecordID，响应数据：{response_data}"
            )

            allure.attach(
                f"分类大图训练集验证id: {self.class_original_verifyId}",
                name="分类大图训练集-verifyId",
                attachment_type=allure.attachment_type.TEXT
            )

        with allure.step("步骤2：分类大图后处理查看样本分析"):
            response = self.api_process.classify_cutting(
                class_verifyId=self.class_original_verifyId
            )

            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            # 提取id值并拼接成list
            class_original_id_list = response_data.get('data', {}).get('list', [])
            if len(class_original_id_list) < 3:
                pytest.fail("响应数据中的list长度不足3")
            class_original_id = [class_original_id_list[0]['id'], class_original_id_list[1]['id'],
                                 class_original_id_list[2]['id']]

        with allure.step("步骤3：分类大图拷贝增广"):
            response = self.api_process.class_copy(
                class_trainTaskId=self.class_original_trainTaskId,
                class_verifyId=self.class_original_verifyId,
                copy_id=class_original_id
            )

            # 响应断言
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

        with allure.step("步骤4：监控分类大图拷贝进度"):
            _, success = self.monitor.monitor_cut_progress(self.class_cut_task_name, "分类大图-拷贝增广处理")
