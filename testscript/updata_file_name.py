import os
import random
import time
import json


# 将文件夹中所有同名文件改为规定格式，同时修改json里imagePath值与名称一致
def rename_files_and_modify_json(folder_path):
    file_dict = {}
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            file_name, file_extension = os.path.splitext(file)
            if file_extension in ['.jpg', '.json']:
                if file_name not in file_dict:
                    random_num1 = random.randint(10, 100)
                    random_num2 = random.randint(10, 100)
                    random_num3 = random.randint(10, 100)
                    current_time = time.strftime("%Y%m%d%H%M%S") + str(time.time()).split('.')[1][:3]
                    new_file_name = f"{random_num1}-{random_num2}-{random_num3}-SYG003-01-01-01-01-{current_time}"
                    # new_file_name = f"1390-0101-01-需要替换的设备或产品名称-01-01-01-01-{current_time}"
                    file_dict[file_name] = new_file_name
                new_file_name = file_dict[file_name]
                old_file_path = os.path.join(root, file)
                new_file_path = os.path.join(root, new_file_name + file_extension)
                os.rename(old_file_path, new_file_path)
                if file_extension == '.json':
                    # 修改 JSON 文件中的 imagePath 值
                    with open(new_file_path, 'r') as f:
                        data = json.load(f)
                        if 'imagePath' in data:
                            data['imagePath'] = new_file_name + '.jpg'
                    with open(new_file_path, 'w') as f:
                        json.dump(data, f)


folder_path = input("请输入文件夹路径：")
rename_files_and_modify_json(folder_path)
