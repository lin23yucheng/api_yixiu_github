"""
深度YoloV8模型训练 - 流程级数据驱动版
基于 test_deep_model_training_v8.py 改造

改动说明：
1. 原来的硬编码参数 → 从scenario字典中读取
2. 原来一条路走到底 → 根据scenario控制走到哪一步
3. 新增autouse清理脏数据
4. 原有的18步流程逻辑基本不变，只是外面包了一层场景驱动

"""
import pytest
import allure
import time
import os
import ast
import json
import random
from common.client_factory import create_lazy_yixiu_client
from common import Assert
import configparser
from api import api_comprehensive_sample_library, api_deep_training_tasks, api_model_base
from common.monitor_utils import MonitorUtils
from AI.semantic_assertion_engine import semantic_expected_failure

import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
from testdata.scenarios.deep_model_training_v8_scenarios import (
    CREATE_TASK_SCENARIOS,
    TRAINING_FLOW_SCENARIOS,
    STOP_TRAIN_SCENARIOS,
    DUPLICATE_TASK_SCENARIOS,
    EMPTY_VALIDATION_DATASET_SCENARIOS,
    ABNORMAL_ANNOTATION_ANALYSIS_SCENARIOS,
    REMOVE_SAMPLE_RECYCLE_SCENARIOS,
    EXPORT_SAMPLE_SCENARIOS,
    DELETE_SUBMITTED_NO_POSTPROCESS_SCENARIOS,
)

assertions = Assert.Assertions()
time_str = time.strftime("%Y%m%d%H%M%S", time.localtime())

# 全局懒加载客户端：仅在首次发送请求时才进行身份认证。
global_client = create_lazy_yixiu_client()


class SharedSetupMixin:
    """统一初始化API实例和环境配置，减少各测试类重复setup_class代码。"""

    @classmethod
    def setup_shared(
            cls,
            *,
            need_model=False,
            need_process=False,
            need_base=False,
            need_data_mgmt=False,
    ):
        cls.api_comprehensive = api_comprehensive_sample_library.ApiComprehensiveSampleLibrary(global_client)
        cls.api_deep = api_deep_training_tasks.ApiDeepTrainTasks(global_client)

        must_init_model = need_model or need_process or need_data_mgmt
        cls.api_model = api_deep_training_tasks.ApiModelTrain(global_client) if must_init_model else None
        if need_process:
            cls.api_process = api_deep_training_tasks.ApiPostProcess(global_client)
        if need_base:
            cls.api_base = api_model_base.ApiModelBase(global_client)
        if need_data_mgmt:
            cls.api_data_mgmt = api_deep_training_tasks.ApiDataManagement(global_client)

        cls.monitor = MonitorUtils(api_deep=cls.api_deep, api_model=cls.api_model)
        cls.max_wait_seconds = 1800
        cls.poll_interval = 10

        config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'env_config.ini')
        config = configparser.ConfigParser()
        config.read(config_path, encoding='utf-8')
        env = config.get("environment", "execution_env", fallback="").strip().lower()
        env_section = f"{env}-yixiu"

        cls.defectName = ast.literal_eval(config.get(env_section, 'defect_name'))
        cls.photoId_ng = ast.literal_eval(config.get(env_section, 'photo_id_ng'))
        cls.photoId_ok = ast.literal_eval(config.get(env_section, 'photo_id_ok'))
        cls.machine_name = config.get(env_section, 'machine_name')


# ============================================================
# Fixture: 清理脏数据
# 不管测试成功还是失败，把创建的任务都删掉
# ============================================================
@pytest.fixture
def cleanup_tasks(login_session):
    """记录测试中创建的任务ID，测试结束后自动清理"""
    created_task_ids = []

    # 提供给测试用例注册需要清理的任务ID
    def register_task(task_id):
        created_task_ids.append(task_id)

    yield register_task

    # 清理阶段：删除所有注册的任务
    api_deep = api_deep_training_tasks.ApiDeepTrainTasks(global_client)
    for task_id in created_task_ids:
        try:
            with semantic_expected_failure("fixture清理：训练任务可能已被测试步骤删除"):
                api_deep.delete_train_tasks(task_id)
            print(f"清理任务: {task_id}")
        except Exception as e:
            print(f"清理任务失败 {task_id}: {e}")


@pytest.fixture
def login_session():
    """返回全局客户端（兼容原有代码结构）"""
    return global_client


# ============================================================
# 测试1：创建训练任务 - 单接口级参数化
# 验证不同输入参数能否正确创建
# ============================================================
@allure.feature("综合-目标检测YoloV11-数据驱动")
@allure.story("创建训练任务-参数化")
@pytest.mark.training_deep
class TestCreateTask(SharedSetupMixin):
    @classmethod
    def setup_class(cls):
        cls.setup_shared()

    @pytest.mark.parametrize("scenario", CREATE_TASK_SCENARIOS, ids=lambda s: s["name"])
    def test_create_task(self, scenario, cleanup_tasks):
        """不同参数创建训练任务，验证创建是否成功"""
        task_name = f"数据驱动-{scenario['name']}-{time.strftime('%Y%m%d%H%M%S')}"

        with allure.step(f"场景: {scenario['name']}"):
            if scenario["expect_success"]:
                response = self.api_comprehensive.create_deep_training_tasks(
                    defectName=self.defectName,
                    photoId=self.photoId_ng,
                    cut=scenario["cut_value"],
                    taskName=task_name,
                    classifyType=scenario["classify_type"],
                    caseId=scenario["case_id"],
                    caseName=scenario["case_name"],
                    create_type=1,
                    iscut=scenario["iscut"],
                    remark=scenario["remark"]
                )
            else:
                with semantic_expected_failure(f"训练任务创建负向场景: {scenario['name']}"):
                    response = self.api_comprehensive.create_deep_training_tasks(
                        defectName=self.defectName,
                        photoId=self.photoId_ng,
                        cut=scenario["cut_value"],
                        taskName=task_name,
                        classifyType=scenario["classify_type"],
                        caseId=scenario["case_id"],
                        caseName=scenario["case_name"],
                        create_type=1,
                        iscut=scenario["iscut"],
                        remark=scenario["remark"]
                    )

            if scenario["expect_success"]:
                assertions.assert_code(response.status_code, 200)
                response_data = response.json()
                assertions.assert_in_text(response_data['msg'], '成功')

                # 注册清理：监控完切图后拿到trainTaskId再清理
                train_task_id, _ = self.monitor.monitor_cut_progress(
                    task_name, f"{scenario['case_name']}切图处理"
                )
                if train_task_id:
                    cleanup_tasks(train_task_id)
            else:
                # 期望失败的场景
                response_data = response.json()
                assert '成功' not in response_data.get('msg', ''), \
                    f"期望失败但创建成功了: {response_data}"
                if scenario.get("expect_error"):
                    assert scenario["expect_error"] in str(response_data), \
                        f"期望包含 '{scenario['expect_error']}'，实际: {response_data}"


# ============================================================
# 测试2：训练全流程 - 流程级数据驱动
# ============================================================
@allure.feature("综合-目标检测YoloV11-数据驱动")
@allure.story("训练全流程-场景驱动")
@pytest.mark.training_deep
class TestTrainingFlow(SharedSetupMixin):
    @classmethod
    def setup_class(cls):
        cls.setup_shared(need_model=True, need_process=True, need_base=True)

    # 复用原有的监控方法（从原文件搬过来）
    def _monitor_analysis_progress(self, analysis_type, api_call):
        """通用的状态监控方法"""
        start_time = time.time()
        attempt = 0
        with allure.step(f"监控{analysis_type}状态"):
            while True:
                attempt += 1
                response = api_call(self.verifyId)
                assertions.assert_code(response.status_code, 200)
                response_data = response.json()
                data = response_data.get('data')
                subStatus = data.get('subStatus') if isinstance(data, dict) else None
                if subStatus == 2:
                    return True
                elif subStatus != 1:
                    pytest.fail(f"未知状态码: {subStatus}")
                elapsed = time.time() - start_time
                if elapsed > self.max_wait_seconds:
                    pytest.fail(f"{analysis_type}超时")
                time.sleep(self.poll_interval)

    def _monitor_generic_progress(self, api_call, get_status_func,
                                  in_progress_status, success_status,
                                  step_name, status_mapping=None):
        """模型库通用状态监控方法"""
        start_time = time.time()
        attempt = 0
        if status_mapping is None:
            status_mapping = {0: "已提交", 1: "测试中", 2: "测试失败", 3: "测试完成"}

        with allure.step(f"监控{step_name}状态"):
            while True:
                attempt += 1
                response = api_call()
                assertions.assert_code(response.status_code, 200)
                response_data = response.json()
                current_status = get_status_func(response_data)

                if current_status == in_progress_status:
                    elapsed = time.time() - start_time
                    if elapsed > self.max_wait_seconds:
                        pytest.fail(f"{step_name}超时")
                    time.sleep(self.poll_interval)
                    continue
                elif current_status == success_status:
                    return True
                elif current_status in [2, 6]:
                    pytest.fail(f"{step_name}失败，状态{current_status}")
                else:
                    time.sleep(self.poll_interval)
                    continue

    def _get_model_manage_id(self, model_train_id=None):
        """根据modelTrainId获取modelManageId"""
        response = self.api_base.query_model_base()
        assertions.assert_code(response.status_code, 200)
        response_data = response.json()
        model_list = response_data.get('data', {}).get('list', [])
        for model in model_list:
            if model_train_id and model.get('modelTrainId') == model_train_id:
                return model.get('modelManageId')
        pytest.fail(f"未找到匹配的modelManageId: {model_train_id}")

    @pytest.mark.parametrize("scenario", TRAINING_FLOW_SCENARIOS, ids=lambda s: s["name"])
    def test_training_flow(self, scenario, cleanup_tasks):
        """数据驱动的训练全流程，根据scenario控制分支"""
        total_start = time.time()
        task_name = f"流程驱动-{scenario['name']}-{time.strftime('%m%d%H%M%S')}"

        # ---- 上下文对象：步骤间传递数据 ----
        ctx = {
            "task_name": task_name,
            "trainTaskId": None,
            "modelTrainId": None,
            "verifyId": None,
            "modelManageId": None,
            "cut_value": scenario["cut_value"],
        }

        # ============ 步骤1：创建深度训练任务 ============
        with allure.step(f"[{scenario['name']}] 步骤1：创建深度训练任务"):
            response = self.api_comprehensive.create_deep_training_tasks(
                defectName=self.defectName,
                photoId=self.photoId_ng,
                cut=ctx["cut_value"],
                taskName=ctx["task_name"],
                classifyType=[],
                caseId="detection",
                caseName="目标检测/分割",
                create_type=1,
                iscut=True,
                remark=scenario.get("remark", "数据驱动流程测试")
            )
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

        # 检查是否只需要跑到这里
        if scenario.get("run_until_step") == 1:
            allure.attach(f"场景止步于步骤1，最终状态: 已创建", name="场景结果")
            return

        # ============ 步骤2：监控创建数据处理进度 ============
        with allure.step(f"[{scenario['name']}] 步骤2：监控创建数据处理进度"):
            ctx["trainTaskId"], _ = self.monitor.monitor_cut_progress(
                ctx["task_name"], "目标检测/分割切图处理"
            )
            cleanup_tasks(ctx["trainTaskId"])  # 注册清理

        # ============ 步骤3：追加ok图 ============
        with allure.step(f"[{scenario['name']}] 步骤3：追加ok图"):
            response = self.api_comprehensive.append_deep_training_tasks2(
                photoId=self.photoId_ok,
                sampleType="ok",
                trainId=ctx["trainTaskId"],
                datasetType=1
            )
            assertions.assert_code(response.status_code, 200)
            assertions.assert_in_text(response.json()['msg'], '成功')

        # ============ 步骤4：监控追加数据处理进度 ============
        with allure.step(f"[{scenario['name']}] 步骤4：监控追加数据处理进度"):
            ctx["trainTaskId"], _ = self.monitor.monitor_cut_progress(
                ctx["task_name"], "目标检测/分割追加OK图处理"
            )

        if scenario.get("run_until_step") == 4:
            allure.attach(f"场景止步于步骤4，最终状态: 数据就绪", name="场景结果")
            return

        # ============ 步骤5：开始模型训练 ============
        with allure.step(f"[{scenario['name']}] 步骤5：开始模型训练"):
            # 查询模型方案
            model_response = self.api_model.query_model()
            assertions.assert_code(model_response.status_code, 200)
            model_data = model_response.json()
            assertions.assert_in_text(model_data['msg'], '操作成功')

            cut_case_mapping = {768: "实例分割", 1024: "目标检测"}
            if ctx["cut_value"] not in cut_case_mapping:
                pytest.fail(f"无效的裁剪值: {ctx['cut_value']}, 预期值为1024/768")
            target_case_name = cut_case_mapping[ctx["cut_value"]]

            matched_model = None
            for model_item in model_data['data']:
                if model_item.get('name') == target_case_name:
                    matched_model = model_item
                    break
            if not matched_model:
                pytest.fail(f"模型 '{target_case_name}' 未找到")

            case_id = None
            modelCaseTemplateId = None
            for version in matched_model.get('modelVersionList', []):
                if version.get('caseName') == "Det V2":
                    case_id = version.get('caseId')
                    modelCaseTemplateId = version.get('modelCaseTemplateId')
                    break
            assertions.assert_is_not_none(case_id, f"在模型 '{target_case_name}' 中未找到caseId")
            assertions.assert_is_not_none(
                modelCaseTemplateId,
                f"在模型 '{target_case_name}' 中未找到modelCaseTemplateId"
            )

            # 查询训练机器
            machine_response = self.api_model.query_machine()
            assertions.assert_code(machine_response.status_code, 200)
            machine_data = machine_response.json()
            assertions.assert_in_text(machine_data['msg'], '操作成功')
            test_machine = next(
                (m for m in machine_data['data'] if m['name'] == self.machine_name), None
            )
            assertions.assert_is_not_none(test_machine, f"{self.machine_name}在机器列表中未找到")
            computing_power_id = test_machine['computingPowerId']
            assertions.assert_is_not_none(computing_power_id, "训练机器computingPowerId不能为空")

            # 启动训练 - 参数从scenario中读取
            train_response = self.api_model.start_train(
                "", "", case_id, -1, computing_power_id,
                scenario["train_epoch"],
                scenario["train_batch_size"],
                scenario["train_lr"],
                ctx["trainTaskId"], modelCaseTemplateId
            )
            assertions.assert_code(train_response.status_code, 200)
            assertions.assert_in_text(train_response.json()['msg'], '操作成功')

        # ============ 步骤6：监控训练进度 ============
        with allure.step(f"[{scenario['name']}] 步骤6：监控训练进度"):
            ctx["modelTrainId"], _ = self.monitor.monitor_train_progress(
                ctx["trainTaskId"], "YoloV8目标检测训练"
            )
            time.sleep(3)

        # ============ 步骤7：提交模型 ============
        with allure.step(f"[{scenario['name']}] 步骤7：提交模型"):
            submit_response = self.api_model.submit_model(
                modelName=ctx["task_name"],
                modelTrainId=ctx["modelTrainId"]
            )
            assertions.assert_code(submit_response.status_code, 200)
            self.monitor.monitor_commit_progress(ctx["trainTaskId"], "模型提交")

        # ============ 步骤8：获取verifyId ============
        with allure.step(f"[{scenario['name']}] 步骤8：获取verifyId"):
            response = self.api_model.query_train_records(trainTaskId=ctx["trainTaskId"])
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            train_list = response_data.get('data', {}).get('list', [])
            if not train_list:
                pytest.fail("未找到训练记录")

            verify_id = None
            for task in train_list:
                for record in task.get('verifyRecord', []):
                    if '验证集' in record.get('name', ''):
                        verify_id = record.get('id')
                        ctx["verifyId"] = verify_id
                        break
                if verify_id:
                    break
            assertions.assert_is_not_none(verify_id, f"未找到验证集verifyRecordID，响应数据：{response_data}")

        # ============ 步骤9-13：后处理（报表分析+样本分析+增广） ============
        with allure.step(f"[{scenario['name']}] 步骤9：报表分析"):
            self.verifyId = ctx["verifyId"]
            response = self.api_process.report_analysis(ctx["verifyId"])
            assertions.assert_code(response.status_code, 200)
            self._monitor_analysis_progress("报表分析", self.api_process.report_analysis_status)

        with allure.step(f"[{scenario['name']}] 步骤10：样本分析"):
            response = self.api_process.sample_analysis(ctx["verifyId"])
            assertions.assert_code(response.status_code, 200)
            self._monitor_analysis_progress("样本分析", self.api_process.sample_analysis_status)

        with allure.step(f"[{scenario['name']}] 步骤11：过检样本-拷贝增广"):
            with allure.step("子步骤1：查询过检样本"):
                response = self.api_process.query_over_samples(verifyId=ctx["verifyId"])
                assertions.assert_code(response.status_code, 200)
                response_data = response.json()
                assertions.assert_in_text(response_data['msg'], '成功')

                over_samples_list = response_data.get('data', {}).get('list', [])
                if not over_samples_list:
                    pytest.fail("未找到过检样本数据")

                over_sample = over_samples_list[0]
                over_sample_id = over_sample.get('id')
                over_img_name = over_sample.get('imgName')
                assertions.assert_is_not_none(over_sample_id, "过检样本id不能为空")
                assertions.assert_is_not_none(over_img_name, "过检样本imgName不能为空")

            with allure.step("子步骤2：查询过检图片GT/PRE"):
                response = self.api_process.query_gt_pre_data(
                    image_id=over_sample_id, verifyId=ctx["verifyId"]
                )
                assertions.assert_code(response.status_code, 200)
                response_data = response.json()
                assertions.assert_in_text(response_data['msg'], '成功')

                gt_pre_data = response_data.get('data', {}).get('gtAndPre', {}).get('shapes', [])
                if not isinstance(gt_pre_data, list):
                    pytest.fail(f"gt_pre_data不是一个列表: {gt_pre_data}")

                over_defect_id = None
                for item in gt_pre_data:
                    if item.get('type') == "0":
                        over_defect_id = item.get('id')
                        break
                assertions.assert_is_not_none(over_defect_id, "未找到type为0的缺陷ID")

            with allure.step("子步骤3：标记空过杀"):
                response = self.api_process.batch_mark(
                    defect_id=over_defect_id,
                    postprocess_label="kongguosha",
                    verifyId=ctx["verifyId"],
                    image_id=over_sample_id,
                    img_name=over_img_name
                )
                assertions.assert_code(response.status_code, 200)
                assertions.assert_in_text(response.json()['msg'], '成功')

            with allure.step("子步骤4：过检样本拷贝增广"):
                num = random.randint(1, 5)
                response = self.api_process.copy_to_trainset(
                    train_task_id=ctx["trainTaskId"],
                    num=num,
                    verifyId=ctx["verifyId"],
                    image_id=over_sample_id,
                    copy_type=0
                )
                assertions.assert_code(response.status_code, 200)
                assertions.assert_in_text(response.json()['msg'], '成功')

            with allure.step("子步骤5：监控过检拷贝进度"):
                self.monitor.monitor_cut_progress(ctx["task_name"], "过检样本-拷贝增广处理")

        # ============ 步骤12：漏检样本-拷贝增广 ============
        with allure.step(f"[{scenario['name']}] 步骤12：漏检样本-拷贝增广"):
            with allure.step("子步骤1：查询漏检样本"):
                response = self.api_process.query_miss_samples(verifyId=ctx["verifyId"])
                assertions.assert_code(response.status_code, 200)
                response_data = response.json()
                assertions.assert_in_text(response_data['msg'], '成功')

                miss_samples_list = response_data.get('data', {}).get('list', [])
                if not miss_samples_list:
                    pytest.fail("未找到漏检样本数据")

                miss_sample = miss_samples_list[0]
                miss_sample_id = miss_sample.get('id')
                miss_img_name = miss_sample.get('imgName')
                assertions.assert_is_not_none(miss_sample_id, "漏检样本id不能为空")
                assertions.assert_is_not_none(miss_img_name, "漏检样本imgName不能为空")

            with allure.step("子步骤2：查询漏检图片GT/PRE"):
                response = self.api_process.query_gt_pre_data(
                    image_id=miss_sample_id, verifyId=ctx["verifyId"]
                )
                assertions.assert_code(response.status_code, 200)
                response_data = response.json()
                assertions.assert_in_text(response_data['msg'], '成功')

                gt_pre_data = response_data.get('data', {}).get('gtAndPre', {}).get('shapes', [])
                if not isinstance(gt_pre_data, list):
                    pytest.fail(f"gt_pre_data不是一个列表: {gt_pre_data}")

                miss_defect_id = None
                for item in gt_pre_data:
                    if item.get('type') == "1":
                        miss_defect_id = item.get('id')
                        break
                assertions.assert_is_not_none(miss_defect_id, "未找到type为1的缺陷ID")

            with allure.step("子步骤3：标记漏检增强"):
                response = self.api_process.batch_mark(
                    defect_id=miss_defect_id,
                    postprocess_label="loujianzengqiang",
                    verifyId=ctx["verifyId"],
                    image_id=miss_sample_id,
                    img_name=miss_img_name
                )
                assertions.assert_code(response.status_code, 200)
                assertions.assert_in_text(response.json()['msg'], '成功')

            with allure.step("子步骤4：漏检样本拷贝增广"):
                num = random.randint(1, 5)
                response = self.api_process.copy_to_trainset(
                    train_task_id=ctx["trainTaskId"],
                    num=num,
                    verifyId=ctx["verifyId"],
                    image_id=miss_sample_id,
                    copy_type=1
                )
                assertions.assert_code(response.status_code, 200)
                assertions.assert_in_text(response.json()['msg'], '成功')

            with allure.step("子步骤5：监控漏检拷贝进度"):
                self.monitor.monitor_cut_progress(ctx["task_name"], "漏检样本-拷贝增广处理")

        # ============ 步骤13：错检样本-拷贝增广 ============
        with allure.step(f"[{scenario['name']}] 步骤13：错检样本-拷贝增广"):
            with allure.step("子步骤1：查询错检样本"):
                response = self.api_process.query_error_samples(verifyId=ctx["verifyId"])
                assertions.assert_code(response.status_code, 200)
                response_data = response.json()
                assertions.assert_in_text(response_data['msg'], '成功')

                error_samples_list = response_data.get('data', {}).get('list', [])
                if not error_samples_list:
                    pytest.fail("未找到错检样本数据")

                error_sample = error_samples_list[0]
                error_sample_id = error_sample.get('id')
                error_img_name = error_sample.get('imgName')
                assertions.assert_is_not_none(error_sample_id, "错检样本id不能为空")
                assertions.assert_is_not_none(error_img_name, "错检样本imgName不能为空")

            with allure.step("子步骤2：查询错检图片GT/PRE"):
                response = self.api_process.query_gt_pre_data(
                    image_id=error_sample_id, verifyId=ctx["verifyId"]
                )
                assertions.assert_code(response.status_code, 200)
                response_data = response.json()
                assertions.assert_in_text(response_data['msg'], '成功')

                gt_pre_data = response_data.get('data', {}).get('gtAndPre', {}).get('shapes', [])
                if not isinstance(gt_pre_data, list):
                    pytest.fail(f"gt_pre_data不是一个列表: {gt_pre_data}")

                error_defect_id = None
                for item in gt_pre_data:
                    if item.get('type') == "2":
                        error_defect_id = item.get('id')
                        break
                assertions.assert_is_not_none(error_defect_id, "未找到type为2的缺陷ID")

            with allure.step("子步骤3：标记错检增强"):
                response = self.api_process.batch_mark(
                    defect_id=error_defect_id,
                    postprocess_label="cuojianzengqiang",
                    verifyId=ctx["verifyId"],
                    image_id=error_sample_id,
                    img_name=error_img_name
                )
                assertions.assert_code(response.status_code, 200)
                assertions.assert_in_text(response.json()['msg'], '成功')

            with allure.step("子步骤4：错检样本拷贝增广"):
                num = random.randint(1, 5)
                response = self.api_process.copy_to_trainset(
                    train_task_id=ctx["trainTaskId"],
                    num=num,
                    verifyId=ctx["verifyId"],
                    image_id=error_sample_id,
                    copy_type=2
                )
                assertions.assert_code(response.status_code, 200)
                assertions.assert_in_text(response.json()['msg'], '成功')

            with allure.step("子步骤5：监控错检拷贝进度"):
                self.monitor.monitor_cut_progress(ctx["task_name"], "错检样本-拷贝增广处理")

        # ============ 步骤14-18：部署+撤回+删除 ============
        with allure.step(f"[{scenario['name']}] 步骤14：获取modelManageId"):
            ctx["modelManageId"] = self._get_model_manage_id(ctx["modelTrainId"])

        with allure.step(f"[{scenario['name']}] 步骤15：部署测试"):
            response = self.api_base.deploy_test(ctx["modelManageId"])
            assertions.assert_code(response.status_code, 200)
            assertions.assert_in_text(response.json()['msg'], '成功')

        with allure.step(f"[{scenario['name']}] 步骤16：监控部署测试状态"):
            def get_deployment_status(response_data):
                model_list = response_data.get('data', {}).get('list', [])
                for model in model_list:
                    if model.get('modelManageId') == ctx["modelManageId"]:
                        return model.get('status')
                return None

            self._monitor_generic_progress(
                api_call=self.api_base.query_model_base,
                get_status_func=get_deployment_status,
                in_progress_status=1,
                success_status=3,
                step_name="部署测试"
            )

        with allure.step(f"[{scenario['name']}] 步骤17：模型撤回"):
            response = self.api_base.model_withdraw(ctx["modelManageId"], 1)
            assertions.assert_code(response.status_code, 200)
            assertions.assert_in_text(response.json()['msg'], '成功')

        with allure.step(f"[{scenario['name']}] 步骤18：训练任务删除"):
            response = self.api_deep.delete_train_tasks(ctx["trainTaskId"])
            assertions.assert_code(response.status_code, 200)
            assertions.assert_in_text(response.json()['msg'], '成功')

        # 最终断言
        allure.dynamic.description(
            f"场景: {scenario['name']} | "
            f"最终状态: {scenario.get('expect_final_status', '完成')} | "
            f"总耗时: {time.strftime('%H:%M:%S', time.gmtime(time.time() - total_start))}"
        )


# ============================================================
# 测试3：终止训练 - 启动训练后调用终止接口，验证状态变为训练失败
# ============================================================
@allure.feature("综合-目标检测YoloV11-数据驱动")
@allure.story("终止训练-状态验证")
@pytest.mark.training_deep
class TestStopTrain(SharedSetupMixin):
    @classmethod
    def setup_class(cls):
        cls.setup_shared(need_model=True)

    def _monitor_stop_train_progress(self, trainTaskId, expect_status, task_description="终止训练"):
        """
        终止训练后轮询训练记录，等待 trainStatus 变为期望值（默认1=训练失败）
        :param trainTaskId: 训练任务ID
        :param expect_status: 期望的 trainStatus 值
        :param task_description: 步骤描述
        """
        status_mapping = {
            0: "训练中",
            1: "训练失败",
            2: "训练完成",
            3: "打包中",
            4: "排队中",
            5: "转onnx中",
            6: "转triton中",
        }
        start_time = time.time()
        attempt = 0

        with allure.step(f"监控{task_description}后状态"):
            while True:
                attempt += 1
                response = self.api_model.query_train_records(trainTaskId=trainTaskId)
                assertions.assert_code(response.status_code, 200)
                response_data = response.json()
                records = response_data.get('data', {}).get('list', [])

                if not records:
                    pytest.fail(f"未找到trainTaskId={trainTaskId}的训练记录")

                current_record = records[0]
                train_status = current_record.get('trainStatus')
                model_train_id = current_record.get('modelTrainId')

                elapsed = time.time() - start_time
                mins, secs = divmod(int(elapsed), 60)
                status_text = status_mapping.get(train_status, f"未知({train_status})")
                print(f"\r[{task_description}] 第{attempt}次 trainStatus={train_status}({status_text}) 已等待{mins}分{secs}秒",
                      end="", flush=True)

                if train_status == expect_status:
                    print(f"\n\033[92m{task_description}达到期望状态: {status_text}\033[0m")
                    allure.attach(
                        f"终止成功，trainStatus={train_status}({status_text})，耗时{mins}分{secs}秒",
                        name="终止训练结果"
                    )
                    return model_train_id, True

                if elapsed > self.max_wait_seconds:
                    pytest.fail(f"{task_description}超时: 等待{self.max_wait_seconds}秒，"
                                f"当前状态仍为{status_text}，期望{status_mapping.get(expect_status)}")

                time.sleep(self.poll_interval)

    @pytest.mark.parametrize("scenario", STOP_TRAIN_SCENARIOS, ids=lambda s: s["name"])
    def test_stop_train(self, scenario, cleanup_tasks):
        """开始训练后调用终止接口，验证最终状态变为训练失败"""
        task_name = f"终止训练-{scenario['name']}-{time.strftime('%m%d%H%M%S')}"
        ctx = {"trainTaskId": None, "modelTrainId": None}

        # ---- 步骤1：创建任务 ----
        with allure.step("步骤1：创建深度训练任务"):
            response = self.api_comprehensive.create_deep_training_tasks(
                defectName=self.defectName,
                photoId=self.photoId_ng,
                cut=scenario["cut_value"],
                taskName=task_name,
                classifyType=[],
                caseId="detection",
                caseName="目标检测/分割",
                create_type=1,
                iscut=True,
                remark=scenario.get("remark", "终止训练场景测试")
            )
            assertions.assert_code(response.status_code, 200)
            assertions.assert_in_text(response.json()['msg'], '成功')

        # ---- 步骤2：监控切图进度 ----
        with allure.step("步骤2：监控创建数据处理进度"):
            ctx["trainTaskId"], _ = self.monitor.monitor_cut_progress(task_name, "目标检测/分割切图处理")
            cleanup_tasks(ctx["trainTaskId"])

        # ---- 步骤3：追加OK图 ----
        with allure.step("步骤3：追加OK图"):
            response = self.api_comprehensive.append_deep_training_tasks2(
                photoId=self.photoId_ok,
                sampleType="ok",
                trainId=ctx["trainTaskId"],
                datasetType=1
            )
            assertions.assert_code(response.status_code, 200)
            assertions.assert_in_text(response.json()['msg'], '成功')

        # ---- 步骤4：监控追加进度 ----
        with allure.step("步骤4：监控追加数据处理进度"):
            ctx["trainTaskId"], _ = self.monitor.monitor_cut_progress(task_name, "目标检测/分割追加OK图处理")

        # ---- 步骤5：开始训练，获取modelTrainId ----
        with allure.step("步骤5：开始模型训练"):
            model_response = self.api_model.query_model()
            assertions.assert_code(model_response.status_code, 200)
            model_data = model_response.json()

            cut_case_mapping = {768: "实例分割", 1024: "目标检测"}
            target_case_name = cut_case_mapping[scenario["cut_value"]]
            matched_model = next(
                (m for m in model_data['data'] if m.get('name') == target_case_name), None
            )
            if not matched_model:
                pytest.fail(f"模型 '{target_case_name}' 未找到")

            case_id = None
            modelCaseTemplateId = None
            for version in matched_model.get('modelVersionList', []):
                if version.get('caseName') == "Det V2":
                    case_id = version.get('caseId')
                    modelCaseTemplateId = version.get('modelCaseTemplateId')
                    break

            machine_response = self.api_model.query_machine()
            machine_data = machine_response.json()
            test_machine = next(
                (m for m in machine_data['data'] if m['name'] == self.machine_name), None
            )
            computing_power_id = test_machine['computingPowerId']

            train_response = self.api_model.start_train(
                "", "", case_id, -1, computing_power_id,
                scenario["train_epoch"],
                scenario["train_batch_size"],
                scenario["train_lr"],
                ctx["trainTaskId"], modelCaseTemplateId
            )
            assertions.assert_code(train_response.status_code, 200)

            # 等待进入训练中（trainStatus=0），再取 modelTrainId
            start_wait = time.time()
            while True:
                rec_resp = self.api_model.query_train_records(trainTaskId=ctx["trainTaskId"])
                records = rec_resp.json().get('data', {}).get('list', [])
                if records and records[0].get('modelTrainId'):
                    ctx["modelTrainId"] = records[0]['modelTrainId']
                    break
                if time.time() - start_wait > 120:
                    pytest.fail("等待modelTrainId超时")
                time.sleep(5)

            allure.attach(f"modelTrainId: {ctx['modelTrainId']}", name="训练记录ID")

        # ---- 步骤6：调用终止训练接口 ----
        with allure.step("步骤6：调用终止训练接口"):
            stop_response = self.api_model.stop_train(ctx["modelTrainId"])
            assertions.assert_code(stop_response.status_code, 200)
            allure.attach(str(stop_response.json()), name="终止训练响应")

        # ---- 步骤7：轮询等待状态变为训练失败（trainStatus=1）----
        with allure.step(f"步骤7：监控终止后状态，期望变为trainStatus={scenario['expect_stop_train_status']}(训练失败)"):
            self._monitor_stop_train_progress(
                trainTaskId=ctx["trainTaskId"],
                expect_status=scenario["expect_stop_train_status"],
                task_description="终止训练"
            )

        allure.dynamic.description(
            f"场景: {scenario['name']} | 训练终止成功，状态变为训练失败"
        )


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--alluredir=./allure-results'])

# ============================================================
# 测试4：重复任务名称 - 验证同名任务被拒绝
# ============================================================
@allure.feature("综合-目标检测YoloV11-数据驱动")
@allure.story("异常分支-重复任务")
@pytest.mark.training_deep
class TestDuplicateTaskName(SharedSetupMixin):
    @classmethod
    def setup_class(cls):
        cls.setup_shared()

    @pytest.mark.parametrize("scenario", DUPLICATE_TASK_SCENARIOS, ids=lambda s: s["name"])
    def test_duplicate_task_name(self, scenario, cleanup_tasks):
        """
        测试：创建两个同名任务，第二个应被拒绝
        异常分支验证：系统应拒绝重复的任务名称
        """
        with allure.step(f"场景: {scenario['name']}"):
            allure.attach(
                f"用例描述: {scenario.get('remark', 'N/A')}",
                name="用例说明",
                attachment_type=allure.attachment_type.TEXT
            )

        # ---- 步骤1：创建第一个任务 ----
        with allure.step("步骤1：创建第一个训练任务"):
            task_name = f"重复测试-{time.strftime('%m%d%H%M%S')}"
            response1 = self.api_comprehensive.create_deep_training_tasks(
                defectName=self.defectName,
                photoId=self.photoId_ng,
                cut=scenario["cut_value"],
                taskName=task_name,
                classifyType=[],
                caseId="detection",
                caseName="目标检测/分割",
                create_type=1,
                iscut=True,
                remark="重复性名称测试-第一个"
            )
            assertions.assert_code(response1.status_code, 200)
            allure.attach(str(response1.json()), name="第一个任务创建响应")
            first_train_task_id, _ = self.monitor.monitor_cut_progress(task_name, "目标检测/分割切图处理")
            cleanup_tasks(first_train_task_id)

        # ---- 步骤2：用相同的名称创建第二个任务，应被拒绝 ----
        with allure.step("步骤2：用相同名称创建第二个任务，期望被拒绝"):
            with semantic_expected_failure(f"重复任务名称负向场景: {scenario['name']}"):
                response2 = self.api_comprehensive.create_deep_training_tasks(
                    defectName=self.defectName,
                    photoId=self.photoId_ng,
                    cut=scenario["cut_value"],
                    taskName=task_name,
                    classifyType=[],
                    caseId="detection",
                    caseName="目标检测/分割",
                    create_type=1,
                    iscut=True,
                    remark="重复性名称测试-第二个（应失败）"
                )
            allure.attach(str(response2.json()), name="第二个任务创建响应（期望失败）")

            # 验证失败
            if not scenario["expect_success"]:
                assert '成功' not in response2.json().get('msg', ''), \
                    f"期望创建失败但实际成功了：{response2.json()}"
                if scenario.get("expect_error"):
                    assertions.assert_in_text(response2.json().get('msg', ''), scenario["expect_error"])

        allure.dynamic.description(
            f"场景: {scenario['name']} | 重复任务名称被正确拒绝"
        )


# ============================================================
# 测试5：验证集无数据导致训练失败
# ============================================================
@allure.feature("综合-目标检测YoloV11-数据驱动")
@allure.story("异常分支-空验证集训练失败")
@pytest.mark.training_deep
class TestEmptyValidationDataset(SharedSetupMixin):
    @classmethod
    def setup_class(cls):
        cls.setup_shared(need_model=True, need_data_mgmt=True)

    @pytest.mark.parametrize("scenario", EMPTY_VALIDATION_DATASET_SCENARIOS, ids=lambda s: s["name"])
    def test_empty_validation_dataset_training_fails(self, scenario, cleanup_tasks):
        """
        测试：验证集无数据导致训练失败
        异常分支验证：移除验证集所有样本后训练应失败（trainStatus=1）
        """
        with allure.step(f"场景: {scenario['name']}"):
            allure.attach(
                f"用例描述: {scenario.get('remark', 'N/A')}",
                name="用例说明",
                attachment_type=allure.attachment_type.TEXT
            )

        ctx = {}

        # ---- 步骤1：创建任务 ----
        with allure.step("步骤1：创建训练任务"):
            task_name = f"空验证集测试-{time.strftime('%m%d%H%M%S')}"
            response = self.api_comprehensive.create_deep_training_tasks(
                defectName=self.defectName,
                photoId=self.photoId_ng,
                cut=scenario["cut_value"],
                taskName=task_name,
                classifyType=[],
                caseId="detection",
                caseName="目标检测/分割",
                create_type=1,
                iscut=True,
                remark="空验证集训练失败测试"
            )
            assertions.assert_code(response.status_code, 200)
            ctx["task_name"] = task_name
            allure.attach(f"任务名称: {ctx['task_name']}", name="训练任务")

        # ---- 步骤2：等待切图完成 ----
        with allure.step("步骤2：监控切图进度，等待完成"):
            train_task_id, _ = self.monitor.monitor_cut_progress(ctx["task_name"], "目标检测/分割切图处理")
            ctx["trainTaskId"] = train_task_id
            cleanup_tasks(ctx["trainTaskId"])
            allure.attach(f"trainTaskId: {ctx['trainTaskId']}", name="训练任务ID")

        # ---- 步骤3：追加OK图 ----
        with allure.step("步骤3：追加OK图"):
            response = self.api_comprehensive.append_deep_training_tasks2(
                photoId=self.photoId_ok,
                sampleType="ok",
                trainId=ctx["trainTaskId"],
                datasetType=1
            )
            assertions.assert_code(response.status_code, 200)

        # ---- 步骤4：等待追加OK图完成 ----
        with allure.step("步骤4：监控追加OK图进度"):
            self.monitor.monitor_cut_progress(ctx["task_name"], "目标检测/分割追加OK图处理")

        # ---- 步骤5：移除验证集所有样本 ----
        with allure.step("步骤5：移除验证集所有样本"):
            response = self.api_data_mgmt.remove_sample_verify(
                trainTaskId=ctx["trainTaskId"],
                productId=[self.api_data_mgmt.product_info_id],
                sample_id=[]
            )
            assertions.assert_code(response.status_code, 200)
            allure.attach(str(response.json()), name="移除验证集样本响应")

        # ---- 步骤6：查询模型方案并启动训练 ----
        with allure.step("步骤6：查询模型方案"):
            model_response = self.api_model.query_model()
            model_data = model_response.json()
            matched_model = None
            for model_item in model_data['data']:
                if model_item.get('name') == "目标检测":
                    matched_model = model_item
                    break
            case_id = None
            modelCaseTemplateId = None
            for version in matched_model.get('modelVersionList', []):
                if version.get('caseName') == "Det V2":
                    case_id = version.get('caseId')
                    modelCaseTemplateId = version.get('modelCaseTemplateId')
                    break

        with allure.step("步骤7：查询训练机器"):
            machine_response = self.api_model.query_machine()
            machine_data = machine_response.json()
            test_machine = next(
                (m for m in machine_data['data'] if m['name'] == self.machine_name), None
            )
            computing_power_id = test_machine['computingPowerId']

        with allure.step("步骤8：启动训练（验证集为空，预期训练失败）"):
            response = self.api_model.start_train(
                "", "", case_id, -1, computing_power_id,
                scenario["train_epoch"],
                scenario["train_batch_size"],
                scenario["train_lr"],
                ctx["trainTaskId"],
                modelCaseTemplateId
            )
            assertions.assert_code(response.status_code, 200)

        # ---- 步骤9：监控训练进度，期望最终失败 ----
        with allure.step(f"步骤9：监控训练进度，期望trainStatus={scenario['expect_train_status']}（训练失败）"):
            self._monitor_training_and_verify_failure(
                trainTaskId=ctx["trainTaskId"],
                expect_status=scenario["expect_train_status"]
            )

        allure.dynamic.description(
            f"场景: {scenario['name']} | 验证集无数据训练正确失败"
        )

    def _monitor_training_and_verify_failure(self, trainTaskId, expect_status):
        """监控训练进度，验证训练失败"""
        start_wait = time.time()
        while True:
            response = self.api_model.query_train_records(trainTaskId)
            records = response.json().get('data', {}).get('list', [])
            if records:
                train_status = records[0].get('trainStatus', -1)
                allure.attach(
                    f"trainStatus: {train_status} (期望: {expect_status})",
                    name="训练状态"
                )
                if train_status == expect_status:
                    return
            if time.time() - start_wait > self.max_wait_seconds:
                pytest.fail(f"等待训练失败超时，期望trainStatus={expect_status}")
            time.sleep(self.poll_interval)


# ============================================================
# 测试6：异常标注分析
# ============================================================
@allure.feature("综合-目标检测YoloV11-数据驱动")
@allure.story("数据管理-异常标注分析")
@pytest.mark.training_deep
class TestAbnormalAnnotationAnalysis(SharedSetupMixin):
    @classmethod
    def setup_class(cls):
        cls.setup_shared(need_data_mgmt=True)

    @pytest.mark.parametrize("scenario", ABNORMAL_ANNOTATION_ANALYSIS_SCENARIOS, ids=lambda s: s["name"])
    def test_abnormal_annotation_analysis(self, scenario, cleanup_tasks):
        """
        测试：异常标注分析场景
        创建任务→切图完成→触发训练集异常标注分析→校验任务状态从处理中变为已完成
        """
        with allure.step(f"场景: {scenario['name']}"):
            allure.attach(
                f"用例描述: {scenario.get('remark', 'N/A')}",
                name="用例说明",
                attachment_type=allure.attachment_type.TEXT
            )

        ctx = {}

        # ---- 步骤1：创建任务 ----
        with allure.step("步骤1：创建训练任务"):
            task_name = f"异常标注分析-{time.strftime('%m%d%H%M%S')}"
            response = self.api_comprehensive.create_deep_training_tasks(
                defectName=self.defectName,
                photoId=self.photoId_ng,
                cut=scenario["cut_value"],
                taskName=task_name,
                classifyType=[],
                caseId="detection",
                caseName="目标检测/分割",
                create_type=1,
                iscut=True,
                remark="异常标注分析场景测试"
            )
            assertions.assert_code(response.status_code, 200)
            assertions.assert_in_text(response.json().get('msg', ''), '成功')
            ctx["task_name"] = task_name
            allure.attach(f"任务名称: {ctx['task_name']}", name="训练任务")

        # ---- 步骤2：等待切图完成 ----
        with allure.step("步骤2：监控切图进度，等待完成"):
            train_task_id, _ = self.monitor.monitor_cut_progress(ctx["task_name"], "目标检测/分割切图处理")
            ctx["trainTaskId"] = train_task_id
            cleanup_tasks(ctx["trainTaskId"])
            allure.attach(f"trainTaskId: {ctx['trainTaskId']}", name="训练任务ID")

        # ---- 步骤3：触发训练集异常标注分析 ----
        with allure.step("步骤3：点击训练集异常标注分析"):
            response = self.api_data_mgmt.abnormal_annotation_analysis(
                datasetType=scenario["dataset_type"],
                trainTaskId=ctx["trainTaskId"]
            )
            response_data = response.json()
            assertions.assert_code(response.status_code, 200)
            assertions.assert_in_text(response_data.get('msg', ''), scenario["expect_msg"])
            allure.attach(str(response_data), name="异常标注分析响应")

        # ---- 步骤4：校验刚触发后任务状态为处理中 ----
        with allure.step("步骤4：校验异常标注分析刚触发后状态为处理中"):
            current_status = self._query_task_data_status(ctx["task_name"])
            assert current_status == scenario["expect_processing_status"], \
                f"期望异常标注分析刚触发后状态为处理中({scenario['expect_processing_status']})，实际: {current_status}"

        # ---- 步骤5：监控异常标注分析完成 ----
        with allure.step("步骤5：监控异常标注分析状态，等待已完成"):
            self.monitor.monitor_cut_progress(ctx["task_name"], "训练集异常标注分析")
            final_status = self._query_task_data_status(ctx["task_name"])
            assert final_status == scenario["expect_final_status"], \
                f"期望异常标注分析完成后状态为已完成({scenario['expect_final_status']})，实际: {final_status}"

        allure.dynamic.description(
            f"场景: {scenario['name']} | 训练集异常标注分析状态从处理中变为已完成"
        )

    def _query_task_data_status(self, task_name):
        """查询训练任务列表中的dataStatus。"""
        response = self.api_deep.query_train_tasks(task_name)
        assertions.assert_code(response.status_code, 200)
        response_data = response.json()
        task_list = response_data.get('data', {}).get('list', [])
        task = next((item for item in task_list if item.get('taskName') == task_name), None)
        if not task:
            pytest.fail(f"未找到任务: {task_name}")
        allure.attach(str(task), name="任务状态")
        return task.get('dataStatus')


# ============================================================
# 测试7：移除训练集样本并校验操作记录
# ============================================================
@allure.feature("综合-目标检测YoloV11-数据驱动")
@allure.story("数据管理-移除样本并校验操作记录")
@pytest.mark.training_deep
class TestRemoveSampleRecycle(SharedSetupMixin):
    @classmethod
    def setup_class(cls):
        cls.setup_shared(need_data_mgmt=True)

    @pytest.mark.parametrize("scenario", REMOVE_SAMPLE_RECYCLE_SCENARIOS, ids=lambda s: s["name"])
    def test_remove_sample_and_verify_record(self, scenario, cleanup_tasks):
        """
        测试：移除训练集样本并校验操作记录
        创建任务→切图完成→查询训练集首个样本→移除该样本→校验操作记录记录了该样本ID
        """
        with allure.step(f"场景: {scenario['name']}"):
            allure.attach(
                f"用例描述: {scenario.get('remark', 'N/A')}",
                name="用例说明",
                attachment_type=allure.attachment_type.TEXT
            )

        ctx = {}

        # ---- 步骤1：创建任务 ----
        with allure.step("步骤1：创建训练任务"):
            task_name = f"移除样本校验-{time.strftime('%m%d%H%M%S')}"
            response = self.api_comprehensive.create_deep_training_tasks(
                defectName=self.defectName,
                photoId=self.photoId_ng,
                cut=scenario["cut_value"],
                taskName=task_name,
                classifyType=[],
                caseId="detection",
                caseName="目标检测/分割",
                create_type=1,
                iscut=True,
                remark="移除样本并校验操作记录场景测试"
            )
            assertions.assert_code(response.status_code, 200)
            assertions.assert_in_text(response.json().get('msg', ''), '成功')
            ctx["task_name"] = task_name
            allure.attach(f"任务名称: {ctx['task_name']}", name="训练任务")

        # ---- 步骤2：等待切图完成 ----
        with allure.step("步骤2：监控切图进度，等待完成"):
            train_task_id, _ = self.monitor.monitor_cut_progress(ctx["task_name"], "目标检测/分割切图处理")
            ctx["trainTaskId"] = train_task_id
            cleanup_tasks(ctx["trainTaskId"])
            allure.attach(f"trainTaskId: {ctx['trainTaskId']}", name="训练任务ID")

        # ---- 步骤3：查询训练集列表，获取第一条样本ID ----
        with allure.step("步骤3：查询训练集列表，获取第一条样本ID"):
            response = self.api_data_mgmt.query_data_list(
                trainTaskId=ctx["trainTaskId"],
                datasetType=scenario["dataset_type"]
            )
            response_data = response.json()
            assertions.assert_code(response.status_code, 200)
            data_list = response_data.get('data', {}).get('list', [])
            if not data_list:
                pytest.fail(f"训练集列表为空，无法获取样本ID，响应: {response_data}")
            sample_id = data_list[0].get('id')
            assertions.assert_is_not_none(sample_id, "训练集第一条样本id不能为空")
            ctx["sample_id"] = sample_id
            allure.attach(str(response_data), name="训练集列表响应")
            allure.attach(f"sample_id: {ctx['sample_id']}", name="待移除样本ID")

        # ---- 步骤4：移除训练集一个样本 ----
        with allure.step("步骤4：移除训练集一个样本"):
            response = self.api_data_mgmt.remove_sample_train(
                trainTaskId=ctx["trainTaskId"],
                productId=scenario["remove_product_id"],
                sample_id=[ctx["sample_id"]]
            )
            response_data = response.json()
            assertions.assert_code(response.status_code, 200)
            assertions.assert_in_text(response_data.get('msg', ''), scenario["expect_msg"])
            allure.attach(str(response_data), name="移除训练集样本响应")

        # ---- 步骤5：查看操作记录，校验移除样本记录 ----
        with allure.step("步骤5：查看操作记录，校验移除样本记录"):
            record = self._wait_remove_operation_record(
                trainTaskId=ctx["trainTaskId"],
                datasetType=scenario["dataset_type"],
                sample_id=ctx["sample_id"],
                expect_edit_type=scenario["expect_edit_type_text"]
            )
            allure.attach(str(record), name="命中的操作记录")

        allure.dynamic.description(
            f"场景: {scenario['name']} | 移除训练集样本后操作记录校验通过"
        )

    def _wait_remove_operation_record(self, trainTaskId, datasetType, sample_id, expect_edit_type):
        """短轮询操作记录，直到第一条记录匹配本次移除样本操作。"""
        start_time = time.time()
        last_response_data = None

        while True:
            response = self.api_data_mgmt.view_operation_record(
                trainTaskId=trainTaskId,
                datasetType=datasetType
            )
            response_data = response.json()
            assertions.assert_code(response.status_code, 200)
            last_response_data = response_data
            records = response_data.get('data', {}).get('list', [])

            if records:
                first_record = records[0]
                condition_ids = self._extract_condition_ids(first_record)
                edit_type_text = first_record.get('editTypeText')
                allure.attach(str(response_data), name="操作记录响应")

                if edit_type_text == expect_edit_type and condition_ids and str(condition_ids[0]) == str(sample_id):
                    return first_record

            if time.time() - start_time > 60:
                pytest.fail(
                    f"等待移除样本操作记录超时，期望editTypeText={expect_edit_type}, "
                    f"sample_id={sample_id}, 最后响应={last_response_data}"
                )
            time.sleep(3)

    @staticmethod
    def _extract_condition_ids(record):
        condition = record.get('condition') or {}
        if isinstance(condition, str):
            try:
                condition = json.loads(condition)
            except json.JSONDecodeError:
                try:
                    condition = ast.literal_eval(condition)
                except (ValueError, SyntaxError):
                    pytest.fail(f"操作记录condition无法解析: {condition}")
        if not isinstance(condition, dict):
            pytest.fail(f"操作记录condition不是对象: {condition}")
        return condition.get('ids', [])


# ============================================================
# 测试8：导出训练集样本
# ============================================================
@allure.feature("综合-目标检测YoloV11-数据驱动")
@allure.story("数据管理-导出训练集样本")
@pytest.mark.training_deep
class TestExportSample(SharedSetupMixin):
    @classmethod
    def setup_class(cls):
        cls.setup_shared(need_data_mgmt=True)

    @pytest.mark.parametrize("scenario", EXPORT_SAMPLE_SCENARIOS, ids=lambda s: s["name"])
    def test_export_train_sample(self, scenario, cleanup_tasks):
        """
        测试：导出训练集样本
        创建任务→切图完成→导出训练集样本→校验响应data包含导出路径
        """
        with allure.step(f"场景: {scenario['name']}"):
            allure.attach(
                f"用例描述: {scenario.get('remark', 'N/A')}",
                name="用例说明",
                attachment_type=allure.attachment_type.TEXT
            )

        ctx = {}

        # ---- 步骤1：创建任务 ----
        with allure.step("步骤1：创建训练任务"):
            task_name = f"导出样本-{time.strftime('%m%d%H%M%S')}"
            response = self.api_comprehensive.create_deep_training_tasks(
                defectName=self.defectName,
                photoId=self.photoId_ng,
                cut=scenario["cut_value"],
                taskName=task_name,
                classifyType=[],
                caseId="detection",
                caseName="目标检测/分割",
                create_type=1,
                iscut=True,
                remark="导出训练集样本场景测试"
            )
            assertions.assert_code(response.status_code, 200)
            assertions.assert_in_text(response.json().get('msg', ''), '成功')
            ctx["task_name"] = task_name
            allure.attach(f"任务名称: {ctx['task_name']}", name="训练任务")

        # ---- 步骤2：等待切图完成 ----
        with allure.step("步骤2：监控切图进度，等待完成"):
            train_task_id, _ = self.monitor.monitor_cut_progress(ctx["task_name"], "目标检测/分割切图处理")
            ctx["trainTaskId"] = train_task_id
            cleanup_tasks(ctx["trainTaskId"])
            allure.attach(f"trainTaskId: {ctx['trainTaskId']}", name="训练任务ID")

        # ---- 步骤3：导出训练集样本 ----
        with allure.step("步骤3：导出训练集样本"):
            response = self.api_data_mgmt.export_sample(
                datasetType=scenario["dataset_type"],
                trainTaskId=ctx["trainTaskId"]
            )
            response_data = response.json()
            assertions.assert_code(response.status_code, 200)
            assertions.assert_in_text(response_data.get('msg', ''), scenario["expect_msg"])
            export_data = response_data.get('data')
            assert export_data not in (None, "", [], {}), f"导出样本响应data为空: {response_data}"
            assert self._contains_export_path(export_data), f"导出样本响应data未找到路径地址: {response_data}"
            allure.attach(str(response_data), name="导出训练集样本响应")

        allure.dynamic.description(
            f"场景: {scenario['name']} | 导出训练集样本成功并返回路径"
        )

    @classmethod
    def _contains_export_path(cls, value):
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, dict):
            return any(cls._contains_export_path(item) for item in value.values())
        if isinstance(value, list):
            return any(cls._contains_export_path(item) for item in value)
        return False


# ============================================================
# 测试9：删除任务生命周期合并场景（无后处理）
# ============================================================
@allure.feature("综合-目标检测YoloV11-数据驱动")
@allure.story("异常分支-删除任务生命周期合并")
@pytest.mark.training_deep
class TestDeleteSubmittedNoPostProcess(SharedSetupMixin):
    @classmethod
    def setup_class(cls):
        cls.setup_shared(need_model=True, need_base=True)

    @pytest.mark.parametrize("scenario", DELETE_SUBMITTED_NO_POSTPROCESS_SCENARIOS, ids=lambda s: s["name"])
    def test_delete_submitted_task_clean_flow(self, scenario, cleanup_tasks):
        """
        测试：删除任务生命周期合并场景
        合并覆盖原三条独立场景：
        1. 删除已提交任务-清洁流程无后处理
        2. 删除已完成的任务
        3. 删除已创建的任务
        """
        with allure.step(f"场景: {scenario['name']}"):
            allure.attach(
                f"用例描述: {scenario.get('remark', 'N/A')}",
                name="用例说明",
                attachment_type=allure.attachment_type.TEXT
            )
            allure.attach(
                "\n".join(scenario.get("covers", [])),
                name="覆盖场景",
                attachment_type=allure.attachment_type.TEXT
            )

        ctx = {}

        # ---- 步骤1：创建任务 ----
        with allure.step("步骤1：创建训练任务"):
            task_name = f"清洁删除测试-{time.strftime('%m%d%H%M%S')}"
            response = self.api_comprehensive.create_deep_training_tasks(
                defectName=self.defectName,
                photoId=self.photoId_ng,
                cut=scenario["cut_value"],
                taskName=task_name,
                classifyType=[],
                caseId="detection",
                caseName="目标检测/分割",
                create_type=1,
                iscut=True,
                remark="删除已提交任务清洁流程测试"
            )
            assertions.assert_code(response.status_code, 200)
            ctx["task_name"] = task_name
            allure.attach(f"任务名称: {ctx['task_name']}", name="训练任务")

        # ---- 步骤2：等待切图完成 ----
        with allure.step("步骤2：监控切图进度"):
            train_task_id, _ = self.monitor.monitor_cut_progress(ctx["task_name"], "目标检测/分割切图处理")
            ctx["trainTaskId"] = train_task_id
            cleanup_tasks(ctx["trainTaskId"])
            allure.attach(f"trainTaskId: {ctx['trainTaskId']}", name="训练任务ID")

        # ---- 步骤3：追加OK图 ----
        with allure.step("步骤3：追加OK图"):
            response = self.api_comprehensive.append_deep_training_tasks2(
                photoId=self.photoId_ok,
                sampleType="ok",
                trainId=ctx["trainTaskId"],
                datasetType=1
            )
            assertions.assert_code(response.status_code, 200)

        # ---- 步骤4：等待追加OK图完成 ----
        with allure.step("步骤4：监控追加OK图进度"):
            self.monitor.monitor_cut_progress(ctx["task_name"], "目标检测/分割追加OK图处理")

        # ---- 步骤5：启动训练 ----
        with allure.step("步骤5：查询模型方案并启动训练"):
            model_response = self.api_model.query_model()
            model_data = model_response.json()
            matched_model = None
            for model_item in model_data['data']:
                if model_item.get('name') == "目标检测":
                    matched_model = model_item
                    break
            case_id = None
            modelCaseTemplateId = None
            for version in matched_model.get('modelVersionList', []):
                if version.get('caseName') == "Det V2":
                    case_id = version.get('caseId')
                    modelCaseTemplateId = version.get('modelCaseTemplateId')
                    break

            machine_response = self.api_model.query_machine()
            machine_data = machine_response.json()
            test_machine = next(
                (m for m in machine_data['data'] if m['name'] == self.machine_name), None
            )
            computing_power_id = test_machine['computingPowerId']

            response = self.api_model.start_train(
                "", "", case_id, -1, computing_power_id,
                scenario["train_epoch"],
                scenario["train_batch_size"],
                scenario["train_lr"],
                ctx["trainTaskId"],
                modelCaseTemplateId
            )
            assertions.assert_code(response.status_code, 200)

        # ---- 步骤6：等待训练完成，获取modelTrainId ----
        with allure.step("步骤6：监控训练进度，等待完成"):
            model_train_id, _ = self.monitor.monitor_train_progress(ctx["trainTaskId"], "目标检测训练")
            ctx["modelTrainId"] = model_train_id

        # ---- 步骤7：提交模型 ----
        with allure.step("步骤7：提交模型到模型库"):
            response = self.api_model.submit_model(
                modelName=ctx["task_name"],
                modelTrainId=ctx["modelTrainId"]
            )
            assertions.assert_code(response.status_code, 200)

        # ---- 步骤8：监控提交进度，等待完成 ----
        with allure.step("步骤8：监控模型提交进度"):
            self.monitor.monitor_commit_progress(ctx["trainTaskId"], "模型提交")

        # ---- 步骤9：尝试删除已提交的任务，期望失败 ----
        with allure.step("步骤9：尝试删除已提交的任务，期望失败"):
            with semantic_expected_failure("已提交训练任务首次删除应被业务拒绝"):
                response = self.api_deep.delete_train_tasks(ctx["trainTaskId"])
            response_data = response.json()
            allure.attach(str(response_data), name="第一次删除响应（期望失败）")

            assert '成功' not in response_data.get('msg', ''), \
                f"期望删除失败但实际成功了：{response_data}"
            if scenario.get("expect_first_delete_error"):
                assertions.assert_in_text(response_data.get('msg', ''), scenario["expect_first_delete_error"])

        # ---- 步骤10：查询模型信息，找到modelManageId ----
        with allure.step("步骤10：查询模型库，找到modelManageId"):
            record_response = self.api_model.query_train_records(trainTaskId=ctx["trainTaskId"])
            records = record_response.json().get('data', {}).get('list', [])
            if not records:
                pytest.fail("查询训练记录失败")
            model_train_id = records[0].get('modelTrainId')

            base_response = self.api_base.query_model_base()
            model_list = base_response.json().get('data', {}).get('list', [])
            model_manage_id = next(
                (m.get('modelManageId') for m in model_list
                 if m.get('modelTrainId') == model_train_id),
                None
            )
            if not model_manage_id:
                pytest.fail("找不到modelManageId")
            ctx["modelManageId"] = model_manage_id
            allure.attach(f"modelManageId: {model_manage_id}", name="模型管理ID")

        # ---- 步骤11：撤回模型 ----
        with allure.step("步骤11：撤回已提交的模型"):
            response = self.api_base.model_withdraw(ctx["modelManageId"], 1)
            assertions.assert_code(response.status_code, 200)
            allure.attach(str(response.json()), name="模型撤回响应")

        # ---- 步骤12：再次删除任务，期望成功 ----
        with allure.step("步骤12：撤回后再次删除任务，期望成功"):
            response = self.api_deep.delete_train_tasks(ctx["trainTaskId"])
            response_data = response.json()
            allure.attach(str(response_data), name="第二次删除响应（期望成功）")

            if scenario.get("expect_second_delete_succeeds"):
                assertions.assert_code(response.status_code, 200)
                assertions.assert_in_text(response_data.get('msg', ''), '成功')

        allure.dynamic.description(
            f"场景: {scenario['name']} | 已提交任务清洁删除流程完成"
        )

