"""
单产品-3D标注流程
"""
import time
import pytest
import allure
from common import Assert
from datetime import datetime, timedelta
from common.Request_Response import ApiClient
from common.client_factory import create_lazy_yixiu_client
from api import api_login, api_3D_label, api_other_sample_library, api_product_label

assertions = Assert.Assertions()
time_str = time.strftime("%Y%m%d%H%M%S", time.localtime())

# 计算日期参数
current_date = datetime.now()
endDateTime = current_date.strftime("%Y-%m-%d")
startDateTime = (current_date - timedelta(days=1)).strftime("%Y-%m-%d")

# 全局懒加载客户端：仅在首次发送请求时才进行身份认证。
global_client = create_lazy_yixiu_client()


@pytest.mark.annotation_3d
@allure.feature("场景：单产品-3D标注&检验GRPC推图数据")
class Test3DLabel:
    @classmethod
    def setup_class(cls):
        """初始化接口封装实例"""
        cls.api_other_sample = api_other_sample_library.ApiOtherSample(global_client)
        cls.api_3d_label = api_3D_label.Api3DLabel(global_client)
        cls.api_product_label = api_product_label.ApiProductLabel(global_client)
        cls.task_name = None
        cls.sampledatasyncid_1 = None
        cls.sampledatasyncid_2 = None
        cls.sampledatasyncid_3 = None
        cls.dimensionTaskId = None
        cls.dimensionDataId_1 = None
        cls.dimensionDataId_2 = None
        cls.label_3d_1 = None
        cls.label_3d_2 = None

    def verify_task_status(self, expected_status, status_name):
        """
        验证标注任务状态是否符合预期
        """
        # 查询任务状态
        response = self.api_3d_label.query_3d_task()
        assertions.assert_code(response.status_code, 200)
        response_data = response.json()
        assertions.assert_in_text(response_data['msg'], '成功')

        # 查找指定任务
        task_list = response_data.get('data', {}).get('list', [])
        target_task = None
        for task in task_list:
            if task.get('taskName') == self.task_name:
                target_task = task
                break

        if target_task:
            current_status = target_task.get('taskStatus')
            # 记录状态信息到报告
            status_info = (
                f"任务名称: {self.task_name}\n"
                f"当前状态: {current_status} ({self.get_status_name(current_status)})\n"
                f"预期状态: {expected_status} ({status_name})"
            )
            allure.attach(status_info,
                          name="任务状态检查",
                          attachment_type=allure.attachment_type.TEXT)

            if current_status == expected_status:
                allure.attach(f"状态验证成功: 当前状态符合预期({status_name})",
                              name="状态验证结果",
                              attachment_type=allure.attachment_type.TEXT)
                return True
            else:
                error_msg = f"错误: 状态不符合预期！当前状态: {self.get_status_name(current_status)}，预期状态: {status_name}"
                allure.attach(error_msg,
                              name="状态验证失败",
                              attachment_type=allure.attachment_type.TEXT)
                pytest.fail(error_msg)
        else:
            error_msg = f"错误: 未找到任务名称为 '{self.task_name}' 的任务"
            allure.attach(error_msg,
                          name="任务查找失败",
                          attachment_type=allure.attachment_type.TEXT)
            pytest.fail(error_msg)

    def get_status_name(self, status_code):
        status_map = {
            1: "未开始",
            2: "进行中",
            3: "待复核",
            4: "复核通过",
            5: "已提交",
            7: "待重标",
            8: "复核未通过",
            9: "辅助标注中",
            10: "辅助标注完成"
        }
        return status_map.get(status_code, f"未知状态({status_code})")

    @pytest.mark.order(1)
    @allure.story("检验各页面推图数据")
    def test_query_push_data(self):
        with allure.step("步骤1：检验标准样本库-标准样") as step1:
            response = self.api_other_sample.query_standard_sample(startDateTime, endDateTime, "standard")
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            # 新增数据存在性检查并写入Allure报告
            sample_data = response_data.get('data', {}).get('list', [])
            if len(sample_data) > 0:
                allure.dynamic.description(f"标准样数据存在: 共 {len(sample_data)} 条记录")
            else:
                allure.attach("标准样数据为空，推图失败", name="数据检查结果",
                              attachment_type=allure.attachment_type.TEXT)
                pytest.fail("标准样数据为空，推图失败")

        with allure.step("步骤2：检验标准样本库-缺陷料") as step2:
            response = self.api_other_sample.query_standard_sample(startDateTime, endDateTime, "defects")
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            # 新增数据存在性检查并写入Allure报告
            defect_data = response_data.get('data', {}).get('list', [])
            if len(defect_data) > 0:
                allure.dynamic.description(f"缺陷料数据存在: 共 {len(defect_data)} 条记录")
            else:
                allure.attach("缺陷料数据为空，推图失败", name="数据检查结果",
                              attachment_type=allure.attachment_type.TEXT)
                pytest.fail("缺陷料数据为空，推图失败")

        with allure.step("步骤3：检验限度样本库-标准限度样") as step3:
            response = self.api_other_sample.query_limit_sample()
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            # 新增数据存在性检查并写入Allure报告
            limit_data = response_data.get('data', {}).get('list', [])
            if len(limit_data) > 0:
                allure.dynamic.description(f"标准限度样数据存在: 共 {len(limit_data)} 条记录")
            else:
                allure.attach("标准限度样数据为空，推图失败", name="数据检查结果",
                              attachment_type=allure.attachment_type.TEXT)
                pytest.fail("标准限度样数据为空，推图失败")

        with allure.step("步骤4：检验抽检样本库") as step4:
            response = self.api_other_sample.query_sample_check_sample(startDateTime, endDateTime)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            # 新增数据存在性检查并写入Allure报告
            check_data = response_data.get('data', {}).get('list', [])
            if len(check_data) > 0:
                allure.dynamic.description(f"抽检样本数据存在: 共 {len(check_data)} 条记录")
            else:
                allure.attach("抽检样本数据为空，推图失败", name="数据检查结果",
                              attachment_type=allure.attachment_type.TEXT)
                pytest.fail("抽检样本数据为空，推图失败")

    @pytest.mark.order(2)
    @allure.story("3D标注")
    def test_3d_label(self):
        with allure.step("步骤1：查询3D样本库") as step1:
            response = self.api_3d_label.query_3d_sample(startDateTime, endDateTime, "", None, 1)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            # 提取前三条数据的sampleDataSyncId
            sample_list = response_data.get('data', {}).get('list', [])
            if len(sample_list) >= 3:
                # 赋值给类变量
                Test3DLabel.sampledatasyncid_1 = sample_list[0].get('sampleDataSyncId')
                Test3DLabel.sampledatasyncid_2 = sample_list[1].get('sampleDataSyncId')
                Test3DLabel.sampledatasyncid_3 = sample_list[2].get('sampleDataSyncId')

                # 记录提取的数据到Allure报告
                extracted_data = (
                    f"提取的前三条sampleDataSyncIexample/local-input.zip"
                    f"1. {Test3DLabel.sampledatasyncid_1}\n"
                    f"2. {Test3DLabel.sampledatasyncid_2}\n"
                    f"3. {Test3DLabel.sampledatasyncid_3}"
                )
                allure.attach(extracted_data,
                              name="提取的sampleDataSyncId",
                              attachment_type=allure.attachment_type.TEXT)
            else:
                allure.attach("警告: 响应数据不足3条，无法提取全部ID",
                              name="数据提取警告",
                              attachment_type=allure.attachment_type.TEXT)

        with allure.step("步骤2：分拣3D样本") as step2:
            # 定义分拣任务列表: (sampleDataSyncId, 分拣结果只能是"ok"或"ng")
            sorting_tasks = [
                (self.sampledatasyncid_1, "ng"),
                (self.sampledatasyncid_2, "ng"),
                (self.sampledatasyncid_3, "ok")
            ]

            # 遍历任务列表执行分拣
            for idx, (sample_id, label) in enumerate(sorting_tasks, 1):
                # 使用allure子步骤记录每个分拣任务
                with allure.step(f"分拣任务{idx}: sampleDataSyncId={sample_id}, label={label}"):
                    response = self.api_3d_label.sort_3d_sample(sample_id, label)
                    assertions.assert_code(response.status_code, 200)
                    response_data = response.json()
                    assertions.assert_in_text(response_data['msg'], '成功')

                    # 记录分拣结果到报告
                    allure.attach(
                        f"样本ID: {sample_id}\n分拣结果: {label}\n响应消息: {response_data['msg']}",
                        name=f"分拣任务{idx}结果",
                        attachment_type=allure.attachment_type.TEXT
                    )

        with allure.step("步骤3：创建3D标注任务") as step3:
            taskname = f"接口自动化标注-{time_str}"
            # 记录任务创建参数
            task_params = (
                f"任务名称: {taskname}\n"
                f"样本ID: {self.sampledatasyncid_1}\n"
            )
            allure.attach(task_params, name="创建标注任务参数", attachment_type=allure.attachment_type.TEXT)

            response = self.api_3d_label.create_3d_label_task(taskname, startDateTime, endDateTime,
                                                              [self.sampledatasyncid_1])
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')
            Test3DLabel.task_name = f"{taskname}-1"

        with allure.step("步骤4：查询3D标注任务的TaskId") as step4:
            response = self.api_3d_label.query_append_3d_task()
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            # 提取任务列表
            task_list = response_data.get('data', [])
            dimension_task_id = None

            # 查找匹配的任务
            for task in task_list:
                if task.get('name') == self.task_name:
                    dimension_task_id = task.get('code')
                    break

            # 处理结果
            if dimension_task_id:
                # 赋值给类变量
                Test3DLabel.dimensionTaskId = dimension_task_id

                # 记录到报告
                allure.attach(
                    f"找到任务: {self.task_name}\n"
                    f"dimensionTaskId: {dimension_task_id}",
                    name="任务匹配结果",
                    attachment_type=allure.attachment_type.TEXT
                )
            else:
                # 记录错误信息
                error_msg = f"错误: 未找到名称为 '{self.task_name}' 的3D标注任务"
                allure.attach(error_msg, name="任务查找失败", attachment_type=allure.attachment_type.TEXT)

                # 抛出异常
                pytest.fail(error_msg)

        with allure.step("步骤5：追加3D标注任务") as step5:
            # 记录追加任务参数
            append_params = (
                f"任务ID: {self.dimensionTaskId}\n"
                f"样本ID: {self.sampledatasyncid_2}\n"
            )
            allure.attach(append_params, name="追加3D标注任务参数", attachment_type=allure.attachment_type.TEXT)

            response = self.api_3d_label.append_3d_label_task(startDateTime, endDateTime, [self.sampledatasyncid_2],
                                                              self.dimensionTaskId)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

        with allure.step("步骤6：ok样本创建&提交3D数据集") as step6:
            # 记录数据集参数
            dataset_params = (
                f"数据集名称: 接口自动化ok图-{time_str}\n"
                f"样本ID: {self.sampledatasyncid_3}\n"
            )
            allure.attach(dataset_params, name="创建数据集参数", attachment_type=allure.attachment_type.TEXT)

            response = self.api_3d_label.ok_graph_create_dataset(f"接口自动化ok图-{time_str}", startDateTime,
                                                                 endDateTime, [self.sampledatasyncid_3])
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

        with allure.step("步骤7：查询3D数据集管理") as step7:
            response = self.api_3d_label.query_3d_dataset()
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            # 提取数据集列表
            dataset_list = response_data.get('data', {}).get('list', [])
            ok_dataset_name = f"接口自动化ok图-{time_str}-train"
            target_dataset = None

            # 查找匹配的数据集
            for dataset in dataset_list:
                if dataset.get('name') == ok_dataset_name:
                    target_dataset = dataset
                    break

            # 处理结果
            if target_dataset:
                # 获取状态和ID
                dataset_status = target_dataset.get('status')
                dataset_id = target_dataset.get('datasetId')

                # 记录数据集信息到报告
                dataset_info = (
                    f"数据集名称: {ok_dataset_name}\n"
                    f"状态: {dataset_status}\n"
                    f"预期状态: 1 (已提交)"
                )
                allure.attach(dataset_info,
                              name="数据集状态检查",
                              attachment_type=allure.attachment_type.TEXT)

                # 验证状态
                if dataset_status == 1:
                    allure.attach(f"状态验证成功: 数据集状态为'已提交'",
                                  name="状态验证结果",
                                  attachment_type=allure.attachment_type.TEXT)

                    # 保存datasetId用于后续步骤
                    Test3DLabel.ok_dataset_id = dataset_id

                    # 记录datasetId
                    id_info = f"成功获取datasetId: {dataset_id}"
                    allure.attach(id_info,
                                  name="datasetId提取",
                                  attachment_type=allure.attachment_type.TEXT)
                else:
                    # 状态异常处理
                    status_map = {
                        2: "已撤回",
                        6: "已发起重标"
                    }
                    status_name = status_map.get(dataset_status, f"未知状态({dataset_status})")

                    error_msg = f"错误: ok数据集状态异常！当前状态: {status_name}，预期状态: 1 (已提交)"
                    allure.attach(error_msg,
                                  name="状态验证失败",
                                  attachment_type=allure.attachment_type.TEXT)
                    pytest.fail(error_msg)
            else:
                error_msg = f"错误: 未找到名称为 '{ok_dataset_name}' 的数据集"
                allure.attach(error_msg,
                              name="数据集查找失败",
                              attachment_type=allure.attachment_type.TEXT)
                pytest.fail(error_msg)

        with allure.step("步骤8：撤回ok3D样本") as step8:
            # 检查是否成功获取了datasetId
            if hasattr(Test3DLabel, 'ok_dataset_id') and Test3DLabel.ok_dataset_id:
                # 记录撤回参数
                withdraw_params = (
                    f"数据集ID: {Test3DLabel.ok_dataset_id}\n"
                    f"数据集名称: 接口自动化ok图-{time_str}"
                )
                allure.attach(withdraw_params,
                              name="撤回参数",
                              attachment_type=allure.attachment_type.TEXT)

                response = self.api_3d_label.dataset_3d_withdraw(Test3DLabel.ok_dataset_id)
                assertions.assert_code(response.status_code, 200)
                response_data = response.json()
                assertions.assert_in_text(response_data['msg'], '成功')

                # 记录撤回结果
                allure.attach(f"撤回结果: {response_data['msg']}",
                              name="样本撤回完成",
                              attachment_type=allure.attachment_type.TEXT)

                # 添加状态验证步骤
                with allure.step("子步骤1：验证数据集状态已更新为'已撤回'") as step8_1:
                    # 重新查询数据集状态
                    response = self.api_3d_label.query_3d_dataset()
                    assertions.assert_code(response.status_code, 200)
                    response_data = response.json()
                    assertions.assert_in_text(response_data['msg'], '成功')

                    # 查找目标数据集
                    dataset_list = response_data.get('data', {}).get('list', [])
                    target_dataset = None
                    for dataset in dataset_list:
                        if dataset.get('datasetId') == Test3DLabel.ok_dataset_id:
                            target_dataset = dataset
                            break

                    if target_dataset:
                        # 获取更新后的状态
                        updated_status = target_dataset.get('status')

                        # 记录状态信息
                        status_info = (
                            f"数据集ID: {Test3DLabel.ok_dataset_id}\n"
                            f"数据集名称: 接口自动化ok图-{time_str}\n"
                            f"当前状态: {updated_status}\n"
                            f"预期状态: 2 (已撤回)"
                        )
                        allure.attach(status_info,
                                      name="数据集状态验证",
                                      attachment_type=allure.attachment_type.TEXT)

                        # 验证状态
                        if updated_status == 2:
                            allure.attach("状态验证成功: 数据集已成功撤回",
                                          name="状态验证结果",
                                          attachment_type=allure.attachment_type.TEXT)
                        else:
                            # 状态异常处理
                            status_map = {
                                1: "已提交",
                                2: "已撤回",
                                6: "已发起重标"
                            }
                            status_name = status_map.get(updated_status, f"未知状态({updated_status})")

                            error_msg = f"错误: 数据集状态异常！当前状态: {status_name}，预期状态: 2 (已撤回)"
                            allure.attach(error_msg,
                                          name="状态验证失败",
                                          attachment_type=allure.attachment_type.TEXT)
                            pytest.fail(error_msg)
                    else:
                        error_msg = f"错误: 未找到数据集ID为 '{Test3DLabel.ok_dataset_id}' 的数据集"
                        allure.attach(error_msg,
                                      name="数据集查找失败",
                                      attachment_type=allure.attachment_type.TEXT)
                        pytest.fail(error_msg)
            else:
                error_msg = "错误: 缺少有效的datasetId，无法执行撤回操作"
                allure.attach(error_msg,
                              name="撤回失败",
                              attachment_type=allure.attachment_type.TEXT)
                pytest.fail(error_msg)

        with allure.step("步骤9：查询3D标注任务是否存在") as step9:
            response = self.api_3d_label.query_3d_task()
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            # 检查任务列表中是否存在指定任务名的任务
            task_list = response_data.get('data', {}).get('list', [])
            task_exists = any(task.get('taskName') == self.task_name for task in task_list)

            if not task_exists:
                error_msg = f"错误: 未找到任务名称为 '{self.task_name}' 的3D标注任务"
                allure.attach(error_msg,
                              name="3D标注任务查找失败",
                              attachment_type=allure.attachment_type.TEXT)
                pytest.fail(error_msg)
            else:
                allure.attach(f"成功找到3D标注任务: {self.task_name}",
                              name="3D标注任务验证结果",
                              attachment_type=allure.attachment_type.TEXT)

        with allure.step("步骤10：开始标注") as step10:
            response = self.api_3d_label.change_3d_task_status(Test3DLabel.dimensionTaskId)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            self.verify_task_status(2, "进行中")

        with allure.step("步骤11：查询3D标注样本获取dimensionDataId") as step11:
            response = self.api_3d_label.query_3d_dimensiondataid(Test3DLabel.dimensionTaskId)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            # 获取前两条数据的dimensionDataId
            sample_list = response_data.get('data', {})
            if len(sample_list) >= 2:
                Test3DLabel.dimensionDataId_1 = sample_list[0].get('dimensionDataId')
                Test3DLabel.dimensionDataId_2 = sample_list[1].get('dimensionDataId')

                # 记录到Allure报告
                extracted_data = (
                    f"提取的前两条dimensionDataIexample/local-input.zip"
                    f"1. {Test3DLabel.dimensionDataId_1}\n"
                    f"2. {Test3DLabel.dimensionDataId_2}"
                )
                allure.attach(extracted_data,
                              name="提取的dimensionDataId",
                              attachment_type=allure.attachment_type.TEXT)
            else:
                error_msg = "错误: 响应数据不足2条，无法提取全部dimensionDataId"
                allure.attach(error_msg,
                              name="数据提取失败",
                              attachment_type=allure.attachment_type.TEXT)
                pytest.fail(error_msg)

        with allure.step("步骤12：获取标注标签") as step12:
            response = self.api_3d_label.query_3d_label()
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            # 提取前两条数据的labelName值
            label_data = response_data.get('data', [])

            # 检查是否有足够的标签数据
            if len(label_data) >= 2:
                Test3DLabel.label_3d_1 = label_data[0].get('labelName')
                Test3DLabel.label_3d_2 = label_data[1].get('labelName')
            else:
                # 标签数据不足，需要添加产品标签
                allure.attach(f"检测到标签数据不足，当前数据量: {len(label_data)}，需要至少2条数据",
                              name="标签数据检查",
                              attachment_type=allure.attachment_type.TEXT)

                with allure.step("子步骤1：添加产品标签") as substep1:
                    add_response = self.api_product_label.add_product_label()
                    assertions.assert_code(add_response.status_code, 200)
                    add_response_data = add_response.json()
                    assertions.assert_in_text(add_response_data['msg'], '成功')

                    allure.attach(f"添加产品标签结果: {add_response_data['msg']}",
                                  name="添加产品标签结果",
                                  attachment_type=allure.attachment_type.TEXT)

                with allure.step("子步骤2：查询产品标签") as substep2:
                    query_response = self.api_product_label.query_product_label()
                    assertions.assert_code(query_response.status_code, 200)
                    query_response_data = query_response.json()
                    assertions.assert_in_text(query_response_data['msg'], '成功')

                    label_list = query_response_data.get('data', {}).get('list', [])
                    target_label_data = None
                    for item in label_list:
                        if item.get('labelName') == 'suokong':
                            target_label_data = item
                            break

                    if target_label_data:
                        priority = target_label_data.get('priority')
                        label_id = target_label_data.get('labelId')

                        # 记录提取的数据
                        extracted_info = (
                            f"找到labelName为'suokong'的数据:\n"
                            f"priority: {priority}\n"
                            f"labelId: {label_id}"
                        )
                        allure.attach(extracted_info,
                                      name="提取的标签数据",
                                      attachment_type=allure.attachment_type.TEXT)
                    else:
                        error_msg = "错误: 未找到labelName为'suokong'的标签数据"
                        allure.attach(error_msg,
                                      name="查询标签失败",
                                      attachment_type=allure.attachment_type.TEXT)
                        pytest.fail(error_msg)

                with allure.step("子步骤3：修改产品标签") as substep3:
                    if target_label_data:
                        modify_response = self.api_product_label.modify_product_label(priority, label_id)
                        assertions.assert_code(modify_response.status_code, 200)
                        modify_response_data = modify_response.json()
                        assertions.assert_in_text(modify_response_data['msg'], '成功')

                        allure.attach(f"修改产品标签结果: {modify_response_data['msg']}",
                                      name="修改产品标签结果",
                                      attachment_type=allure.attachment_type.TEXT)
                    else:
                        error_msg = "错误: 无法执行修改操作，因为未找到labelName为'suokong'的标签数据"
                        allure.attach(error_msg,
                                      name="修改标签失败",
                                      attachment_type=allure.attachment_type.TEXT)
                        pytest.fail(error_msg)

                with allure.step("子步骤4：重新获取标注标签") as requery_step:
                    response = self.api_3d_label.query_3d_label()
                    assertions.assert_code(response.status_code, 200)
                    response_data = response.json()
                    assertions.assert_in_text(response_data['msg'], '成功')

                    # 重新提取前两条数据的labelName值
                    label_data = response_data.get('data', [])
                    if len(label_data) >= 2:
                        Test3DLabel.label_3d_1 = label_data[0].get('labelName')
                        Test3DLabel.label_3d_2 = label_data[1].get('labelName')

                        # 记录提取的标签名称到Allure报告
                        extracted_labels = (
                            f"重新提取的前两条labelNamexample/local-input.zip"
                            f"1. {Test3DLabel.label_3d_1}\n"
                            f"2. {Test3DLabel.label_3d_2}"
                        )
                        allure.attach(extracted_labels,
                                      name="重新提取的labelName",
                                      attachment_type=allure.attachment_type.TEXT)
                    else:
                        error_msg = f"错误: 重新添加标签后仍未提取到足够的标签数据，当前数据量: {len(label_data)}"
                        allure.attach(error_msg,
                                      name="标签数据提取失败",
                                      attachment_type=allure.attachment_type.TEXT)
                        pytest.fail(error_msg)

            # 记录提取的标签名称到Allure报告
            extracted_labels = (
                f"提取的前两条labelNamexample/local-input.zip"
                f"1. {Test3DLabel.label_3d_1}\n"
                f"2. {Test3DLabel.label_3d_2}"
            )
            allure.attach(extracted_labels,
                          name="提取的labelName",
                          attachment_type=allure.attachment_type.TEXT)

        with allure.step("步骤13：3D标注第一张") as step13:
            response = self.api_3d_label.label_3d(Test3DLabel.dimensionDataId_1, [566.0107005214322, 243.03692916466312,
                                                                                  118.08943939200213,
                                                                                  276.82962552300023, 324.1271494817036,
                                                                                  83.89034464762142, 0, 0, 0],
                                                  Test3DLabel.label_3d_1, "WH")
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

        with allure.step("步骤14：3D标注第二张") as step14:
            response = self.api_3d_label.label_3d(Test3DLabel.dimensionDataId_2,
                                                  [561.5785487046447, 475.4253437561026, 256.74868729206804,
                                                   263.9773852012997, 229.18250488057146, 552.493992091475, 0, 0, 0],
                                                  Test3DLabel.label_3d_2, "GH")
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

        with allure.step("步骤15：判断3D标注任务是否完成") as step15:
            response = self.api_3d_label.query_3d_task()
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            # 查找指定任务名的任务
            task_list = response_data.get('data', {}).get('list', [])
            target_task = None

            for task in task_list:
                if task.get('taskName') == self.task_name:
                    target_task = task
                    break

            if target_task:
                # 检查未标注数量
                no_tag_num = target_task.get('noTagNum', -1)  # 默认-1表示未获取到

                # 记录任务信息到报告
                task_info = (
                    f"3D任务名称: {self.task_name}\n"
                    f"未标注数量(noTagNum): {no_tag_num}\n"
                    f"预期值: 0"
                )
                allure.attach(task_info,
                              name="3D任务标注状态检查",
                              attachment_type=allure.attachment_type.TEXT)

                if no_tag_num == 0:
                    allure.attach("标注完成: 未标注数量为0",
                                  name="标注状态验证结果",
                                  attachment_type=allure.attachment_type.TEXT)
                else:
                    error_msg = f"错误: 未标注数量({no_tag_num})大于0，标注未完成！"
                    allure.attach(error_msg,
                                  name="标注状态验证失败",
                                  attachment_type=allure.attachment_type.TEXT)
                    pytest.fail(error_msg)
            else:
                error_msg = f"错误: 未找到任务名称为 '{self.task_name}' 的3D任务"
                allure.attach(error_msg,
                              name="3D任务查找失败",
                              attachment_type=allure.attachment_type.TEXT)
                pytest.fail(error_msg)

        with allure.step("步骤16：3D任务提交复核") as step16:
            response = self.api_3d_label.three_dim_task_commit_review(Test3DLabel.dimensionTaskId)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            self.verify_task_status(3, "待复核")

        with allure.step("步骤17：3D任务复核不通过") as step17:
            response = self.api_3d_label.three_dim_task_review_judge(Test3DLabel.dimensionTaskId, 8)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            self.verify_task_status(8, "复核未通过")

        with allure.step("步骤18：3D任务重标") as step18:
            response = self.api_3d_label.change_3d_task_status(Test3DLabel.dimensionTaskId)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            self.verify_task_status(2, "进行中")

        with allure.step("步骤19：3D任务再次提交复核") as step19:
            response = self.api_3d_label.three_dim_task_commit_review(Test3DLabel.dimensionTaskId)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            self.verify_task_status(3, "待复核")

        with allure.step("步骤20：3D任务复核通过") as step20:
            response = self.api_3d_label.three_dim_task_review_judge(Test3DLabel.dimensionTaskId, 4)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            self.verify_task_status(4, "复核通过")

        with allure.step("步骤21：创建&提交3D数据集") as step21:
            response = self.api_3d_label.create_3d_dataset(self.task_name, Test3DLabel.dimensionTaskId)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            self.verify_task_status(5, "已提交")

        with allure.step("步骤22：查询3D数据集管理") as step22:
            dataset_name = f"{self.task_name}-train"

            response = self.api_3d_label.query_3d_dataset()
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            # 提取数据集列表
            dataset_list = response_data.get('data', {}).get('list', [])
            target_dataset = None

            # 查找匹配的数据集
            for dataset in dataset_list:
                if dataset.get('name') == dataset_name:
                    target_dataset = dataset
                    break

            # 处理结果
            if target_dataset:
                # 获取状态和ID
                dataset_status = target_dataset.get('status')
                dataset_id = target_dataset.get('datasetId')

                # 记录数据集信息到报告
                dataset_info = (
                    f"3D数据集名称: {dataset_name}\n"
                    f"状态: {dataset_status}\n"
                    f"预期状态: 1 (已提交)"
                )
                allure.attach(dataset_info,
                              name="3D数据集状态检查",
                              attachment_type=allure.attachment_type.TEXT)

                # 验证状态
                if dataset_status == 1:
                    allure.attach(f"状态验证成功: 数据集状态为'已提交'",
                                  name="状态验证结果",
                                  attachment_type=allure.attachment_type.TEXT)

                    # 保存datasetId用于后续步骤
                    Test3DLabel.train_dataset_id = dataset_id

                    # 记录datasetId
                    id_info = f"成功获取datasetId: {dataset_id}"
                    allure.attach(id_info,
                                  name="datasetId提取",
                                  attachment_type=allure.attachment_type.TEXT)
                else:
                    # 状态异常处理
                    status_map = {
                        2: "已撤回",
                        6: "已发起重标"
                    }
                    status_name = status_map.get(dataset_status, f"未知状态({dataset_status})")

                    error_msg = f"错误: 3D数据集状态异常！当前状态: {status_name}，预期状态: 1 (已提交)"
                    allure.attach(error_msg,
                                  name="状态验证失败",
                                  attachment_type=allure.attachment_type.TEXT)
                    pytest.fail(error_msg)
            else:
                error_msg = f"错误: 未找到名称为 '{dataset_name}' 的3D数据集"
                allure.attach(error_msg,
                              name="3D数据集查找失败",
                              attachment_type=allure.attachment_type.TEXT)
                pytest.fail(error_msg)

        with allure.step("步骤23：撤回3D标注任务") as step23:
            if hasattr(Test3DLabel, 'train_dataset_id') and Test3DLabel.train_dataset_id:
                # 记录撤回参数
                withdraw_params = (
                    f"3D数据集ID: {Test3DLabel.train_dataset_id}\n"
                    f"3D数据集名称: {self.task_name}-train"
                )
                allure.attach(withdraw_params,
                              name="撤回参数",
                              attachment_type=allure.attachment_type.TEXT)

                response = self.api_3d_label.dataset_3d_withdraw(Test3DLabel.train_dataset_id)
                assertions.assert_code(response.status_code, 200)
                response_data = response.json()
                assertions.assert_in_text(response_data['msg'], '成功')

                # 记录撤回结果
                allure.attach(f"撤回结果: {response_data['msg']}",
                              name="样本撤回完成",
                              attachment_type=allure.attachment_type.TEXT)

                # 添加状态验证步骤
                with allure.step("子步骤1：验证数据集状态已更新为'已撤回'") as step15_1:
                    # 重新查询数据集状态
                    response = self.api_3d_label.query_3d_dataset()
                    assertions.assert_code(response.status_code, 200)
                    response_data = response.json()
                    assertions.assert_in_text(response_data['msg'], '成功')

                    # 查找目标数据集
                    dataset_list = response_data.get('data', {}).get('list', [])
                    target_dataset = None
                    for dataset in dataset_list:
                        if dataset.get('datasetId') == Test3DLabel.train_dataset_id:
                            target_dataset = dataset
                            break

                    if target_dataset:
                        # 获取更新后的状态
                        updated_status = target_dataset.get('status')

                        # 记录状态信息
                        status_info = (
                            f"3D数据集ID: {Test3DLabel.train_dataset_id}\n"
                            f"3D数据集名称: {self.task_name}-train\n"
                            f"当前状态: {updated_status}\n"
                            f"预期状态: 2 (已撤回)"
                        )
                        allure.attach(status_info,
                                      name="3D数据集状态验证",
                                      attachment_type=allure.attachment_type.TEXT)

                        # 验证状态
                        if updated_status == 2:
                            allure.attach("状态验证成功: 3D数据集已成功撤回",
                                          name="状态验证结果",
                                          attachment_type=allure.attachment_type.TEXT)
                        else:
                            # 状态异常处理
                            status_map = {
                                1: "已提交",
                                2: "已撤回",
                                6: "已发起重标"
                            }
                            status_name = status_map.get(updated_status, f"未知状态({updated_status})")

                            error_msg = f"错误: 3D数据集状态异常！当前状态: {status_name}，预期状态: 2 (已撤回)"
                            allure.attach(error_msg,
                                          name="状态验证失败",
                                          attachment_type=allure.attachment_type.TEXT)
                            pytest.fail(error_msg)
                    else:
                        error_msg = f"错误: 未找到数据集ID为 '{Test3DLabel.train_dataset_id}' 的3D数据集"
                        allure.attach(error_msg,
                                      name="3D数据集查找失败",
                                      attachment_type=allure.attachment_type.TEXT)
                        pytest.fail(error_msg)
            else:
                error_msg = "错误: 缺少有效的datasetId，无法执行撤回操作"
                allure.attach(error_msg,
                              name="撤回失败",
                              attachment_type=allure.attachment_type.TEXT)
                pytest.fail(error_msg)

        with allure.step("步骤24：3D任务发起重标") as step24:
            # 检查是否成功获取了datasetId
            if hasattr(Test3DLabel, 'train_dataset_id') and Test3DLabel.train_dataset_id:
                # 记录重标参数
                relabel_params = (
                    f"数据集ID: {Test3DLabel.train_dataset_id}\n"
                    f"数据集名称: {self.task_name}-train"
                )
                allure.attach(relabel_params,
                              name="重标参数",
                              attachment_type=allure.attachment_type.TEXT)

                response = self.api_3d_label.dataset_3d_relabel(Test3DLabel.train_dataset_id)
                assertions.assert_code(response.status_code, 200)
                response_data = response.json()
                assertions.assert_in_text(response_data['msg'], '成功')

                # 记录重标结果
                allure.attach(f"重标结果: {response_data['msg']}",
                              name="重标完成",
                              attachment_type=allure.attachment_type.TEXT)

                # 添加状态验证步骤
                with allure.step("子步骤1：验证数据集状态已更新为'已发起重标'") as step16_1:
                    # 重新查询数据集状态
                    response = self.api_3d_label.query_3d_dataset()
                    assertions.assert_code(response.status_code, 200)
                    response_data = response.json()
                    assertions.assert_in_text(response_data['msg'], '成功')

                    # 查找目标数据集
                    dataset_list = response_data.get('data', {}).get('list', [])
                    target_dataset = None
                    for dataset in dataset_list:
                        if dataset.get('datasetId') == Test3DLabel.train_dataset_id:
                            target_dataset = dataset
                            break

                    if target_dataset:
                        # 获取更新后的状态
                        updated_status = target_dataset.get('status')

                        # 记录状态信息
                        status_info = (
                            f"3D数据集ID: {Test3DLabel.train_dataset_id}\n"
                            f"3D数据集名称: {self.task_name}-train\n"
                            f"当前状态: {updated_status}\n"
                            f"预期状态: 6 (已发起重标)"
                        )
                        allure.attach(status_info,
                                      name="3D数据集状态验证",
                                      attachment_type=allure.attachment_type.TEXT)

                        # 验证状态
                        if updated_status == 6:
                            allure.attach("状态验证成功: 3D数据集已成功发起重标",
                                          name="状态验证结果",
                                          attachment_type=allure.attachment_type.TEXT)
                        else:
                            # 状态异常处理
                            status_map = {
                                1: "已提交",
                                2: "已撤回",
                                6: "已发起重标"
                            }
                            status_name = status_map.get(updated_status, f"未知状态({updated_status})")

                            error_msg = f"错误: 3D数据集状态异常！当前状态: {status_name}，预期状态: 6 (已发起重标)"
                            allure.attach(error_msg,
                                          name="状态验证失败",
                                          attachment_type=allure.attachment_type.TEXT)
                            pytest.fail(error_msg)
                    else:
                        error_msg = f"错误: 未找到数据集ID为 '{Test3DLabel.train_dataset_id}' 的3D数据集"
                        allure.attach(error_msg,
                                      name="3D数据集查找失败",
                                      attachment_type=allure.attachment_type.TEXT)
                        pytest.fail(error_msg)
            else:
                error_msg = "错误: 缺少有效的datasetId，无法执行重标操作"
                allure.attach(error_msg,
                              name="重标失败",
                              attachment_type=allure.attachment_type.TEXT)
                pytest.fail(error_msg)

        with allure.step("步骤25：检查3D标注任务状态") as step25:
            response = self.api_3d_label.query_3d_task()
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            self.verify_task_status(7, "待重标")
