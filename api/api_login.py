"""
一休云登录环境封装
"""
import time
import os
import requests
import configparser

# 读取配置
config = configparser.ConfigParser()
config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "env_config.ini")
config.read(config_path, encoding="utf-8")

env = config.get("environment", "execution_env", fallback="").strip().lower()
if env not in {"fat", "prod"}:
    raise ValueError(f"execution_env 配置错误: {env}，仅支持 fat 或 prod")

section = f"{env}-yixiu"
if not config.has_section(section):
    raise ValueError(f"配置文件缺少节: [{section}]")

space_name = config.get(section, "space_name")
miai_product_code = config.get(section, "miai-product-code")
miaispacemanageid = config.get(section, "miaispacemanageid")

env_login_map = {
    "prod": {
        "token_url": "https://sso.svfactory.com/auth/realms/uuam/protocol/openid-connect/token",
        "username": "linyucheng",
        "password": "qwe123123",
        "url": "https://manage.svfactory.com",
    },
    "fat": {
        "token_url": "https://fat-sso.svfactory.com:6143/auth/realms/uuam/protocol/openid-connect/token",
        "username": "linyucheng",
        "password": "123456",
        "url": "https://fat-manage.svfactory.com:6143",
    },
}

token_url = env_login_map[env]["token_url"]
username = env_login_map[env]["username"]
password = env_login_map[env]["password"]
# 一休云地址
url = env_login_map[env]["url"]
# 一休云header所需配置
code = miai_product_code
manageid = miaispacemanageid


class ApiLogin:
    def __init__(self):
        pass

    def login(self, max_retries=5, retry_delay=3):
        login_data = {"client_id": "brainstorm-fe", "username": username, "password": password,
                      "grant_type": "password"}
        login_header = {"content-type": "application/x-www-form-urlencoded"}

        for attempt in range(max_retries):
            try:
                login_rep = requests.post(url=token_url, data=login_data, headers=login_header)

                # 检查响应状态
                if login_rep.status_code == 200:
                    response_json = login_rep.json()

                    # 验证必要字段是否存在
                    if "token_type" in response_json and "access_token" in response_json:
                        token_type = response_json["token_type"]
                        access_token = response_json["access_token"]
                        token = token_type + " " + access_token
                        return token
                    else:
                        print(f"第{attempt + 1}次尝试：响应缺少必要字段")
                else:
                    print(f"第{attempt + 1}次尝试：HTTP状态码 {login_rep.status_code}")

            except Exception as e:
                print(f"第{attempt + 1}次尝试失败：{str(e)}")

            # 如果不是最后一次尝试，则等待后重试
            if attempt < max_retries - 1:
                print(f"等待{retry_delay}秒后进行第{attempt + 2}次重试...")
                time.sleep(retry_delay)

        # 所有重试都失败
        raise Exception(f"登录失败，已重试{max_retries}次")


if __name__ == '__main__':
    m = ApiLogin()
    m.login()
