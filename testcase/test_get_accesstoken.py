"""
DMP获取机台token流程
"""
import os
import configparser
import pytest
import allure
from common import Assert
from common.Request_Response import ApiClient
from api import api_dmp, api_login

assertions = Assert.Assertions()


@allure.feature("场景：DMP-获取机台token")
class TestGetAccessToken:
    @classmethod
    def setup_class(cls):
        cls.client = ApiClient(base_headers={})
        cls.api_dmp = api_dmp.ApiDmp(cls.client)
        cls.machine_id = None

    @staticmethod
    def write_device_no_to_config(device_no):
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "config",
            "env_config.ini"
        )
        config = configparser.ConfigParser()
        config.read(config_path, encoding="utf-8")
        config.set("Inspection", "device_no", str(device_no))
        with open(config_path, "w", encoding="utf-8") as f:
            config.write(f)
        return config_path

    @allure.story("获取机台token")
    def test_get_machine_token(self):
        with allure.step("步骤1：登录dmp系统"):
            token = api_login.ApiLogin().login()
            if not token:
                pytest.fail("DMP登录失败，token为空")

            self.client.base_headers["Authorization"] = token
            self.client.base_headers["Miai-Product-Code"] = api_login.code
            self.client.base_headers["Miaispacemanageid"] = api_login.manageid
            allure.attach(token, name="DMP Token", attachment_type=allure.attachment_type.TEXT)

        with allure.step("步骤2：查询机器管理"):
            response = self.api_dmp.query_machine_manage()
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()

            machine_list = response_data.get("data", {}).get("list", [])
            if machine_list:
                self.machine_id = machine_list[-1].get("machineId")
                if not self.machine_id:
                    pytest.fail("机器管理存在数据但machineId为空")
                allure.attach(str(self.machine_id), name="已存在machineId", attachment_type=allure.attachment_type.TEXT)
            else:
                with allure.step("子步骤1：获取可选机器列表"):
                    optional_response = self.api_dmp.query_optional_machine_list()
                    assertions.assert_code(optional_response.status_code, 200)
                    optional_data = optional_response.json()
                    optional_list = optional_data.get("data", {}).get("list", [])

                    if not optional_list:
                        pytest.fail("无可选机器")

                    self.machine_id = optional_list[-1].get("machineId")
                    if not self.machine_id:
                        pytest.fail("可选机器存在数据但machineId为空")
                    allure.attach(str(self.machine_id), name="可选machineId", attachment_type=allure.attachment_type.TEXT)

                with allure.step("子步骤2：添加机器"):
                    add_response = self.api_dmp.add_machine(self.machine_id)
                    assertions.assert_code(add_response.status_code, 200)
                    add_data = add_response.json()
                    msg = add_data.get("msg", "")
                    if msg:
                        assertions.assert_in_text(msg, "成功")

        with allure.step("步骤3：获取机器sn写入配置文件"):
            response = self.api_dmp.query_machine_manage()
            assertions.assert_code(response.status_code, 200)
            response_data = response.json()

            machine_list = response_data.get("data", {}).get("list", [])
            if not machine_list:
                pytest.fail("机器管理列表为空，无法获取machineNo")

            machine_no = machine_list[-1].get("machineNo")
            if not machine_no:
                pytest.fail("最后一条机器数据machineNo为空")

            config_path = self.write_device_no_to_config(machine_no)
            allure.attach(str(machine_no), name="写入device_no", attachment_type=allure.attachment_type.TEXT)
            allure.attach(config_path, name="配置文件路径", attachment_type=allure.attachment_type.TEXT)

        with allure.step("步骤4：下载机台token"):
            if not self.machine_id:
                pytest.fail("缺少machineId，无法下载token")

            token_path = self.api_dmp.machine_token_download(self.machine_id)
            if not os.path.isfile(token_path):
                pytest.fail(f"token文件不存在: {token_path}")

            if os.path.basename(token_path) != "accessToken.txt":
                pytest.fail(f"token文件名错误: {token_path}")

            allure.attach(token_path, name="token文件路径", attachment_type=allure.attachment_type.TEXT)


if __name__ == '__main__':
    pass

