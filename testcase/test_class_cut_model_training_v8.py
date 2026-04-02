"""
深度分类切图YoloV8模型训练接口自动化流程
"""
import ast
from time import sleep

import pytest
import allure
import time
import os
import configparser
from configparser import ConfigParser
from common.Request_Response import ApiClient
from common import Assert
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


@allure.feature("场景：综合-分类切图YoloV8训练全流程")
class TestClassCutModelTraining:
    @classmethod
    def setup_class(cls):
        """初始化接口封装实例"""
        cls.api_comprehensive = api_comprehensive_sample_library.ApiComprehensiveSampleLibrary(global_client)
        cls.api_deep = api_deep_training_tasks.ApiDeepTrainTasks(global_client)
        cls.api_model = api_deep_training_tasks.ApiModelTrain(global_client)
        cls.api_process = api_deep_training_tasks.ApiPostProcess(global_client)
        cls.api_base = api_model_base.ApiModelBase(global_client)
        cls.task_name = f"接口自动化-{time_str}-分类切图"  # 统一任务名称格式
        cls.max_wait_seconds = 1800  # 最大等待30分钟
        cls.poll_interval = 10  # 轮询间隔10秒
        cls.start_timestamp = None  # 新增时间记录点
        cls.trainTaskId = None
        cls.modelTrainId = None
        cls.class_cut_verifyId = None
        cls.modelManageId = None
        cls.monitor = MonitorUtils(api_deep=cls.api_deep, api_model=cls.api_model)
        # 读取配置文件
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'env_config.ini')
        config = configparser.ConfigParser()
        config.read(config_path)
        cls.classifyType = ast.literal_eval(config.get('class_cut_ids', 'classify_type'))
        cls.machine_name = config.get('class_cut_ids', 'machine_name')

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

    def _withdraw_model(self, model_manage_id, model_type):
        """通用模型撤回方法"""
        with allure.step(f"{model_type}模型撤回"):
            response = self.api_base.model_withdraw(model_manage_id, 1)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')
            allure.attach(
                f"{model_type}模型撤回成功: {model_manage_id}",
                name=f"{model_type}模型撤回",
                attachment_type=allure.attachment_type.TEXT
            )

    @allure.story("图像分类(切图)YoloV8模型训练&后处理")
    def test_class_cut_task_workflow_v8(self):
        total_start = time.time()  # 记录总开始时间

        with allure.step("步骤1：创建分类切图训练任务"):
            sleep(1)
            response = self.api_comprehensive.create_deep_training_tasks(
                defectName=[],
                photoId=[],
                cut=224,
                taskName=self.task_name,
                classifyType=self.classifyType,
                caseId="cls_model",
                caseName="图像分类",
                create_type=2,
                iscut=True,
                remark="图像分类(切图)YoloV8模型训练"
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
                "图像分类(切图)数据处理"
            )
            self.__class__.trainTaskId = self.trainTaskId

        with allure.step("步骤3：开始分类切图YoloV8模型训练"):
            with allure.step("子步骤1：查询模型方案获取caseId"):
                model_response = self.api_model.query_model_cls()
                assertions.assert_code(model_response.status_code, 200)
                model_data = model_response.json()
                assertions.assert_in_text(model_data['msg'], '操作成功')

                # 查找name为"图像分类"的模型数据
                matched_model = None
                case_id = None
                modelCaseTemplateId = None

                for model_item in model_data['data']:
                    # 查找name为"图像分类"的数据
                    if model_item.get('name') == "图像分类":
                        matched_model = model_item
                        break

                if not matched_model:
                    pytest.fail("模型 '图像分类' 在响应中未找到")

                # 在匹配的模型中查找modelVersionList中caseName为"Cls V2"的项
                model_version_list = matched_model.get('modelVersionList', [])
                for version in model_version_list:
                    if version.get('caseName') == "Cls V2":
                        case_id = version.get('caseId')
                        modelCaseTemplateId = version.get('modelCaseTemplateId')
                        break

                if not case_id or not modelCaseTemplateId:
                    pytest.fail("在模型 '图像分类' 中未找到caseName为'Cls V2'的版本")

                allure.attach(
                    f"找到 caseId: {case_id}, modelCaseTemplateId: {modelCaseTemplateId}",
                    name="图像分类模型案例",
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

            with allure.step("子步骤3：组装参数并开始分类切图-YoloV8训练"):
                train_response = self.api_model.start_train("224", "224", case_id, -1, computing_power_id, 30, 16,
                                                            0.0002,
                                                            self.trainTaskId, modelCaseTemplateId)
                assertions.assert_code(train_response.status_code, 200)
                train_data = train_response.json()
                assertions.assert_in_text(train_data['msg'], '操作成功')

        with allure.step("步骤4：监控训练进度"):
            self.modelTrainId, success = self.monitor.monitor_train_progress(self.trainTaskId, "图像分类(切图)训练")
            self.__class__.modelTrainId = self.modelTrainId
            time.sleep(3)

        with allure.step("步骤5：提交模型"):
            with allure.step("子步骤1：发起分类切图模型提交"):
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
                success = self.monitor.monitor_commit_progress(self.trainTaskId, "图像分类(切图)模型提交")

        with allure.step("步骤6：训练记录查询获取分类切图验证集verifyId"):
            response = self.api_model.query_train_records(
                trainTaskId=TestClassCutModelTraining.trainTaskId
            )

            # 响应断言
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            # 提取验证集verify_id
            class_cut_verify_id = None
            for task in response_data.get('data', {}).get('list', []):
                # 遍历verifyRecord查找包含'验证集'的条目
                for record in task.get('verifyRecord', []):
                    if '验证集' in record.get('name', ''):
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
                f"未找到分类切图验证集verifyRecordID，响应数据：{response_data}"
            )

            allure.attach(
                f"分类切图验证集验证id: {self.class_cut_verifyId}",
                name="分类切图验证集-verifyId",
                attachment_type=allure.attachment_type.TEXT
            )

        with allure.step("步骤7：分类切图后处理查看样本分析"):
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

        with allure.step("步骤8：分类切图拷贝增广"):
            response = self.api_process.class_copy(
                class_trainTaskId=TestClassCutModelTraining.trainTaskId,
                class_verifyId=self.class_cut_verifyId,
                copy_id=class_cut_id
            )

            # 响应断言
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

        with allure.step("步骤9：监控分类切图拷贝进度"):
            _, success = self.monitor.monitor_cut_progress(TestClassCutModelTraining.task_name, "分类切图-拷贝增广处理")

        with allure.step("步骤10：分类切图Yolov8模型撤回"):
            class_original_manage_id = self._get_model_manage_id(
                model_train_id=TestClassCutModelTraining.modelTrainId
            )
            self._withdraw_model(class_original_manage_id, "分类切图")

        with allure.step("步骤11：分类切图训练任务删除"):
            response = self.api_deep.delete_train_tasks(TestClassCutModelTraining.trainTaskId)

            # 响应断言
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

        allure.dynamic.description(
            "深度(分类切图)Yolov8模型训练&后处理测试完成！\n"
            f"总耗时: {time.strftime('%H:%M:%S', time.gmtime(time.time() - total_start))}"
        )
        print("\n\n\033[92m深度(分类切图)-自动化Yolov8模型训练&后处理测试完成！\033[0m")
        print(f"总耗时: {time.strftime('%H:%M:%S', time.gmtime(time.time() - total_start))}")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--alluredir=./allure-results'])
