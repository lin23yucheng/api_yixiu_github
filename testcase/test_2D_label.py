"""
单产品-2D标注流程
"""
import time
import pytest
import allure
from common import Assert
from datetime import datetime, timedelta
from common.Request_Response import ApiClient
from api import api_login, api_bash_sample_library, api_2D_label, api_product_label

assertions = Assert.Assertions()
time_str = time.strftime("%Y%m%d%H%M%S", time.localtime())

# 初始化全局客户端
base_headers = {
    "Authorization": api_login.ApiLogin().login(),
    "Miai-Product-Code": api_login.code,
    "Miaispacemanageid": api_login.manageid
}
global_client = ApiClient(base_headers=base_headers)


@allure.feature("场景：单产品-bash样本库分拣&2D标注全流程")
class TestLabel:
    @classmethod
    def setup_class(cls):
        """初始化接口封装实例"""
        cls.api_bash_sample = api_bash_sample_library.ApiBashSample(global_client)
        cls.api_2d_label = api_2D_label.Api2DLabel(global_client)
        cls.api_product_label = api_product_label.ApiProductLabel(global_client)
        cls.task_name = None
        cls.sampleDataSyncId_1 = None
        cls.sampleDataSyncId_2 = None
        cls.sampleDataSyncId_3 = None
        cls.dimensionTaskId = None
        cls.datasetDataId_1 = None
        cls.datasetDataId_2 = None
        cls.label_2d_1 = None
        cls.label_2d_2 = None

    def verify_task_status(self, expected_status, status_name):
        """
        验证标注任务状态是否符合预期
        """
        # 查询任务状态
        response = self.api_2d_label.query_2d_task(self.task_name)
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
    @allure.story("bash样本库分拣")
    def test_bash_sorting(self):
        # 计算日期参数
        current_date = datetime.now()
        endDateTime = current_date.strftime("%Y-%m-%d")
        startDateTime = (current_date - timedelta(days=1)).strftime("%Y-%m-%d")

        with allure.step("步骤1：查询bash样本库-原始样本") as step1:
            # 记录日期参数到Allure
            allure.attach(f"查询参数:\nstartDateTime={startDateTime}\nendDateTime={endDateTime}",
                          name="查询参数",
                          attachment_type=allure.attachment_type.TEXT)

            response = self.api_bash_sample.query_bash_sample(startDateTime, endDateTime)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            # 提取前三条数据的sampleDataSyncId
            sample_list = response_data.get('data', {}).get('list', [])
            if len(sample_list) >= 3:
                # 赋值给类变量
                TestLabel.sampleDataSyncId_1 = sample_list[0].get('sampleDataSyncId')
                TestLabel.sampleDataSyncId_2 = sample_list[1].get('sampleDataSyncId')
                TestLabel.sampleDataSyncId_3 = sample_list[2].get('sampleDataSyncId')

                # 记录提取的数据到Allure报告
                extracted_data = (
                    f"提取的前三条sampleDataSyncId:\n"
                    f"1. {TestLabel.sampleDataSyncId_1}\n"
                    f"2. {TestLabel.sampleDataSyncId_2}\n"
                    f"3. {TestLabel.sampleDataSyncId_3}"
                )
                allure.attach(extracted_data,
                              name="提取的sampleDataSyncId",
                              attachment_type=allure.attachment_type.TEXT)
            else:
                allure.attach("警告: 响应数据不足3条，无法提取全部ID",
                              name="数据提取警告",
                              attachment_type=allure.attachment_type.TEXT)

        with allure.step("步骤2：bash分拣") as step2:
            # 定义分拣任务列表: (sampleDataSyncId, 分拣结果只能是"ok"或"ng")
            sorting_tasks = [
                (self.sampleDataSyncId_1, "ng"),
                (self.sampleDataSyncId_2, "ng"),
                (self.sampleDataSyncId_3, "ok")
            ]

            # 遍历任务列表执行分拣
            for idx, (sample_id, label) in enumerate(sorting_tasks, 1):
                # 使用allure子步骤记录每个分拣任务
                with allure.step(f"分拣任务{idx}: sampleDataSyncId={sample_id}, label={label}"):
                    response = self.api_bash_sample.bash_sorting_sample(sample_id, label)
                    assertions.assert_code(response.status_code, 200)
                    response_data = response.json()
                    assertions.assert_in_text(response_data['msg'], '成功')

                    # 记录分拣结果到报告
                    allure.attach(
                        f"样本ID: {sample_id}\n分拣结果: {label}\n响应消息: {response_data['msg']}",
                        name=f"分拣任务{idx}结果",
                        attachment_type=allure.attachment_type.TEXT
                    )

        with allure.step("步骤3：创建2D标注任务") as step3:
            taskname = f"接口自动化标注-{time_str}"
            # 记录任务创建参数
            task_params = (
                f"任务名称: {taskname}\n"
                f"样本ID: {self.sampleDataSyncId_1}\n"
            )
            allure.attach(task_params, name="创建标注任务参数", attachment_type=allure.attachment_type.TEXT)

            response = self.api_bash_sample.create_label_task([self.sampleDataSyncId_1], startDateTime, endDateTime,
                                                              taskname)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')
            TestLabel.task_name = f"{taskname}-1"

        with allure.step("步骤4：查询标注任务的dimensionTaskId") as step4:
            response = self.api_bash_sample.query_append_task_id()
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
                TestLabel.dimensionTaskId = dimension_task_id

                # 记录到报告
                allure.attach(
                    f"找到任务: {self.task_name}\n"
                    f"dimensionTaskId: {dimension_task_id}",
                    name="任务匹配结果",
                    attachment_type=allure.attachment_type.TEXT
                )
            else:
                # 记录错误信息
                error_msg = f"错误: 未找到名称为 '{self.task_name}' 的任务"
                allure.attach(error_msg, name="任务查找失败", attachment_type=allure.attachment_type.TEXT)

                # 抛出异常
                pytest.fail(error_msg)

        with allure.step("步骤5：追加标注任务") as step5:
            # 记录追加任务参数
            append_params = (
                f"任务ID: {self.dimensionTaskId}\n"
                f"样本ID: {self.sampleDataSyncId_2}\n"
            )
            allure.attach(append_params, name="追加标注任务参数", attachment_type=allure.attachment_type.TEXT)

            response = self.api_bash_sample.append_label_task(startDateTime, endDateTime, [self.sampleDataSyncId_2],
                                                              self.dimensionTaskId)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

        with allure.step("步骤6：ok图创建提交数据集") as step6:
            # 记录数据集参数
            dataset_params = (
                f"数据集名称: 接口自动化ok图-{time_str}\n"
                f"样本ID: {self.sampleDataSyncId_3}\n"
            )
            allure.attach(dataset_params, name="创建数据集参数", attachment_type=allure.attachment_type.TEXT)

            response = self.api_bash_sample.ok_graph_create_dataset(f"接口自动化ok图-{time_str}", startDateTime,
                                                                    endDateTime, [self.sampleDataSyncId_3])
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

        with allure.step("步骤7：查询2D数据集管理") as step7:
            response = self.api_2d_label.query_2d_dataset()
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
                    TestLabel.ok_dataset_id = dataset_id

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

        with allure.step("步骤8：撤回ok样本") as step8:
            # 检查是否成功获取了datasetId
            if hasattr(TestLabel, 'ok_dataset_id') and TestLabel.ok_dataset_id:
                # 记录撤回参数
                withdraw_params = (
                    f"数据集ID: {TestLabel.ok_dataset_id}\n"
                    f"数据集名称: 接口自动化ok图-{time_str}"
                )
                allure.attach(withdraw_params,
                              name="撤回参数",
                              attachment_type=allure.attachment_type.TEXT)

                # 最多重试3次
                max_retries = 3
                retry_count = 0
                response = None
                response_data = None

                while retry_count < max_retries:
                    response = self.api_2d_label.dataset_withdraw(TestLabel.ok_dataset_id)
                    response_data = response.json()

                    # 如果返回预期的成功消息，则跳出循环
                    if response.status_code == 200 and '成功' in response_data.get('msg', ''):
                        break

                    # 如果返回ES插入中的错误消息，则等待1秒后重试
                    if '当前数据集正在插入到es,无法删除' in response_data.get('msg', ''):
                        retry_count += 1
                        if retry_count < max_retries:
                            time.sleep(1)  # 等待1秒后重试
                            continue
                        else:
                            # 达到最大重试次数，抛出异常
                            error_msg = f"错误: 数据集撤回失败，已重试{max_retries}次，仍然返回'{response_data.get('msg')}'"
                            allure.attach(error_msg,
                                          name="撤回失败",
                                          attachment_type=allure.attachment_type.TEXT)
                            pytest.fail(error_msg)
                    else:
                        # 其他错误情况直接失败
                        assertions.assert_code(response.status_code, 200)
                        assertions.assert_in_text(response_data['msg'], '成功')

                # 如果成功了，继续后续步骤
                if response and response.status_code == 200 and '成功' in response_data.get('msg', ''):
                    allure.attach(f"撤回结果: {response_data['msg']}",
                                  name="样本撤回完成",
                                  attachment_type=allure.attachment_type.TEXT)

                    # 添加状态验证步骤
                    with allure.step("子步骤1：验证数据集状态已更新为'已撤回'") as step8_1:
                        # 重新查询数据集状态
                        response = self.api_2d_label.query_2d_dataset()
                        assertions.assert_code(response.status_code, 200)
                        response_data = response.json()
                        assertions.assert_in_text(response_data['msg'], '成功')

                        # 查找目标数据集
                        dataset_list = response_data.get('data', {}).get('list', [])
                        target_dataset = None
                        for dataset in dataset_list:
                            if dataset.get('datasetId') == TestLabel.ok_dataset_id:
                                target_dataset = dataset
                                break

                        if target_dataset:
                            # 获取更新后的状态
                            updated_status = target_dataset.get('status')

                            # 记录状态信息
                            status_info = (
                                f"数据集ID: {TestLabel.ok_dataset_id}\n"
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
                            error_msg = f"错误: 未找到数据集ID为 '{TestLabel.ok_dataset_id}' 的数据集"
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

    @pytest.mark.order(2)
    @allure.story("2D标注")
    def test_2d_label(self):
        # 使用类变量
        dimensionTaskId = TestLabel.dimensionTaskId

        # 计算日期参数
        current_date = datetime.now()
        DateTime = current_date.strftime("%Y-%m-%d")

        with allure.step("步骤1：查询2D标注任务是否存在") as step1:
            response = self.api_2d_label.query_2d_task(self.task_name)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            # 检查任务列表中是否存在指定任务名的任务
            task_list = response_data.get('data', {}).get('list', [])
            task_exists = any(task.get('taskName') == self.task_name for task in task_list)

            if not task_exists:
                error_msg = f"错误: 未找到任务名称为 '{self.task_name}' 的任务"
                allure.attach(error_msg,
                              name="任务查找失败",
                              attachment_type=allure.attachment_type.TEXT)
                pytest.fail(error_msg)
            else:
                allure.attach(f"成功找到任务: {self.task_name}",
                              name="任务验证结果",
                              attachment_type=allure.attachment_type.TEXT)

        with allure.step("步骤2：开始标注") as step2:
            response = self.api_2d_label.re_label(dimensionTaskId)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            self.verify_task_status(2, "进行中")

        with allure.step("步骤3：查询标注图片获取datasetDataId") as step3:
            response = self.api_2d_label.query_2d_sample(dimensionTaskId)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            # 获取前两条数据的datasetDataId
            sample_list = response_data.get('data', {}).get('list', [])
            if len(sample_list) >= 2:
                TestLabel.datasetDataId_1 = sample_list[0].get('datasetDataId')
                TestLabel.datasetDataId_2 = sample_list[1].get('datasetDataId')

                # 记录到Allure报告
                extracted_data = (
                    f"提取的前两条datasetDataId:\n"
                    f"1. {TestLabel.datasetDataId_1}\n"
                    f"2. {TestLabel.datasetDataId_2}"
                )
                allure.attach(extracted_data,
                              name="提取的datasetDataId",
                              attachment_type=allure.attachment_type.TEXT)
            else:
                error_msg = "错误: 响应数据不足2条，无法提取全部datasetDataId"
                allure.attach(error_msg,
                              name="数据提取失败",
                              attachment_type=allure.attachment_type.TEXT)
                pytest.fail(error_msg)

        with allure.step("步骤4：获取标注缺陷") as step4:
            response = self.api_2d_label.query_2d_label()
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            # 提取标记方法为"矩形"和"多边形"的第一条数据的labelName
            label_data = response_data.get('data', [])

            rectangle_label = None
            polygon_label = None

            # 查找标记方法为"矩形"的第一条数据
            for item in label_data:
                if item.get('markMethod') == '矩形':
                    rectangle_label = item.get('labelName')
                    break

            # 查找标记方法为"多边形"的第一条数据
            for item in label_data:
                if item.get('markMethod') == '多边形':
                    polygon_label = item.get('labelName')
                    break

            # 检查是否成功提取到所需标签
            missing_labels = []
            if not rectangle_label:
                missing_labels.append('矩形')
            if not polygon_label:
                missing_labels.append('多边形')

            if missing_labels:
                # 有标签缺失，需要添加产品标签
                allure.attach(f"检测到缺失标签类型: {', '.join(missing_labels)}，开始添加产品标签",
                              name="标签缺失处理",
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

                    # 在响应中查找labelName等于"suokong"的数据
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

                with allure.step("子步骤4：重新获取标注缺陷") as requery_step:
                    response = self.api_2d_label.query_2d_label()
                    assertions.assert_code(response.status_code, 200)
                    response_data = response.json()
                    assertions.assert_in_text(response_data['msg'], '成功')

                    # 重新提取标记方法为"矩形"和"多边形"的第一条数据的labelName
                    label_data = response_data.get('data', [])

                    rectangle_label = None
                    polygon_label = None

                    # 查找标记方法为"矩形"的第一条数据
                    for item in label_data:
                        if item.get('markMethod') == '矩形':
                            rectangle_label = item.get('labelName')
                            break

                    # 查找标记方法为"多边形"的第一条数据
                    for item in label_data:
                        if item.get('markMethod') == '多边形':
                            polygon_label = item.get('labelName')
                            break

                    # 再次检查是否成功提取到所需标签
                    if not rectangle_label:
                        error_msg = "错误: 重新添加标签后仍未找到标记方法为'矩形'的标签数据"
                        allure.attach(error_msg,
                                      name="矩形标签提取失败",
                                      attachment_type=allure.attachment_type.TEXT)
                        pytest.fail(error_msg)

                    if not polygon_label:
                        error_msg = "错误: 重新添加标签后仍未找到标记方法为'多边形'的标签数据"
                        allure.attach(error_msg,
                                      name="多边形标签提取失败",
                                      attachment_type=allure.attachment_type.TEXT)
                        pytest.fail(error_msg)

            # 赋值给类变量
            if rectangle_label:
                TestLabel.label_2d_1 = rectangle_label
            if polygon_label:
                TestLabel.label_2d_2 = polygon_label

            # 记录提取结果到Allure报告
            extracted_labels = (
                f"提取的标签名称:\n"
                f"矩形标签(label_2d_1): {TestLabel.label_2d_1}\n"
                f"多边形标签(label_2d_2): {TestLabel.label_2d_2}"
            )
            allure.attach(extracted_labels,
                          name="提取的labelName",
                          attachment_type=allure.attachment_type.TEXT)

        with allure.step("步骤5：标注矩形-无争议") as step5:
            # 记录标注参数到Allure
            label_params = (
                f"标注参数:\n"
                f"datasetDataId: {self.datasetDataId_1}\n"
                f"标签: {self.label_2d_1}\n"
                f"形状: 矩形\n"
                f"坐标: [[78, 57], [128, 83]]\n"
                f"争议: 无争议"
            )
            allure.attach(label_params,
                          name="矩形标注参数",
                          attachment_type=allure.attachment_type.TEXT)

            response = self.api_2d_label.label_2d_rectangle(self.datasetDataId_1, self.label_2d_1, "rectangle",
                                                            [[78, 57], [128, 83]],
                                                            "")
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            # 记录标注结果
            allure.attach(f"标注结果: {response_data['msg']}",
                          name="矩形标注结果",
                          attachment_type=allure.attachment_type.TEXT)

        with allure.step("步骤6：标注多边形-有争议") as step6:
            # 记录标注参数到Allure
            label_params = (
                f"标注参数:\n"
                f"datasetDataId: {self.datasetDataId_2}\n"
                f"标签: {self.label_2d_2}\n"
                f"形状: 多边形\n"
                f"坐标: [[160, 64], [110, 116], [118, 222], [268, 242], [308, 138], [244, 60]]\n"
                f"争议: 有争议"
            )
            allure.attach(label_params,
                          name="多边形标注参数",
                          attachment_type=allure.attachment_type.TEXT)

            response = self.api_2d_label.label_2d_polygon(self.datasetDataId_2, self.label_2d_2, "polygon",
                                                          [[160, 64], [110, 116], [118, 222], [268, 242], [308, 138],
                                                           [244, 60]],
                                                          "Dispute")
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            # 记录标注结果
            allure.attach(f"标注结果: {response_data['msg']}",
                          name="多边形标注结果",
                          attachment_type=allure.attachment_type.TEXT)

        with allure.step("步骤7：判断2D标注任务是否完成") as step7:
            response = self.api_2d_label.query_2d_task(self.task_name)
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
                    f"任务名称: {self.task_name}\n"
                    f"未标注数量(noTagNum): {no_tag_num}\n"
                    f"预期值: 0"
                )
                allure.attach(task_info,
                              name="任务标注状态检查",
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
                error_msg = f"错误: 未找到任务名称为 '{self.task_name}' 的任务"
                allure.attach(error_msg,
                              name="任务查找失败",
                              attachment_type=allure.attachment_type.TEXT)
                pytest.fail(error_msg)

        with allure.step("步骤8：提交复核") as step8:
            response = self.api_2d_label.submit_review(dimensionTaskId)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            self.verify_task_status(3, "待复核")

        with allure.step("步骤9：复核不通过") as step9:
            response = self.api_2d_label.review_judge(dimensionTaskId, 8)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            self.verify_task_status(8, "复核未通过")

        with allure.step("步骤10：重标") as step10:
            response = self.api_2d_label.re_label(dimensionTaskId)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            self.verify_task_status(2, "进行中")

        with allure.step("步骤11：再次提交复核") as step11:
            response = self.api_2d_label.submit_review(dimensionTaskId)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            self.verify_task_status(3, "待复核")

        with allure.step("步骤12：复核通过") as step12:
            response = self.api_2d_label.review_judge(dimensionTaskId, 4)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            self.verify_task_status(4, "复核通过")

        with allure.step("步骤13：判断是否标注有争议") as step13:
            response = self.api_2d_label.query_2d_task(self.task_name)
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
                # 检查争议数量
                disputeNum = target_task.get('disputeNum', -1)  # 默认-1表示未获取到

                # 记录任务信息到报告
                task_info = (
                    f"任务名称: {self.task_name}\n"
                    f"争议数量(disputeNum): {disputeNum}"
                )
                allure.attach(task_info,
                              name="争议数量检查",
                              attachment_type=allure.attachment_type.TEXT)

                # 判断争议数量
                if disputeNum > 0:
                    dispute_id = None  # 初始化争议ID变量

                    with allure.step("子步骤1: 获取争议缺陷id") as substep1:
                        response = self.api_2d_label.query_dispute_defect_id(self.datasetDataId_2)
                        assertions.assert_code(response.status_code, 200)
                        response_data = response.json()
                        assertions.assert_in_text(response_data['msg'], '成功')

                        # 提取第一条数据的id
                        defect_list = response_data.get('data', [])
                        if defect_list:
                            dispute_id = defect_list[0].get('id')

                            # 记录获取的争议ID到报告
                            id_info = (
                                f"样本ID: {self.datasetDataId_2}\n"
                                f"获取到的争议缺陷ID: {dispute_id}"
                            )
                            allure.attach(id_info,
                                          name="争议缺陷ID获取结果",
                                          attachment_type=allure.attachment_type.TEXT)
                        else:
                            error_msg = "错误: 未获取到争议缺陷ID列表"
                            allure.attach(error_msg,
                                          name="争议缺陷ID获取失败",
                                          attachment_type=allure.attachment_type.TEXT)
                            pytest.fail(error_msg)

                    with allure.step("子步骤2: 争议判定") as substep2:
                        if dispute_id:
                            # 记录争议判定参数
                            judge_params = (
                                f"样本ID: {self.datasetDataId_2}\n"
                                f"日期: {DateTime}\n"
                                f"争议缺陷ID: {dispute_id}"
                            )
                            allure.attach(judge_params,
                                          name="争议判定参数",
                                          attachment_type=allure.attachment_type.TEXT)

                            response = self.api_2d_label.dispute_judge(
                                self.datasetDataId_2, DateTime, dispute_id, self.label_2d_2,
                                [[160, 64], [110, 116], [118, 222], [268, 242], [308, 138], [244, 60]])
                            assertions.assert_code(response.status_code, 200)
                            response_data = response.json()
                            assertions.assert_in_text(response_data['msg'], '成功')

                            # 记录判定结果
                            allure.attach(f"争议判定结果: {response_data['msg']}",
                                          name="争议判定完成",
                                          attachment_type=allure.attachment_type.TEXT)
                        else:
                            error_msg = "错误: 缺少有效的争议缺陷ID，无法执行争议判定"
                            allure.attach(error_msg,
                                          name="争议判定失败",
                                          attachment_type=allure.attachment_type.TEXT)
                            pytest.fail(error_msg)

                    with allure.step("子步骤3: 修改有争议为无争议") as substep3:
                        # 记录处理参数
                        handle_params = (
                            f"样本ID: {self.datasetDataId_2}\n"
                            f"日期: {DateTime}"
                        )
                        allure.attach(handle_params,
                                      name="争议处理参数",
                                      attachment_type=allure.attachment_type.TEXT)

                        response = self.api_2d_label.dispute_handle(self.datasetDataId_2, DateTime, self.label_2d_2,
                                                                    [[160, 64], [110, 116], [118, 222], [268, 242],
                                                                     [308, 138], [244, 60]])
                        assertions.assert_code(response.status_code, 200)
                        response_data = response.json()
                        assertions.assert_in_text(response_data['msg'], '成功')

                        # 记录处理结果
                        allure.attach(f"争议处理结果: {response_data['msg']}",
                                      name="争议处理完成",
                                      attachment_type=allure.attachment_type.TEXT)

                    with allure.step("子步骤4: 判断争议是否已处理") as substep4:
                        response = self.api_2d_label.query_2d_task(self.task_name)
                        assertions.assert_code(response.status_code, 200)
                        response_data = response.json()
                        assertions.assert_in_text(response_data['msg'], '成功')

                        # 获取更新后的争议数量
                        updated_task_list = response_data.get('data', {}).get('list', [])
                        updated_disputeNum = 0
                        for task in updated_task_list:
                            if task.get('taskName') == self.task_name:
                                updated_disputeNum = task.get('disputeNum', -1)
                                break

                        # 记录争议数量检查结果
                        dispute_check = (
                            f"任务名称: {self.task_name}\n"
                            f"处理后争议数量: {updated_disputeNum}\n"
                            f"预期值: 0"
                        )
                        allure.attach(dispute_check,
                                      name="争议处理验证",
                                      attachment_type=allure.attachment_type.TEXT)

                        if updated_disputeNum == 0:
                            allure.attach("争议处理成功: 争议数量已清零",
                                          name="争议处理验证通过",
                                          attachment_type=allure.attachment_type.TEXT)
                        else:
                            error_msg = f"错误: 争议处理失败，争议数量({updated_disputeNum})大于0！"
                            allure.attach(error_msg,
                                          name="争议处理验证失败",
                                          attachment_type=allure.attachment_type.TEXT)
                            pytest.fail(error_msg)
                else:
                    allure.attach("没有争议数据，继续执行后续步骤",
                                  name="无争议确认",
                                  attachment_type=allure.attachment_type.TEXT)
            else:
                error_msg = f"错误: 未找到任务名称为 '{self.task_name}' 的任务"
                allure.attach(error_msg,
                              name="任务查找失败",
                              attachment_type=allure.attachment_type.TEXT)
                pytest.fail(error_msg)

        with allure.step("步骤14：创建&提交数据集") as step14:
            response = self.api_2d_label.create_dataset(self.task_name, dimensionTaskId)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            self.verify_task_status(5, "已提交")

        with allure.step("步骤15：查询2D数据集管理") as step15:
            # 构建数据集名称
            dataset_name = f"{self.task_name}-train"

            response = self.api_2d_label.query_2d_dataset()
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
                    f"数据集名称: {dataset_name}\n"
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
                    TestLabel.train_dataset_id = dataset_id

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

                    error_msg = f"错误: 数据集状态异常！当前状态: {status_name}，预期状态: 1 (已提交)"
                    allure.attach(error_msg,
                                  name="状态验证失败",
                                  attachment_type=allure.attachment_type.TEXT)
                    pytest.fail(error_msg)
            else:
                error_msg = f"错误: 未找到名称为 '{dataset_name}' 的数据集"
                allure.attach(error_msg,
                              name="数据集查找失败",
                              attachment_type=allure.attachment_type.TEXT)
                pytest.fail(error_msg)

        with allure.step("步骤16：撤回标注样本") as step16:
            # 检查是否成功获取了datasetId
            if hasattr(TestLabel, 'train_dataset_id') and TestLabel.train_dataset_id:
                # 记录撤回参数
                withdraw_params = (
                    f"数据集ID: {TestLabel.train_dataset_id}\n"
                    f"数据集名称: {self.task_name}-train"
                )
                allure.attach(withdraw_params,
                              name="撤回参数",
                              attachment_type=allure.attachment_type.TEXT)

                # 最多重试3次
                max_retries = 3
                retry_count = 0
                response = None
                response_data = None

                while retry_count < max_retries:
                    response = self.api_2d_label.dataset_withdraw(TestLabel.train_dataset_id)
                    response_data = response.json()

                    # 如果返回预期的成功消息，则跳出循环
                    if response.status_code == 200 and '成功' in response_data.get('msg', ''):
                        break

                    # 如果返回ES插入中的错误消息，则等待3秒后重试
                    if '当前数据集正在插入到es,无法删除' in response_data.get('msg', ''):
                        retry_count += 1
                        if retry_count < max_retries:
                            time.sleep(3)  # 等待3秒后重试
                            continue
                        else:
                            # 达到最大重试次数，抛出异常
                            error_msg = f"错误: 数据集撤回失败，已重试{max_retries}次，仍然返回'{response_data.get('msg')}'"
                            allure.attach(error_msg,
                                          name="撤回失败",
                                          attachment_type=allure.attachment_type.TEXT)
                            pytest.fail(error_msg)
                    else:
                        # 其他错误情况直接失败
                        assertions.assert_code(response.status_code, 200)
                        assertions.assert_in_text(response_data['msg'], '成功')

                # 如果成功了，继续后续步骤
                if response and response.status_code == 200 and '成功' in response_data.get('msg', ''):
                    allure.attach(f"撤回结果: {response_data['msg']}",
                                  name="样本撤回完成",
                                  attachment_type=allure.attachment_type.TEXT)

                    # 添加状态验证步骤
                    with allure.step("子步骤1：验证数据集状态已更新为'已撤回'") as step15_1:
                        # 重新查询数据集状态
                        response = self.api_2d_label.query_2d_dataset()
                        assertions.assert_code(response.status_code, 200)
                        response_data = response.json()
                        assertions.assert_in_text(response_data['msg'], '成功')

                        # 查找目标数据集
                        dataset_list = response_data.get('data', {}).get('list', [])
                        target_dataset = None
                        for dataset in dataset_list:
                            if dataset.get('datasetId') == TestLabel.train_dataset_id:
                                target_dataset = dataset
                                break

                        if target_dataset:
                            # 获取更新后的状态
                            updated_status = target_dataset.get('status')

                            # 记录状态信息
                            status_info = (
                                f"数据集ID: {TestLabel.train_dataset_id}\n"
                                f"数据集名称: {self.task_name}-train\n"
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
                            error_msg = f"错误: 未找到数据集ID为 '{TestLabel.train_dataset_id}' 的数据集"
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

        with allure.step("步骤17：发起重标") as step17:
            # 检查是否成功获取了datasetId
            if hasattr(TestLabel, 'train_dataset_id') and TestLabel.train_dataset_id:
                # 记录重标参数
                relabel_params = (
                    f"数据集ID: {TestLabel.train_dataset_id}\n"
                    f"数据集名称: {self.task_name}-train"
                )
                allure.attach(relabel_params,
                              name="重标参数",
                              attachment_type=allure.attachment_type.TEXT)

                response = self.api_2d_label.dataset_relabel(TestLabel.train_dataset_id)
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
                    response = self.api_2d_label.query_2d_dataset()
                    assertions.assert_code(response.status_code, 200)
                    response_data = response.json()
                    assertions.assert_in_text(response_data['msg'], '成功')

                    # 查找目标数据集
                    dataset_list = response_data.get('data', {}).get('list', [])
                    target_dataset = None
                    for dataset in dataset_list:
                        if dataset.get('datasetId') == TestLabel.train_dataset_id:
                            target_dataset = dataset
                            break

                    if target_dataset:
                        # 获取更新后的状态
                        updated_status = target_dataset.get('status')

                        # 记录状态信息
                        status_info = (
                            f"数据集ID: {TestLabel.train_dataset_id}\n"
                            f"数据集名称: {self.task_name}-train\n"
                            f"当前状态: {updated_status}\n"
                            f"预期状态: 6 (已发起重标)"
                        )
                        allure.attach(status_info,
                                      name="数据集状态验证",
                                      attachment_type=allure.attachment_type.TEXT)

                        # 验证状态
                        if updated_status == 6:
                            allure.attach("状态验证成功: 数据集已成功发起重标",
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

                            error_msg = f"错误: 数据集状态异常！当前状态: {status_name}，预期状态: 6 (已发起重标)"
                            allure.attach(error_msg,
                                          name="状态验证失败",
                                          attachment_type=allure.attachment_type.TEXT)
                            pytest.fail(error_msg)
                    else:
                        error_msg = f"错误: 未找到数据集ID为 '{TestLabel.train_dataset_id}' 的数据集"
                        allure.attach(error_msg,
                                      name="数据集查找失败",
                                      attachment_type=allure.attachment_type.TEXT)
                        pytest.fail(error_msg)
            else:
                error_msg = "错误: 缺少有效的datasetId，无法执行重标操作"
                allure.attach(error_msg,
                              name="重标失败",
                              attachment_type=allure.attachment_type.TEXT)
                pytest.fail(error_msg)

        with allure.step("步骤18：检查标注任务状态") as step18:
            response = self.api_2d_label.query_2d_task(self.task_name)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            self.verify_task_status(7, "待重标")
