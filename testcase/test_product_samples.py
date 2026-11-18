"""
产品样例接口自动化流程
"""
import allure
import time
import pytest
from common import Assert
from api import api_login, api_product_samples
from common.Request_Response import ApiClient
from common.client_factory import create_lazy_yixiu_client

assertions = Assert.Assertions()
code = api_login.code
manageid = api_login.manageid
time_str = time.strftime("%Y%m%d%H%M%S", time.localtime())

# 全局懒加载客户端：仅在首次发送请求时才进行身份认证。
global_client = create_lazy_yixiu_client()


@pytest.mark.product_samples
@allure.feature("场景：单产品-产品样例流程")
class TestProductSamples:
    @classmethod
    def setup_class(cls):
        cls.api_product_samples = api_product_samples.ApiProductSamples(global_client)
        cls.productSampleId = None
        cls.sample_name = f"CS_{time_str}"

    @allure.story("产品样例增删改查")
    def test_product_samples(self):
        with allure.step(f"步骤1：新增产品样例") as step1:
            data_value = self.api_product_samples.upload_pictures()
            response = self.api_product_samples.samples_add(data_value, self.sample_name)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

        with allure.step(f"步骤2：查询产品样例") as step2:
            response = self.api_product_samples.samples_query()
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            # 提取指定名称的productSampleId
            sample_list = response_data.get('data', {}).get('list', [])
            for sample in sample_list:
                if sample.get('name') == self.sample_name:
                    self.productSampleId = sample.get('productSampleId')
                    break

            assert self.productSampleId, f"未找到名称为 {self.sample_name} 的产品样例"
            allure.attach(
                f"提取的样例ID: {self.productSampleId}",
                name="样例ID",
                attachment_type=allure.attachment_type.TEXT
            )

        with allure.step(f"步骤3：修改产品样例") as step3:
            response = self.api_product_samples.samples_update(
                code,
                manageid,
                self.productSampleId,  # 使用提取的ID
                data_value,
                f"update_{self.sample_name}"
            )
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

        with allure.step(f"步骤4：删除产品样例") as step4:
            response = self.api_product_samples.samples_delete(self.productSampleId)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')


if __name__ == '__main__':
    pass
