"""
DMP获取机台token流程
"""
import os
import json
import configparser
from pathlib import Path
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
    def _get_active_yixiu_section(config):
        """根据 execution_env 返回当前一休环境节名。"""
        env = config.get("environment", "execution_env", fallback="").strip().lower()
        if env not in {"fat", "prod"}:
            raise ValueError(f"execution_env 配置错误: {env}，仅支持 fat 或 prod")

        env_section = f"{env}-yixiu"
        if not config.has_section(env_section):
            raise ValueError(f"配置文件缺少节: [{env_section}]")

        return env_section

    @staticmethod
    def _replace_ini_key_in_section(file_path, section_name, key, value):
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        default_newline = "\n"
        for line in lines:
            if line.endswith("\r\n"):
                default_newline = "\r\n"
                break
            if line.endswith("\n"):
                default_newline = "\n"
                break

        target_section = section_name.strip().lower()
        target_key = key.strip().lower()

        in_target_section = False
        section_found = False
        key_found = False
        insert_index = None

        for i, line in enumerate(lines):
            stripped = line.strip()

            if stripped.startswith("[") and stripped.endswith("]"):
                if in_target_section and insert_index is None:
                    insert_index = i
                current_section = stripped[1:-1].strip().lower()
                in_target_section = current_section == target_section
                section_found = section_found or in_target_section
                continue

            if not in_target_section:
                continue

            if not stripped or stripped.startswith(";") or stripped.startswith("#"):
                continue

            if "=" not in line:
                continue

            left, _, _ = line.partition("=")
            if left.strip().lower() != target_key:
                continue

            line_newline = ""
            if line.endswith("\r\n"):
                line_newline = "\r\n"
            elif line.endswith("\n"):
                line_newline = "\n"

            leading_ws = left[: len(left) - len(left.lstrip())]
            lines[i] = f"{leading_ws}{left.strip()} = {value}{line_newline}"
            key_found = True
            break

        if not section_found:
            raise ValueError(f"配置节不存在: [{section_name}]")

        if not key_found:
            if insert_index is None:
                insert_index = len(lines)
                if lines and not lines[-1].endswith(("\n", "\r\n")):
                    lines[-1] = lines[-1] + default_newline
            lines.insert(insert_index, f"{key} = {value}{default_newline}")

        with open(file_path, "w", encoding="utf-8", newline="") as f:
            f.writelines(lines)

    @staticmethod
    def write_device_no_to_config(device_no):
        config_path = str(Path(__file__).resolve().parents[1] / "config" / "env_config.ini")
        config = configparser.ConfigParser()
        config.read(config_path, encoding="utf-8")

        # 获取当前环境并写入对应环境节的 device_no
        env_section = TestGetAccessToken._get_active_yixiu_section(config)
        TestGetAccessToken._replace_ini_key_in_section(
            file_path=config_path,
            section_name=env_section,
            key="device_no",
            value=str(device_no),
        )

        # 回读校验，确保写入的是当前环境对应节
        verify_config = configparser.ConfigParser()
        verify_config.read(config_path, encoding="utf-8")
        actual_device_no = verify_config.get(env_section, "device_no", fallback="").strip()
        if actual_device_no != str(device_no):
            raise AssertionError(
                f"device_no 写入失败，目标节[{env_section}]期望={device_no}，实际={actual_device_no}"
            )

        return config_path, env_section

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
                pytest.fail("机器管理列表为空，无法获取sn")

            target_machine = next(
                (item for item in machine_list if str(item.get("machineId")) == str(self.machine_id)),
                None,
            )
            if not target_machine:
                pytest.fail(f"未在机器管理列表中找到 machineId={self.machine_id} 对应的数据，无法获取sn")

            allure.attach(
                json.dumps(target_machine, ensure_ascii=False, indent=2),
                name="目标机器信息",
                attachment_type=allure.attachment_type.JSON,
            )

            machine_no = target_machine.get("sn")
            if not machine_no:
                pytest.fail(f"machineId={self.machine_id} 对应机器数据sn为空")

            config_path, env_section = self.write_device_no_to_config(machine_no)
            allure.attach(str(machine_no), name="写入device_no", attachment_type=allure.attachment_type.TEXT)
            allure.attach(env_section, name="写入配置节", attachment_type=allure.attachment_type.TEXT)
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

