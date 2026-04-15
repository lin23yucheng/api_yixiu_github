"""
EIIR空间标注流程
"""
import os
import pytest
import allure
import configparser
import time
from common import Assert
from datetime import datetime, timedelta
from common.Log import MyLog
from common.Request_Response import ApiClient
from api import api_login, api_eiir_samples, api_eiir_label, api_space
from testcase.test_bash import start_time

assertions = Assert.Assertions()
time_str = time.strftime("%Y%m%d%H%M%S", time.localtime())

config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'env_config.ini')
config = configparser.ConfigParser()
config.read(config_path, encoding='utf-8')

# 获取当前环境并从对应环境节读取
env = config.get("environment", "execution_env", fallback="").strip().lower()
if env not in {"fat", "prod"}:
    raise ValueError(f"execution_env 配置错误: {env}，仅支持 fat 或 prod")

env_eiir_section = f"{env}-EIIR"
space_name = config.get(env_eiir_section, 'space_name')

miaispacemanageid = None

# 获取空间ID - 添加错误检查
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


@allure.feature("场景：EIIR-标注流程")
class TestEiirLabel:
    @classmethod
    def setup_class(cls):
        """初始化接口封装实例"""
        cls.api_eiir_samples = api_eiir_samples.ApiEiirSamples(global_client)
        cls.api_eiir_label = api_eiir_label.ApiEiirLabel(global_client)
        cls.task_name = f"EIIR接口自动化标注-{time_str}"
        cls.samples_select_id = None
        cls.task_id = None
        cls.data_id = None

    @pytest.mark.order(1)
    @allure.story("EIIR原始样本创建标注任务")
    def test_create_label_task(self):


        with allure.step("步骤1：查询EIIR检测样本-待标注") as step1:
            response = self.api_eiir_samples.query_eiir_sample(start_time, end_time, ["1"])
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            # 提取第一条记录的id值并赋值给self.samples_select_id
            records = response_data['data']['records']
            if records:
                TestEiirLabel.samples_select_id = records[0]['id']
                # 添加Allure报告信息
                allure.attach(f"提取的样本ID: {self.samples_select_id}",
                              name="样本ID提取结果",
                              attachment_type=allure.attachment_type.TEXT)
            else:
                pytest.fail("未查询到待标注样本")

        with allure.step("步骤2：创建EIIR标注任务") as step2:
            assert self.samples_select_id is not None, "未获取到样本ID，无法创建标注任务"

            response = self.api_eiir_samples.create_label_task(self.task_name, "1935546134172188674",
                                                               start_time, end_time, [self.samples_select_id])
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            # 添加Allure报告信息
            allure.attach(
                f"任务名称: EIIR接口自动化标注-{time_str}\n"
                f"使用的样本ID: {self.samples_select_id}",
                name="创建标注任务参数",
                attachment_type=allure.attachment_type.TEXT
            )

    @pytest.mark.order(2)
    @allure.story("EIIR标注")
    def test_eiir_label(self):

        with allure.step("步骤1：查询EIIR标注任务是否存在并检查状态") as step1:
            # 定义超时和轮询间隔
            max_wait_time = 5 * 60  # 5分钟
            poll_interval = 3  # 3秒
            start_time = time.time()
            task_found = False
            task_status_ok = False

            while not task_status_ok and (time.time() - start_time) < max_wait_time:
                # 查询任务列表
                response = self.api_eiir_label.query_label_task()
                assertions.assert_code(response.status_code, 200)
                response_data = response.json()
                assertions.assert_in_text(response_data['msg'], '成功')

                # 检查是否存在指定名称的任务
                target_task_name = f"{TestEiirLabel.task_name}-1"
                task_found = False
                task_status = None

                # 遍历任务列表查找匹配的任务
                for task in response_data['data']['list']:
                    if task['taskName'] == target_task_name:
                        TestEiirLabel.task_id = task['dimensionTaskId']
                        task_status = task['taskStatus']
                        task_found = True
                        break

                # 记录当前轮询状态到Allure
                status_info = (
                    f"轮询时间: {time.time() - start_time:.1f}秒\n"
                    f"任务名称: {target_task_name}\n"
                    f"任务ID: {self.task_id if task_found else '未找到'}\n"
                    f"任务状态: {task_status if task_found else 'N/A'}\n"
                    f"期望状态: 1(待开始)"
                )
                allure.attach(
                    status_info,
                    name=f"任务状态轮询-{time.strftime('%H:%M:%S')}",
                    attachment_type=allure.attachment_type.TEXT
                )

                # 检查任务状态
                if task_found and task_status == 1:
                    task_status_ok = True
                    break

                # 如果任务存在但状态不正确
                if task_found and task_status != 1:
                    MyLog.warning(f"任务状态不正确: {task_status}, 期望1(待开始), 继续轮询...")

                # 等待下一次轮询
                time.sleep(poll_interval)

            # 检查最终结果
            if not task_found:
                allure.attach(
                    f"未找到名称为 {target_task_name} 的标注任务",
                    name="任务查询失败",
                    attachment_type=allure.attachment_type.TEXT
                )
                pytest.fail(f"未找到名称为 {target_task_name} 的标注任务")

            if not task_status_ok:
                elapsed = time.time() - start_time
                allure.attach(
                    f"任务状态轮询超时 ({elapsed:.1f}秒)\n"
                    f"任务ID: {self.task_id}\n"
                    f"最后状态: {task_status}\n"
                    f"期望状态: 1(待开始)",
                    name="任务状态超时",
                    attachment_type=allure.attachment_type.TEXT
                )
                pytest.fail(f"任务状态未在{max_wait_time}秒内变为待开始状态")

            # 添加最终成功的Allure报告信息
            allure.attach(
                f"成功找到任务并状态正常\n"
                f"任务名称: {target_task_name}\n"
                f"任务ID: {self.task_id}\n"
                f"任务状态: {task_status}",
                name="任务查询成功",
                attachment_type=allure.attachment_type.TEXT
            )

        with allure.step("步骤2：开启标注任务") as step2:
            assert self.task_id is not None, "未获取到任务ID，无法开启标注任务"

            response = self.api_eiir_label.update_label_task_status(self.task_id)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

        with allure.step("步骤3：获取样本dataId") as step3:
            assert self.task_id is not None, "未获取到任务ID，无法查询样本dataId"

            response = self.api_eiir_label.query_label_data_id(self.task_id)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            # 提取第一条数据的dataId
            if response_data['data']:
                self.data_id = response_data['data'][0]['dataId']
                # 添加Allure报告信息
                allure.attach(
                    f"提取的dataId: {self.data_id}",
                    name="dataId提取结果",
                    attachment_type=allure.attachment_type.TEXT
                )
            else:
                pytest.fail("未查询到样本数据")

        with allure.step("步骤4：获取标注label") as step4:
            response = self.api_eiir_label.get_label(miaispacemanageid)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            # 从响应data中提取第一个标签值
            if response_data['data']:
                label = response_data['data'][0]  # 获取第一个标签值

                # 添加Allure报告信息
                allure.attach(
                    f"提取的标签值: {label}",
                    name="标签提取结果",
                    attachment_type=allure.attachment_type.TEXT
                )
            else:
                pytest.fail("未获取到任何标签数据")

        with allure.step("步骤5:标注矩形") as step5:
            assert self.data_id is not None, "未获取到dataId，无法进行标注"

            response = self.api_eiir_label.save_label(self.data_id, label)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

        with allure.step("步骤6:完成标注任务") as step6:
            response = self.api_eiir_label.complete_label_task(self.task_id)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

        with allure.step("步骤7:撤回标注任务") as step7:
            response = self.api_eiir_label.revoke_label_task(self.task_id)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

        with allure.step("步骤8:关闭标注任务") as step8:
            response = self.api_eiir_label.close_label_task(self.task_id)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')
