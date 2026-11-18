"""
产品资料接口自动化流程
包含：
1. 业务流程自动化（增删改查主流程）
2. 单接口数据驱动（增、查、改、删各自独立参数化）
"""
import pytest
import allure
import time
from common import Assert
from api import api_login, api_product_information
from common.Request_Response import ApiClient
from common.client_factory import create_lazy_yixiu_client
from common.Log import MyLog
from AI.semantic_assertion_engine import semantic_expected_failure

assertions = Assert.Assertions()
code = api_login.code
manageid = api_login.manageid
time_str = time.strftime("%Y%m%d%H%M%S", time.localtime())

# 全局懒加载客户端：仅在首次发送请求时才进行身份认证。
global_client = create_lazy_yixiu_client()


# ──────────────────────────────────────────────────────────
# Fixture：为修改/删除测试准备数据，测试结束后自动清理
# ──────────────────────────────────────────────────────────

@pytest.fixture(scope="class")
def api_instance():
    """提供产品资料API实例"""
    return api_product_information.ApiProductInformation(global_client)


@pytest.fixture(scope="function")
def uploaded_pdf(api_instance):
    """上传PDF文件，返回dataPath"""
    data_path = api_instance.upload_pdf()
    assert data_path, "PDF上传失败，返回空字符串"
    return data_path


@pytest.fixture(scope="function")
def created_information(api_instance, uploaded_pdf):
    """
    新增一个产品资料，供修改/删除测试使用。
    测试结束后自动删除（无论测试成功还是失败）。
    """
    info_name = f" fixture_{time_str}_{id(uploaded_pdf) % 10000}"
    add_resp = api_instance.information_add(uploaded_pdf, info_name)
    assert add_resp.status_code == 200, f"Fixture新增产品资料失败: {add_resp.text}"

    # 查询获取 productDataId
    query_resp = api_instance.information_query(info_name)
    data_list = query_resp.json().get('data', {}).get('list', [])
    product_data_id = None
    for item in data_list:
        if item.get('name') == info_name:
            product_data_id = item.get('productDataId')
            break

    assert product_data_id, f"Fixture未能查询到新增的产品资料: {info_name}"

    yield {
        "productDataId": product_data_id,
        "name": info_name,
        "dataPath": uploaded_pdf,
    }

    # ── teardown：测试结束后删除 ──
    try:
        with semantic_expected_failure("fixture清理：资料可能已被测试步骤删除"):
            del_resp = api_instance.information_delete(product_data_id)
        if del_resp.status_code == 200:
            MyLog.info(f"Fixture清理成功: 删除产品资料 {info_name}")
    except Exception as e:
        MyLog.warning(f"Fixture清理异常（可忽略）: {e}")


# ──────────────────────────────────────────────────────────
# 数据驱动场景定义
# ──────────────────────────────────────────────────────────

# 新增接口场景
ADD_SCENARIOS = [
    {"name": "正常新增",         "info_name": f"ADD_OK_{time_str}",      "expect_success": True},
    {"name": "名称为空字符串",    "info_name": "",                        "expect_success": False, "expect_msg_contains": "名称"},
    {"name": "名称超长",         "info_name": "A" * 200,                 "expect_success": False},
]

# 查询接口场景
QUERY_SCENARIOS = [
    {"name": "精确查询-存在",     "query_name": f"Q_EXIST_{time_str}",    "prepare": True,  "expect_found": True},
    {"name": "精确查询-不存在",   "query_name": f"Q_NOT_FOUND_{time_str}", "prepare": False, "expect_found": False},
    {"name": "模糊查询",          "query_name": f"Q_FUZZY_{time_str}",     "prepare": True,  "expect_found": True, "use_fuzzy": True},
]

# 修改接口场景
UPDATE_SCENARIOS = [
    {"name": "正常修改",          "expect_success": True,  "target_exists": True},
    {"name": "修改不存在的数据",   "expect_success": False, "target_exists": False, "expect_msg_contains": "不存在"},
]

# 删除接口场景
DELETE_SCENARIOS = [
    {"name": "正常删除",          "expect_success": True,  "target_exists": True},
    {"name": "删除不存在的数据",   "expect_success": False, "target_exists": False},
]


# ──────────────────────────────────────────────────────────
# 测试类
# ──────────────────────────────────────────────────────────

@pytest.mark.product_info
@allure.feature("场景：单产品-产品资料流程")
class TestProductInformation:
    @classmethod
    def setup_class(cls):
        cls.api_product_information = api_product_information.ApiProductInformation(global_client)
        cls.information_name = f"CS_{time_str}"
        cls.productDataId = None

    # ── 1. 原有业务流程（保留） ──
    @allure.story("产品资料增删改查-业务流程")
    def test_product_samples(self):
        with allure.step(f"步骤1：新增产品资料") as step1:
            information_dataPath = self.api_product_information.upload_pdf()
            response = self.api_product_information.information_add(information_dataPath, self.information_name)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

        with allure.step(f"步骤2：查询产品资料") as step2:
            response = self.api_product_information.information_query(self.information_name)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

            data_list = response_data.get('data', {}).get('list', [])
            for item in data_list:
                if item.get('name') == self.information_name:
                    self.productDataId = item.get('productDataId')
                    break
            else:
                pytest.fail(f"未找到名称为 {self.information_name} 的产品资料")

        with allure.step(f"步骤3：修改产品资料") as step3:
            response = self.api_product_information.information_update(self.productDataId,
                                                                       information_dataPath,
                                                                       f"update_CS_{time_str}")
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

        with allure.step(f"步骤4：删除产品资料") as step4:
            response = self.api_product_information.information_delete(self.productDataId)
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()
            assertions.assert_in_text(response_data['msg'], '成功')

    # ── 2. 单接口数据驱动：新增 ──
    @allure.story("单接口-新增产品资料（数据驱动）")
    @pytest.mark.parametrize("scenario", ADD_SCENARIOS, ids=lambda s: s["name"])
    def test_add_information(self, api_instance, uploaded_pdf, scenario):
        with allure.step(f"执行场景: {scenario['name']}"):
            allure.attach(
                f"输入参数:\n"
                f"  name: {scenario['info_name']}\n"
                f"  expect_success: {scenario['expect_success']}",
                name="场景参数",
                attachment_type=allure.attachment_type.TEXT,
            )

            if scenario["expect_success"]:
                response = api_instance.information_add(uploaded_pdf, scenario["info_name"])
            else:
                with semantic_expected_failure(f"产品资料新增负向场景: {scenario['name']}"):
                    response = api_instance.information_add(uploaded_pdf, scenario["info_name"])
            response_data = response.json()

            if scenario["expect_success"]:
                assertions.assert_code(response.status_code, 200)
                assertions.assert_in_text(response_data['msg'], '成功')

                # 成功后记录ID方便追踪
                allure.attach(
                    f"新增成功，响应: {response_data}",
                    name="新增结果",
                    attachment_type=allure.attachment_type.TEXT,
                )
                # 清理：成功新增的数据需要删除
                data_list = api_instance.information_query(scenario["info_name"]).json().get('data', {}).get('list', [])
                for item in data_list:
                    if item.get('name') == scenario['info_name']:
                        api_instance.information_delete(item.get('productDataId'))
                        break
            else:
                # 预期失败场景
                assert response.status_code != 200 or '成功' not in response_data.get('msg', ''), \
                    f"场景 '{scenario['name']}' 预期失败，但接口返回成功"
                if scenario.get("expect_msg_contains"):
                    assert scenario["expect_msg_contains"] in response_data.get('msg', ''), \
                        f"预期错误信息包含 '{scenario['expect_msg_contains']}'，实际: {response_data.get('msg', '')}"

    # ── 3. 单接口数据驱动：查询 ──
    @allure.story("单接口-查询产品资料（数据驱动）")
    @pytest.mark.parametrize("scenario", QUERY_SCENARIOS, ids=lambda s: s["name"])
    def test_query_information(self, api_instance, uploaded_pdf, scenario):
        with allure.step(f"执行场景: {scenario['name']}"):
            query_name = scenario["query_name"]

            # 如果需要预先准备数据
            if scenario.get("prepare"):
                add_resp = api_instance.information_add(uploaded_pdf, query_name)
                assert add_resp.status_code == 200, f"预准备数据失败: {add_resp.text}"

            try:
                response = api_instance.information_query(query_name)
                response_data = response.json()
                data_list = response_data.get('data', {}).get('list', [])

                # 判断是否找到
                found = any(query_name in item.get('name', '') for item in data_list) if scenario.get("use_fuzzy") \
                    else any(item.get('name') == query_name for item in data_list)

                if scenario["expect_found"]:
                    assert found, f"预期能找到 '{query_name}'，但未找到"
                    assertions.assert_code(response.status_code, 200)
                else:
                    assert not found, f"预期找不到 '{query_name}'，但找到了"

            finally:
                # 清理预准备的数据
                if scenario.get("prepare"):
                    del_resp = api_instance.information_query(query_name)
                    for item in del_resp.json().get('data', {}).get('list', []):
                        if item.get('name') == query_name:
                            api_instance.information_delete(item.get('productDataId'))

    # ── 4. 单接口数据驱动：修改 ──
    @allure.story("单接口-修改产品资料（数据驱动）")
    @pytest.mark.parametrize("scenario", UPDATE_SCENARIOS, ids=lambda s: s["name"])
    def test_update_information(self, api_instance, uploaded_pdf, created_information, scenario):
        with allure.step(f"执行场景: {scenario['name']}"):
            if scenario.get("target_exists"):
                # 使用 fixture 创建的真实数据
                product_data_id = created_information["productDataId"]
                new_name = f"UPDATED_{time_str}"
            else:
                # 使用一个不存在的ID
                product_data_id = "999999999999"
                new_name = f"UPDATE_NOT_EXIST_{time_str}"

            if scenario["expect_success"]:
                response = api_instance.information_update(
                    product_data_id,
                    created_information["dataPath"] if scenario.get("target_exists") else uploaded_pdf,
                    new_name,
                )
            else:
                with semantic_expected_failure(f"产品资料修改负向场景: {scenario['name']}"):
                    response = api_instance.information_update(
                        product_data_id,
                        created_information["dataPath"] if scenario.get("target_exists") else uploaded_pdf,
                        new_name,
                    )
            response_data = response.json()

            if scenario["expect_success"]:
                assertions.assert_code(response.status_code, 200)
                assertions.assert_in_text(response_data['msg'], '成功')
            else:
                assert response.status_code != 200 or '成功' not in response_data.get('msg', ''), \
                    f"场景 '{scenario['name']}' 预期失败，但接口返回成功"
                if scenario.get("expect_msg_contains"):
                    assert scenario["expect_msg_contains"] in response_data.get('msg', ''), \
                        f"预期错误信息包含 '{scenario['expect_msg_contains']}'，实际: {response_data.get('msg', '')}"

    # ── 5. 单接口数据驱动：删除 ──
    @allure.story("单接口-删除产品资料（数据驱动）")
    @pytest.mark.parametrize("scenario", DELETE_SCENARIOS, ids=lambda s: s["name"])
    def test_delete_information(self, api_instance, uploaded_pdf, created_information, scenario):
        with allure.step(f"执行场景: {scenario['name']}"):
            if scenario.get("target_exists"):
                # 使用 fixture 创建的真实数据
                product_data_id = created_information["productDataId"]
            else:
                # 使用一个不存在的ID
                product_data_id = "999999999999"

            if scenario["expect_success"]:
                response = api_instance.information_delete(product_data_id)
            else:
                with semantic_expected_failure(f"产品资料删除负向场景: {scenario['name']}"):
                    response = api_instance.information_delete(product_data_id)
            response_data = response.json()

            if scenario["expect_success"]:
                assertions.assert_code(response.status_code, 200)
                assertions.assert_in_text(response_data['msg'], '成功')
            else:
                assert response.status_code != 200 or '成功' not in response_data.get('msg', ''), \
                    f"场景 '{scenario['name']}' 预期失败，但接口返回成功"


if __name__ == '__main__':
    pass
