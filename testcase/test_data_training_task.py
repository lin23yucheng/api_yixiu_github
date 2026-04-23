"""
数据训练任务接口自动化流程
"""
import ast
import pytest
import allure
import psycopg2
import configparser
import time
from common.Request_Response import ApiClient
from common import Assert
from common.path_utils import get_resource_path
from api import api_login, api_comprehensive_sample_library, api_data_training_tasks

assertions = Assert.Assertions()
time_str = time.strftime("%Y%m%d%H%M%S", time.localtime())

# 初始化全局客户端
base_headers = {
    "Authorization": api_login.ApiLogin().login(),
    "Miai-Product-Code": api_login.code,
    "Miaispacemanageid": api_login.manageid
}
global_client = ApiClient(base_headers=base_headers)


@allure.feature("场景：综合-数据训练任务全流程")
class TestDataTrainingTask:
    @classmethod
    def setup_class(cls):
        """初始化接口封装实例"""
        cls.api_comprehensive = api_comprehensive_sample_library.ApiComprehensiveSampleLibrary(global_client)
        cls.api_data = api_data_training_tasks.ApiDataTrainTasks(global_client)
        cls.task_name = f"接口自动化-{time_str}-数据训练"
        cls.max_wait_seconds = 1800
        cls.poll_interval = 10
        cls.dataAlgorithmTrainTaskId = None
        # 读取配置文件
        config_path = get_resource_path('config', 'env_config.ini')
        config = configparser.ConfigParser()
        config.read(config_path, encoding='utf-8')

        # 获取当前环境并从对应环境节读取
        env = config.get("environment", "execution_env", fallback="").strip().lower()
        if env not in {"fat", "prod"}:
            raise ValueError(f"execution_env 配置错误: {env}，仅支持 fat 或 prod")

        env_section = f"{env}-yixiu"
        cls.classify_type = ast.literal_eval(config.get(env_section, 'classify_type'))
        cls.photo_id = ast.literal_eval(config.get(env_section, 'photo_id'))

    def _monitor_data_task_progress(self):
        """监控数据训练任务采集状态并获取任务ID"""
        start_time = time.time()
        attempt = 0
        task_id_acquired = False

        # 状态映射表
        status_mapping = {
            0: "处理中",
            1: "采集中",
            2: "已完成",
            3: "处理失败",
            4: "采集失败"
        }

        with allure.step("监控数据训练任务采集状态"):
            while True:
                attempt += 1
                step_start = time.time()
                with allure.step(f"第{attempt}次状态检查"):
                    response = self.api_data.query_data_tasks()
                    assertions.assert_code(response.status_code, 200)

                    response_data = response.json()
                    tasks = response_data['data']['list']

                    allure.attach(
                        str(response_data),
                        name="数据任务查询响应",
                        attachment_type=allure.attachment_type.JSON
                    )

                    if not tasks:
                        pytest.fail(f"未找到任何数据训练任务")

                    current_task = next(
                        (t for t in tasks if t.get('name') == self.task_name),
                        None
                    )

                    if not current_task:
                        pytest.fail(f"未找到任务: {self.task_name}")

                    if not task_id_acquired:
                        task_id = current_task.get('dataAlgorithmTrainTaskId')
                        if task_id:
                            self.dataAlgorithmTrainTaskId = task_id
                            self.__class__.dataAlgorithmTrainTaskId = task_id
                            task_id_acquired = True
                            allure.attach(
                                f"获取到dataAlgorithmTrainTaskId: {task_id}",
                                name="数据训练任务ID",
                                attachment_type=allure.attachment_type.TEXT
                            )
                            # print(f"获取到任务ID: {task_id}")

                    status = current_task.get('status')
                    if status is None:
                        pytest.fail("状态字段缺失")

                    current_duration = int(time.time() - start_time)
                    mins, secs = divmod(current_duration, 60)
                    step_duration = time.time() - step_start

                    status_info = (
                        f"数据训练任务状态: {status} ({status_mapping.get(status, '未知状态')}) | "
                        f"总等待时间: {mins}分{secs}秒"
                    )

                    if status in [0, 1]:
                        print(f"\r\033[93m{status_info}\033[0m", end="")
                    elif status == 2:
                        print(f"\r\033[92m{status_info}\033[0m")
                    else:
                        print(f"\r\033[91m{status_info}\033[0m")

                    allure.attach(status_info, name="状态详情")

                    if status == 2:
                        allure.attach("数据采集已完成", name="最终状态")
                        return True
                    elif status in [3, 4]:
                        error_msg = current_task.get('errorMsg', '无错误信息')
                        pytest.fail(f"数据采集失败: {error_msg}")

                    elapsed = time.time() - start_time
                    if elapsed > self.max_wait_seconds:
                        pytest.fail(f"数据采集超时: 等待{self.max_wait_seconds}秒未完成")

                    time.sleep(self.poll_interval)

    def _delete_data_algorithm_via_db(self):
        """通过数据库逻辑删除数据算法包"""
        config = configparser.ConfigParser()
        config_path = get_resource_path('config', 'env_config.ini')
        config.read(config_path, encoding='utf-8')

        # 获取当前环境并从对应环境节读取数据库配置
        env = config.get("environment", "execution_env", fallback="").strip().lower()
        if env not in {"fat", "prod"}:
            raise ValueError(f"execution_env 配置错误: {env}，仅支持 fat 或 prod")

        db_config_section = f"{env}-PostgreSQL"
        db_config = config[db_config_section]
        host = db_config['host']
        port = int(db_config['port'])
        user = db_config['user_name']
        password = db_config['password']
        database = db_config['database']

        conn = None
        try:
            # 添加数据库连接信息到Allure
            db_info = f"连接数据库: host={host}, port={port}, user={user}, database={database}"
            allure.attach(db_info, name="数据库连接信息", attachment_type=allure.attachment_type.TEXT)

            conn = psycopg2.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                dbname=database
            )
            print(f"✅ 成功连接到数据库: {host}:{port}/{database}")

            # 添加连接成功信息到Allure
            success_msg = f"✅ 成功连接到数据库: {host}:{port}/{database}"
            allure.attach(success_msg, name="数据库连接成功", attachment_type=allure.attachment_type.TEXT)

            with conn.cursor() as cursor:
                # 检查记录数量
                check_sql = "SELECT COUNT(*) FROM data_algorithm_model WHERE data_algorithm_train_task_id = %s"
                cursor.execute(check_sql, (self.dataAlgorithmTrainTaskId,))
                count = cursor.fetchone()[0]

                # 添加查询结果到Allure
                count_info = f"查询到匹配记录数: {count} (任务ID: {self.dataAlgorithmTrainTaskId})"
                allure.attach(count_info, name="数据库查询结果", attachment_type=allure.attachment_type.TEXT)

                if count == 0:
                    error_msg = f"未找到匹配记录: data_algorithm_train_task_id={self.dataAlgorithmTrainTaskId}"
                    allure.attach(error_msg, name="数据库错误", attachment_type=allure.attachment_type.TEXT)
                    raise Exception(error_msg)

                if count > 1:
                    error_msg = f"找到多条记录({count}条)，拒绝执行删除操作"
                    allure.attach(error_msg, name="数据库错误", attachment_type=allure.attachment_type.TEXT)
                    raise Exception(error_msg)

                # 执行逻辑删除
                update_sql = "UPDATE data_algorithm_model SET is_delete = 't' WHERE data_algorithm_train_task_id = %s"
                cursor.execute(update_sql, (self.dataAlgorithmTrainTaskId,))
                conn.commit()

                success_msg = f"✅ 成功逻辑删除数据算法包，任务ID: {self.dataAlgorithmTrainTaskId}"
                print(success_msg)
                allure.attach(success_msg, name="数据库更新成功", attachment_type=allure.attachment_type.TEXT)

        except Exception as e:
            error_msg = f"❌ 数据库操作失败: {str(e)}"
            print(error_msg)
            allure.attach(error_msg, name="数据库错误", attachment_type=allure.attachment_type.TEXT)
            raise
        finally:
            if conn is not None:
                conn.close()

    @allure.story("数据训练任务")
    @allure.title("数据训练任务全流程")
    def test_data_task_workflow(self):
        total_start = time.time()
        step_durations = {}  # 存储每个步骤的耗时

        with allure.step("步骤1：获取产品下的深度模型") as step1:
            step_start = time.time()

            # 调用查询产品深度模型接口
            response = self.api_comprehensive.query_product_deep_model()

            # 验证响应
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            # 判断data下是否有数据
            deep_models = response_data.get('data', [])
            if not deep_models:
                print(f"\033[93m产品下无可用深度模型，无法创建数据训练任务\033[0m")
                pytest.skip("产品下无可用深度模型，无法创建数据训练任务")

            # 提取最后一条数据的字段
            last_model = deep_models[-1]
            self.check_scope = last_model.get('checkScope')
            self.class_names_list = last_model.get('classNamesList')
            self.deep_model_name = last_model.get('deepModelName')
            self.deep_model_source = last_model.get('deepModelSource')
            self.deep_model_version = last_model.get('deepModelVersion')
            self.inference_label = last_model.get('inferenceLabel')
            self.model_manage_id = last_model.get('modelManageId')
            self.triton_path = last_model.get('tritonPath')

            # 记录提取的字段信息
            extracted_info = f"""
            提取的深度模型字段信息:
            - checkScope: {self.check_scope}
            - classNamesList: {self.class_names_list}
            - deepModelName: {self.deep_model_name}
            - deepModelSource: {self.deep_model_source}
            - deepModelVersion: {self.deep_model_version}
            - inferenceLabel: {self.inference_label}
            - modelManageId: {self.model_manage_id}
            - tritonPath: {self.triton_path}
            """

            allure.attach(
                extracted_info,
                name="提取的深度模型字段信息",
                attachment_type=allure.attachment_type.TEXT
            )

            # 记录步骤耗时
            step_duration = time.time() - step_start
            step_durations["步骤1"] = step_duration

        with allure.step("步骤2：创建数据训练任务") as step2:
            step_start = time.time()

            # 使用提取的字段值创建数据训练任务
            response = self.api_comprehensive.create_data_training_tasks(
                self.photo_id,
                self.classify_type,
                self.task_name,
                self.model_manage_id,
                self.deep_model_name,
                self.deep_model_version,
                self.triton_path,
                self.deep_model_source,
                self.class_names_list,
                self.check_scope,
                self.inference_label
            )

            # 验证响应
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            # 记录任务信息
            allure.attach(
                f"任务名称: {self.task_name}",
                name="数据训练任务创建信息",
                attachment_type=allure.attachment_type.TEXT
            )

            # 记录步骤耗时
            step_duration = time.time() - step_start
            step_durations["步骤2"] = step_duration

        with allure.step("步骤3：监控数据训练任务采集状态") as step3:
            step_start = time.time()
            self._monitor_data_task_progress()

            # 记录步骤耗时
            step_duration = time.time() - step_start
            step_durations["步骤3"] = step_duration

        with allure.step("步骤4：生成下载数据包") as step4:
            step_start = time.time()
            response = self.api_data.create_data_zip(self.dataAlgorithmTrainTaskId)

            # 验证响应
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            # 记录步骤耗时
            step_duration = time.time() - step_start
            step_durations["步骤4"] = step_duration

        with allure.step("步骤5：上传数据算法包") as step5:
            step_start = time.time()
            response = self.api_data.upload_data_algorithm(self.dataAlgorithmTrainTaskId)

            # 验证响应
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            # 记录步骤耗时
            step_duration = time.time() - step_start
            step_durations["步骤5"] = step_duration

        with allure.step("步骤6：删除数据训练任务") as step6:
            step_start = time.time()

            with allure.step("子步骤1：数据库逻辑删除上传的数据算法包") as sub_step1:
                sub_start = time.time()
                self._delete_data_algorithm_via_db()
                sub_duration = time.time() - sub_start

            with allure.step("子步骤2：删除数据训练任务") as sub_step2:
                sub_start = time.time()

                # 记录请求信息
                request_info = (
                    f"删除任务请求:\n"
                    f"任务ID: {self.dataAlgorithmTrainTaskId}"
                )
                allure.attach(request_info, name="删除请求信息", attachment_type=allure.attachment_type.TEXT)

                # 执行删除操作
                response = self.api_data.delete_data_tasks(self.dataAlgorithmTrainTaskId)

                # 验证响应
                assertions.assert_code(response.status_code, 200)
                response_data = response.json()
                assertions.assert_in_text(response_data['msg'], '成功')

                # 记录响应信息
                response_info = (
                    f"状态码: {response.status_code}\n"
                    f"响应消息: {response_data['msg']}\n"
                    f"响应数据: {response.text}"
                )
                allure.attach(response_info, name="删除响应信息", attachment_type=allure.attachment_type.TEXT)

                sub_duration = time.time() - sub_start

                # 添加成功信息
                success_msg = f"✅ 成功删除数据训练任务，任务ID: {self.dataAlgorithmTrainTaskId}"
                allure.attach(success_msg, name="删除成功", attachment_type=allure.attachment_type.TEXT)

            # 记录步骤耗时
            step_duration = time.time() - step_start
            step_durations["步骤6"] = step_duration

        # 测试结束处理
        total_duration = time.time() - total_start
        mins, secs = divmod(int(total_duration), 60)

        # 打印测试完成信息
        print("\n" + "=" * 60)
        print(f"✅ 数据算法流程测试完成! 总耗时: {mins}分{secs}秒")
        print("=" * 60)

        # 添加总耗时到测试报告
        allure.dynamic.description(f"数据算法流程测试总耗时: {mins}分{secs}秒")
