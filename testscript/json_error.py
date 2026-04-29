import zipfile
import json


# 输出zip包中json格式异常的json名称
def check_json_files_in_zip(zip_file_path):
    with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
        for file_name in zip_ref.namelist():
            if file_name.endswith('.json'):
                with zip_ref.open(file_name) as json_file:
                    try:
                        json.loads(json_file.read().decode('utf-8'))
                    except json.JSONDecodeError:
                        print(file_name + " 格式异常")


zip_file_path = r'C:\Users\admin\Desktop\验证集_切图样本_20240724160224.zip'  # 请将此处替换为实际的 zip 文件路径
check_json_files_in_zip(zip_file_path)
