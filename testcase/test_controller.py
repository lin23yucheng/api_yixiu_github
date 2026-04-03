"""
模型训练前置数据校验控制器
功能：
1. 检查当前配置产品下是否有 imgNum=158 且 sampleType=ng 且 status=1 的数据集
2. 如无符合条件的数据集，则上传训练集ng数据集并监控上传状态
3. 上传训练集ok数据集并监控上传状态
"""
import pytest
import allure
import time
import os
import sys
from api import api_login, api_2D_label
from common.Request_Response import ApiClient
from common import Assert

assertions = Assert.Assertions()


class TestController:
    """模型训练数据准备控制器"""

    @classmethod
    def setup_class(cls):
        """初始化全局客户端"""
        cls.base_headers = {
            "Authorization": api_login.ApiLogin().login(),
            "Miai-Product-Code": api_login.code,
            "Miaispacemanageid": api_login.manageid
        }
        cls.global_client = ApiClient(base_headers=cls.base_headers)
        cls.api_2d_label = api_2D_label.Api2DLabel(cls.global_client)

    @allure.feature("场景：模型训练前置数据校验与准备")
    def test_prepare_training_data(self):
        """准备模型训练所需数据集"""

        with allure.step("步骤1：查询当前配置产品数据集，检查是否有imgNum=158且sampleType=ng且status=1的数据"):
            # 首先校验空间名称
            if api_login.space_name in ["YiXiu_Test_Use", "Test_Use_Test"]:
                allure.attach(
                    f"当前空间名称为{api_login.space_name}，为测试空间，无需上传数据集",
                    name="空间名称校验",
                    attachment_type=allure.attachment_type.TEXT
                )
                print(f"⚠️ 当前空间名称为{api_login.space_name}，为测试空间，无需上传数据集")
                return

            # 进行数据集检查
            has_valid_ng_dataset = self._check_current_product_dataset()

            if has_valid_ng_dataset:
                # 如果找到符合条件的数据集，终止脚本，不继续执行后续步骤
                return

        with allure.step("步骤2：上传训练集ng数据集"):
            # 上传数据集
            upload_response = self.api_2d_label.upload_dataset(
                name="api_158_ng",
                sample_type="ng",
                dataset_type=0,
                file_path="testdata/dataset/训练集ng.zip"
            )

            assertions.assert_code(upload_response.status_code, 200)
            upload_data = upload_response.json()
            assertions.assert_in_text(upload_data.get('msg', ''), '成功')

            allure.attach(
                f"训练集ng上传成功",
                name="上传结果",
                attachment_type=allure.attachment_type.TEXT
            )
            print(f"✅ 训练集ng上传成功")

        with allure.step("步骤3：监控训练集ng上传状态"):
            self._monitor_upload_status("api_158_ng")
            print("✅ 训练集ng上传完成且状态正常")

        with allure.step("步骤4：上传训练集ok数据集"):
            # 上传训练集ok数据集
            upload_response = self.api_2d_label.upload_dataset(
                name="api_2_ok",
                sample_type="ok",
                dataset_type=0,
                file_path="testdata/dataset/训练集ok.zip"
            )

            assertions.assert_code(upload_response.status_code, 200)
            upload_data = upload_response.json()
            assertions.assert_in_text(upload_data.get('msg', ''), '成功')

            allure.attach(
                f"训练集ok上传成功",
                name="上传结果",
                attachment_type=allure.attachment_type.TEXT
            )
            print(f"✅ 训练集ok上传成功")

        with allure.step("步骤5：监控训练集ok上传状态"):
            self._monitor_upload_status("api_2_ok")
            print("✅ 训练集ok上传完成且状态正常")

        with allure.step("步骤6：上传测试集ng数据集"):
            # 上传测试集ng数据集
            upload_response = self.api_2d_label.upload_dataset(
                name="api_95_ng",
                sample_type="ng",
                dataset_type=1,
                file_path="testdata/dataset/测试集ng.zip"
            )

            assertions.assert_code(upload_response.status_code, 200)
            upload_data = upload_response.json()
            assertions.assert_in_text(upload_data.get('msg', ''), '成功')

            allure.attach(
                f"测试集ng上传成功",
                name="上传结果",
                attachment_type=allure.attachment_type.TEXT
            )
            print(f"✅ 测试集ng上传成功")

        with allure.step("步骤7：刷新分类类别"):
            # 调用刷新分类类别接口
            refresh_url = "https://fat-yixiu-bash-api.svfactory.com:6143/brainstorm/dimensiontask/refresh/classify/type/{}".format(api_login.manageid)
            refresh_response = self.global_client.post(refresh_url, json={})

            # 记录请求和响应信息到allure，便于排查
            headers = getattr(self.global_client, 'headers', self.base_headers)
            allure.attach(
                f"请求URL: {refresh_url}\n请求Headers: {headers}\n请求Body: {{}}\n响应内容: {refresh_response.text}",
                name="刷新分类类别接口请求与响应",
                attachment_type=allure.attachment_type.TEXT
            )

            assertions.assert_code(refresh_response.status_code, 200)
            if not refresh_response.text.strip():
                # 空响应体，认为成功
                allure.attach("刷新分类类别成功（响应体为空，操作已完成）", name="刷新结果", attachment_type=allure.attachment_type.TEXT)
                print("✅ 刷新分类类别成功（响应体为空）")
            else:
                try:
                    resp_json = refresh_response.json()
                    msg = resp_json.get('msg', '')
                    if '成功' in msg:
                        allure.attach(f"刷新分类类别成功: {msg}", name="刷新结果", attachment_type=allure.attachment_type.TEXT)
                        print(f"✅ 刷新分类类别成功: {msg}")
                    else:
                        allure.attach(f"刷新分类类别失败: {msg}", name="刷新失败", attachment_type=allure.attachment_type.TEXT)
                        pytest.fail(f"刷新分类类别失败: {msg}")
                except Exception:
                    pytest.fail(f"刷新分类类别接口响应非json: {refresh_response.text}")

    def _check_current_product_dataset(self):
        """
        检查当前配置产品下的数据集，判断是否有imgNum=158且sampleType=ng且status=1的数据
        :return: True-找到符合条件的数据集，False-未找到
        """
        # 查询当前配置产品的数据集
        response = self.api_2d_label.query_2d_dataset()
        assertions.assert_code(response.status_code, 200)

        response_data = response.json()
        dataset_list = response_data.get('data', {}).get('list', [])

        # 检查是否有符合条件的数据集
        for dataset in dataset_list:
            img_num = dataset.get('imgNum')
            sample_type = dataset.get('sampleType')
            status = dataset.get('status')

            if img_num == 158 and sample_type == "ng" and status == 1:
                allure.attach(
                    f"在当前配置产品下找到符合条件的ng数据集: "
                    f"imgNum={img_num}, sampleType={sample_type}, status={status}",
                    name="符合条件的ng数据集",
                    attachment_type=allure.attachment_type.TEXT
                )
                print(f"✅ 当前配置产品下找到符合条件的ng数据集")
                return True

        print(f"❌ 当前配置产品下未找到符合条件的ng数据集")
        return False

    def _monitor_upload_status(self, dataset_name):
        """
        监控数据集上传状态
        :param dataset_name: 数据集名称
        :return: True-上传成功，False/异常-上传失败
        """
        start_time = time.time()
        max_wait_seconds = 900  # 15分钟超时
        poll_interval = 5  # 5秒轮询

        attempt = 0

        while True:
            attempt += 1
            elapsed = time.time() - start_time

            # 超时检查
            if elapsed > max_wait_seconds:
                pytest.fail(f"数据集({dataset_name})上传状态监控超时: 等待{max_wait_seconds}秒仍未完成")

            # 查询数据集状态
            response = self.api_2d_label.query_2d_dataset()
            assertions.assert_code(response.status_code, 200)

            response_data = response.json()
            dataset_list = response_data.get('data', {}).get('list', [])

            # 查找指定名称的数据集
            target_dataset = None
            for dataset in dataset_list:
                if dataset.get('name') == dataset_name:
                    target_dataset = dataset
                    break

            if not target_dataset:
                # 数据集可能还未创建，继续等待
                print(f"第{attempt}次检查: 未找到name={dataset_name}的数据集，继续等待...")
                time.sleep(poll_interval)
                continue

            status = target_dataset.get('status')
            status_text = self._get_status_text(status)

            allure.attach(
                f"第{attempt}次检查: 数据集{dataset_name}状态={status_text}({status}), "
                f"已等待{int(elapsed)}秒",
                name="上传状态监控",
                attachment_type=allure.attachment_type.TEXT
            )
            print(f"第{attempt}次检查: 数据集{dataset_name}状态={status_text}({status}), 已等待{int(elapsed)}秒")

            # 状态判断
            if status == 1:  # 已提交（上传完成）
                allure.attach(
                    f"数据集{dataset_name}上传完成，状态：已提交",
                    name="上传完成",
                    attachment_type=allure.attachment_type.TEXT
                )
                print(f"✅ 数据集{dataset_name}上传完成，状态：已提交")
                return True

            elif status == 5:  # 上传失败
                pytest.fail(f"数据集{dataset_name}上传失败，状态码：{status}")

            elif status == 3:  # 上传中
                # 继续监控
                time.sleep(poll_interval)
                continue

            else:  # 其他未知状态
                print(f"⚠️ 未知状态: {status}，继续监控...")
                time.sleep(poll_interval)
                continue

    def _get_status_text(self, status):
        """
        获取状态码对应的状态文本
        :param status: 状态码
        :return: 状态文本
        """
        status_mapping = {
            1: "已提交",
            3: "上传中",
            5: "上传失败"
        }
        return status_mapping.get(status, f"未知状态({status})")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--alluredir=./allure-results'])
