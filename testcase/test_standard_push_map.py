"""
GRPC推图
"""
import os
import json
import configparser
import subprocess
import logging
import allure
import pytest
import importlib.util
from pathlib import Path
from common import Assert
from api.api_space import ApiSpace

assertions = Assert.Assertions()

# 获取项目根目录（基于当前脚本位置）
PROJECT_ROOT = Path(__file__).parent.parent

# 读取配置 - 使用绝对路径
config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'env_config.ini')
config = configparser.ConfigParser()
config.read(config_path, encoding="utf-8")

# 获取当前环境并从对应环境节读取
_env = config.get("environment", "execution_env", fallback="").strip().lower()
if _env not in {"fat", "prod"}:
    raise ValueError(f"execution_env 配置错误: {_env}，仅支持 fat 或 prod")

_env_section = f"{_env}-yixiu"
space_name = config.get(_env_section, "space_name")
miai_product_code = config.get(_env_section, "miai-product-code")

# 推图命令
grpc_command = config.get(_env_section, "grpc_command")

# 初始化日志记录器
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# 创建控制台处理器
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)

# 设置日志格式
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)

# 添加处理器到日志记录器
logger.addHandler(ch)

# 获取项目根目录
PROJECT_ROOT = Path(__file__).parent.parent


def run_renaming_scripts():
    """执行2D和3D图像重命名脚本"""
    try:
        logger.info("开始执行2D和3D图像重命名脚本")

        # 导入并执行2D重命名脚本
        spec_2d = importlib.util.spec_from_file_location(
            "update_2d_name",
            PROJECT_ROOT / "common" / "update_2d_name.py"
        )
        module_2d = importlib.util.module_from_spec(spec_2d)
        spec_2d.loader.exec_module(module_2d)
        module_2d.rename_files_and_modify_json()
        logger.info("2D图像重命名完成")

        # 导入并执行3D重命名脚本
        spec_3d = importlib.util.spec_from_file_location(
            "update_3d_name",
            PROJECT_ROOT / "common" / "update_3d_name.py"
        )
        module_3d = importlib.util.module_from_spec(spec_3d)
        spec_3d.loader.exec_module(module_3d)
        module_3d.rename_files_and_modify_json()
        logger.info("3D图像重命名完成")

        return True

    except Exception as e:
        logger.error(f"执行重命名脚本时出错: {str(e)}")
        return False


def update_data_json():
    """更新data.json文件内容"""
    try:
        # 1. 读取accessToken.txt
        token_path = PROJECT_ROOT / "testdata" / "accessToken.txt"
        access_token = ""
        if token_path.exists():
            with open(token_path, 'r') as f:
                access_token = f.read().strip()
            logger.info(f"成功读取Token文件: {token_path}")
        else:
            logger.warning(f"Token文件不存在: {token_path}")
            return False

        # 2. 读取配置文件获取miai-product-code和device_no
        config_path = PROJECT_ROOT / "config" / "env_config.ini"
        miai_product_code = ""
        device_no = ""
        if config_path.exists():
            config = configparser.ConfigParser()
            config.read(config_path, encoding="utf-8")

            # 获取当前环境并从对应环境节读取
            env = config.get("environment", "execution_env", fallback="").strip().lower()
            if env not in {"fat", "prod"}:
                logger.warning(f"execution_env 配置错误: {env}，仅支持 fat 或 prod")
                return False

            env_section = f"{env}-yixiu"
            if config.has_section(env_section):
                try:
                    miai_product_code = config.get(env_section, 'miai-product-code')
                    logger.info(f"成功读取miai-product-code: {miai_product_code}")
                except configparser.NoOptionError:
                    logger.warning("配置文件中缺少miai-product-code字段")
                    return False

                try:
                    device_no = config.get(env_section, 'device_no')
                    logger.info(f"成功读取device_no: {device_no}")
                except configparser.NoOptionError:
                    logger.warning("配置文件中缺少device_no字段")
                    return False
            else:
                logger.warning(f"配置文件中缺少节: [{env_section}]")
                return False
        else:
            logger.warning(f"配置文件不存在: {config_path}")
            return False

        # 3. 修改data.json
        data_json_path = PROJECT_ROOT / "testdata" / "brainstormGRpcClient" / "2.0" / "testdata" / "1" / "data.json"
        if data_json_path.exists():
            with open(data_json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 更新字段
            data["access_token"] = access_token
            data["device_no"] = device_no
            data["product_name"] = miai_product_code

            # 写回文件
            with open(data_json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)

            logger.info(f"成功更新data.json: {data_json_path}")

            # 记录更新后的内容到Allure报告
            updated_content = json.dumps(data, indent=4, ensure_ascii=False)
            allure.attach(
                updated_content,
                name="更新后的data.json内容",
                attachment_type=allure.attachment_type.JSON
            )

            return True
        else:
            logger.error(f"data.json文件不存在: {data_json_path}")
            return False

    except Exception as e:
        logger.error(f"更新data.json时出错: {str(e)}")
        return False


def execute_grpc_command():
    """执行GRPC命令"""
    try:

        # 目标目录
        target_dir = PROJECT_ROOT / "testdata" / "brainstormGRpcClient" / "2.0"

        # 切换到目标目录
        os.chdir(target_dir)
        logger.info(f"切换到目录: {target_dir}")

        # 记录当前目录内容到报告
        dir_contents = "\n".join(os.listdir(target_dir))
        allure.attach(
            dir_contents,
            name="目标目录内容",
            attachment_type=allure.attachment_type.TEXT
        )

        # 执行命令
        logger.info(f"执行命令: {grpc_command}")
        result = subprocess.run(
            grpc_command,
            shell=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # 将 stderr 重定向到 stdout
            text=True,
            encoding='utf-8'
        )

        # 记录输出
        if result.stdout:
            logger.info(f"命令标准输出:\n{result.stdout}")

        if result.stderr:
            # 检查内容是否包含错误关键字
            if "ERROR" in result.stderr or "WARNING" in result.stderr:
                logger.warning(f"命令错误输出:\n{result.stderr}")
            else:
                logger.info(f"命令日志输出:\n{result.stderr}")  # 作为普通日志记录

        # 将输出附加到Allure报告
        allure.attach(
            result.stdout if result.stdout else "无输出",
            name="命令标准输出",
            attachment_type=allure.attachment_type.TEXT
        )

        if result.stderr:
            # 根据内容决定附件名称
            attachment_name = "命令错误输出" if ("ERROR" in result.stderr) else "命令日志输出"
            allure.attach(
                result.stderr,
                name=attachment_name,
                attachment_type=allure.attachment_type.TEXT
            )

        return True

    except subprocess.CalledProcessError as e:
        logger.error(f"命令执行失败: {e}")
        logger.error(f"错误输出:\n{e.stderr}")

        # 附加错误信息到报告
        allure.attach(
            f"命令执行失败: {str(e)}\n错误输出:\n{e.stderr}",
            name="命令执行错误",
            attachment_type=allure.attachment_type.TEXT
        )

        return False
    except Exception as e:
        logger.error(f"执行命令时出错: {str(e)}")

        # 附加错误信息到报告
        allure.attach(
            f"执行命令时出错: {str(e)}",
            name="命令执行错误",
            attachment_type=allure.attachment_type.TEXT
        )

        return False


@allure.feature("GRPC推图")
class TestStandardPushMap:
    @allure.story("更新配置并执行GRPC命令")
    def test_execute_grpc_command(self):
        """测试更新配置并执行GRPC命令"""
        # with allure.step("步骤1：验证一休机台管理"):
        #     # 初始化一休云空间API
        #     api_space = ApiSpace()
        #     device_id = None  # 用于存储设备ID
        #
        #     # 第一次查询机台列表
        #     response = api_space.machine_query()
        #     assertions.assert_code(response.status_code, 200)
        #     data = response.json()
        #
        #     # 检查响应是否成功
        #     if not data.get("success", False):
        #         error_msg = f"查询机台失败: {data.get('msg', '未知错误')}"
        #         allure.attach(error_msg, name="机台查询错误", attachment_type=allure.attachment_type.TEXT)
        #         raise AssertionError(error_msg)
        #
        #     # 判断是否有数据
        #     has_data = 'data' in data and data['data'].get('list') is not None and len(data['data']['list']) > 0
        #     found_device = False
        #
        #     # 如果有数据，检查是否有目标设备
        #     if has_data:
        #         for machine in data['data']['list']:
        #             if (machine.get('spaceName') == space_name and
        #                     machine.get('localDeviceNo') == miai_product_code):
        #                 # 提取cloudDeviceNo值
        #                 device_id = machine.get('cloudDeviceNo')
        #                 if device_id:
        #                     found_device = True
        #                     allure.attach(f"找到匹配机台: {machine}",
        #                                   name="机台详情",
        #                                   attachment_type=allure.attachment_type.JSON)
        #                     allure.attach(f"提取机台ID: {device_id}",
        #                                   name="机台ID",
        #                                   attachment_type=allure.attachment_type.TEXT)
        #                     break
        #
        #     # 如果没有数据或没有找到目标设备，添加机台并再次查询
        #     if not has_data or not found_device:
        #         with allure.step("子步骤1：添加机台"):
        #             response = api_space.machine_add()
        #             assertions.assert_code(response.status_code, 200)
        #             add_data = response.json()
        #
        #             if not add_data.get("success", False):
        #                 error_msg = f"添加机台失败: {add_data.get('msg', '未知错误')}"
        #                 allure.attach(error_msg, name="添加机台错误", attachment_type=allure.attachment_type.TEXT)
        #                 raise AssertionError(error_msg)
        #
        #             allure.attach("已添加新机台",
        #                           name="添加机台成功",
        #                           attachment_type=allure.attachment_type.TEXT)
        #
        #         with allure.step("子步骤2：再次查询机台列表"):
        #             response = api_space.machine_query()
        #             assertions.assert_code(response.status_code, 200)
        #             data = response.json()
        #
        #             if not data.get("success", False):
        #                 error_msg = f"再次查询机台失败: {data.get('msg', '未知错误')}"
        #                 allure.attach(error_msg, name="机台查询错误", attachment_type=allure.attachment_type.TEXT)
        #                 raise AssertionError(error_msg)
        #
        #             # 检查是否有数据
        #             if 'data' not in data or not data['data'].get('list'):
        #                 error_msg = "机台列表仍为空，添加机台后未找到机台"
        #                 allure.attach(error_msg, name="机台数据为空错误", attachment_type=allure.attachment_type.TEXT)
        #                 raise AssertionError(error_msg)
        #
        #             # 在机台列表中查找目标设备
        #             found_device = False
        #             for machine in data['data']['list']:
        #                 if (machine.get('spaceName') == space_name and
        #                         machine.get('localDeviceNo') == miai_product_code):
        #                     # 提取cloudDeviceNo值
        #                     device_id = machine.get('cloudDeviceNo')
        #                     if device_id:
        #                         found_device = True
        #                         allure.attach(f"找到新添加机台: {machine}",
        #                                       name="机台详情",
        #                                       attachment_type=allure.attachment_type.JSON)
        #                         allure.attach(f"提取机台ID: {device_id}",
        #                                       name="机台ID",
        #                                       attachment_type=allure.attachment_type.TEXT)
        #                         break
        #
        #             # 如果第二次查询后仍未找到设备ID
        #             if not found_device:
        #                 error_msg = "添加机台后仍未找到目标机台"
        #                 allure.attach(error_msg, name="机台缺失错误", attachment_type=allure.attachment_type.TEXT)
        #                 raise AssertionError(error_msg)
        #
        # with allure.step("步骤2：下载设备Token"):
        #     # 确保设备ID存在
        #     if not device_id:
        #         error_msg = "机台ID缺失，无法下载Token"
        #         allure.attach(error_msg, name="机台ID缺失错误", attachment_type=allure.attachment_type.TEXT)
        #         raise AssertionError(error_msg)
        #
        #     # 下载机台Token
        #     token_path = api_space.machine_token_download(device_id)
        #     if not token_path:
        #         error_msg = "下载机台Token失败"
        #         allure.attach(error_msg, name="Token下载错误", attachment_type=allure.attachment_type.TEXT)
        #         raise AssertionError(error_msg)
        #
        #     # 记录下载成功信息
        #     allure.attach(f"Token文件路径: {token_path}",
        #                   name="Token下载成功",
        #                   attachment_type=allure.attachment_type.TEXT)
        #
        #     # 读取并记录Token内容
        #     try:
        #         with open(token_path, 'r') as f:
        #             token_content = f.read()
        #             allure.attach(f"机台Token: {token_content}",
        #                           name="Token内容",
        #                           attachment_type=allure.attachment_type.TEXT)
        #     except Exception as e:
        #         error_msg = f"读取Token文件失败: {str(e)}"
        #         allure.attach(error_msg, name="Token读取错误", attachment_type=allure.attachment_type.TEXT)

        with allure.step("步骤1：执行2D和3D图像重命名"):
            renaming_success = run_renaming_scripts()
            assert renaming_success, "2D/3D图像重命名失败"

            # 在Allure报告中记录结果
            allure.attach(
                f"重命名结果: {'成功' if renaming_success else '失败'}",
                name="图像重命名状态",
                attachment_type=allure.attachment_type.TEXT
            )

        # 如果重命名失败，直接终止测试
        if not renaming_success:
            pytest.fail("2D/3D图像重命名失败，终止测试")

        with allure.step("步骤2：更新data.json配置"):
            update_success = update_data_json()

            # 使用标准的Python断言替代自定义断言
            assert update_success, "更新data.json失败"

            # 在Allure报告中记录更新结果
            allure.attach(
                f"更新结果: {'成功' if update_success else '失败'}",
                name="data.json更新状态",
                attachment_type=allure.attachment_type.TEXT
            )

        with allure.step("步骤3：执行GRPC命令"):
            command_success = execute_grpc_command()

            # 使用标准的Python断言替代自定义断言
            assert command_success, "执行GRPC命令失败"

            # 在Allure报告中记录执行结果
            allure.attach(
                f"命令执行结果: {'成功' if command_success else '失败'}",
                name="GRPC命令执行状态",
                attachment_type=allure.attachment_type.TEXT
            )


if __name__ == "__main__":
    # 直接运行时的测试逻辑
    print("===== 开始执行GRPC命令测试 =====")

    # 执行2D和3D图像重命名
    print("--- 执行2D和3D图像重命名 ---")
    if run_renaming_scripts():
        print("2D/3D图像重命名成功")

        # 更新data.json
        if update_data_json():
            print("data.json更新成功")

            # 执行命令
            if execute_grpc_command():
                print("GRPC命令执行成功")
            else:
                print("GRPC命令执行失败")
        else:
            print("data.json更新失败，终止执行")
    else:
        print("2D/3D图像重命名失败，终止执行")

    print("===== 测试结束 =====")
