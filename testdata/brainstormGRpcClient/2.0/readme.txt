模拟中控调试接口2.0说明
单元测试，1:上传数据集\n",
		"2:完成数据集\n",
		"3:模型方案模版下发接口\n",
		"4:开始训练\n",
		"5:停止训练\n",
		"6:模型下发\n",
		"7:开始测试\n",
		"8:停止测试\n",

main.exe -h 命令查看帮助
  start       启动一休云gRPC服务
  test        测试一休云gRPC服务
  
main.ext test -h 命令查看测试命令帮助
Flags:
  -c, --config string   使用提供的配置文件启动服务器 (default "config/application-local.yml")
      --grpc string     配置grpc连接地址，如127.0.0.1:8001
  -h, --help            help for test
  -m, --method int32    单元测试，1:上传数据集
                        2:完成数据集
                        3:模型方案模版下发接口
                        4:开始训练（废弃）
                        5:停止训练
                        6:模型下发（废弃）
                        7:开始测试（废弃）
                        8:停止测试（废弃）
                        9:模型下发接收完成接口
                        10:模型检查更新
                        11:正在运行模型上报
                        12:产品和标签关联
                        13:标签及元数据同步

      --path string     选择测试需要读取的路径./testData，默认当前路径+测试编号 (default "./testData0")

例如
1:上传数据集
.\main.exe test --grpc=dev-yixiu-brainstorm-grpc.svfactory.com:9180 --path=.\testdata\1 --method=1

--grpc=dev-yixiu-brainstorm-grpc.svfactory.com:9180 表示连接dev环境的grpc，
--path=.\testdata\1 获取.\testdata\1里面的数据，
--method=1  执行方法1代表上传数据集

不指定--grpc地址，默认连接dev环境地址：dev-yixiu-brainstorm-grpc.svfactory.com:9180
不指定--path路径，默认寻找当前路径.\testdata\ + 方法索引
以上路径可以简化为 .\main.exe test -m=1
2;完成数据集
.\main.exe test --grpc=:58001 --path=.\testdata\2 --method=2

处理上传数据集需要准备图片目录，其它文件夹只需要json配置文件




main.exe test  --grpc=fat-yixiu-brainstorm-grpc.svfactory.com:9181 -m 1   （测试环境）
main.exe test  --grpc=dev-yixiu-brainstorm-grpc.svfactory.com:9180 -m 1   （DEV环境）
main.exe test  --grpc=yixiu-grpc.idmaic.cn:9181 -m 1  （生产环境）
main.exe test  --grpc=192.168.100.231:32001 -m 1  （私有化）
main.exe test  --grpc=172.16.8.110:32001 -m 1  （私有化）


