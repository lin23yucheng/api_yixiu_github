import os
import random
import time
import json
import configparser
from pathlib import Path

# 获取项目根目录
PROJECT_ROOT = Path(__file__).parent.parent


def get_miai_product_code():
    """从配置文件中获取miai-product-code值"""
    config_path = PROJECT_ROOT / "config" / "env_config.ini"
    if not config_path.exists():
        print(f"错误：配置文件不存在 - {config_path}")
        return "JHOCT001"  # 默认值

    try:
        config = configparser.ConfigParser()
        config.read(config_path, encoding='utf-8')

        # 获取当前环境
        env = config.get("environment", "execution_env", fallback="").strip().lower()
        if env not in {"fat", "prod"}:
            print(f"execution_env 配置错误: {env}，仅支持 fat 或 prod")
            return "JHOCT001"  # 默认值

        # 从对应环境节读取
        env_section = f"{env}-yixiu"
        if config.has_option(env_section, 'miai-product-code'):
            return config.get(env_section, 'miai-product-code')
        else:
            print(f"配置文件中缺少{env_section}节或miai-product-code字段")
            return "JHOCT001"  # 默认值
    except Exception as e:
        print(f"读取配置文件时出错: {e}")
        return "JHOCT001"  # 默认值


def rename_files_and_modify_json():
    """重命名2D图像文件并修改对应的JSON文件"""
    # 获取产品代码
    miai_product_code = get_miai_product_code()
    print(f"使用的产品代码: {miai_product_code}")

    # 定义所有需要处理的2D图像文件夹
    base_path = PROJECT_ROOT / "testdata" / "brainstormGRpcClient" / "2.0" / "testdata" / "1" / "images"
    folders = [
        "defect",
        "defects",
        "limit",
        "normal",
        "sampling"
    ]

    # 处理每个文件夹
    for folder in folders:
        folder_path = base_path / folder

        if not folder_path.exists():
            print(f"警告：文件夹路径不存在 - {folder_path}")
            continue

        print(f"开始处理2D文件: {folder_path}")

        file_dict = {}
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                file_name, file_extension = os.path.splitext(file)
                if file_extension.lower() in ['.jpg', '.jpeg', '.png', '.json']:
                    if file_name not in file_dict:
                        # 生成随机部分
                        random_num1 = random.randint(10, 100)
                        random_num2 = random.randint(10, 100)
                        random_num3 = random.randint(1, 10)

                        # 生成时间戳部分
                        current_time = time.strftime("%Y%m%d%H%M%S") + str(time.time()).split('.')[1][:3]

                        # 构建新文件名（使用配置中的miai-product-code）
                        new_file_name = f"{random_num1}-{random_num2}-{random_num3}-{miai_product_code}-01-02-03-04-{current_time}"
                        file_dict[file_name] = new_file_name

                    # 获取新文件名
                    new_file_name = file_dict[file_name]
                    old_file_path = os.path.join(root, file)
                    new_file_path = os.path.join(root, new_file_name + file_extension)

                    try:
                        # 重命名文件
                        os.rename(old_file_path, new_file_path)
                        print(f"重命名: {file} -> {new_file_name}{file_extension}")

                        # 如果是JSON文件，更新其中的imagePath字段
                        if file_extension.lower() == '.json':
                            try:
                                with open(new_file_path, 'r') as f:
                                    data = json.load(f)

                                # 更新imagePath字段指向对应的图像文件
                                if 'imagePath' in data:
                                    # 查找对应的图像扩展名
                                    image_ext = None
                                    for ext in ['.jpg', '.jpeg', '.png']:
                                        if os.path.exists(os.path.join(root, new_file_name + ext)):
                                            image_ext = ext
                                            break

                                    if image_ext:
                                        data['imagePath'] = new_file_name + image_ext
                                        print(f"更新JSON文件: {new_file_name}.json -> 指向 {new_file_name}{image_ext}")
                                    else:
                                        print(f"警告: 未找到对应的图像文件 {new_file_name}.*")

                                # 写回文件
                                with open(new_file_path, 'w') as f:
                                    json.dump(data, f, indent=4)

                            except Exception as e:
                                print(f"处理JSON文件 {new_file_path} 时出错: {e}")

                    except FileExistsError:
                        print(f"文件 {new_file_path} 已存在，跳过重命名。")
                    except Exception as e:
                        print(f"重命名文件 {old_file_path} 时出错: {e}")

        print(f"完成处理文件夹: {folder_path}\n")

    print("所有2D文件夹处理完成")


if __name__ == "__main__":
    rename_files_and_modify_json()
