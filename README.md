# CodeGuard-NJU-26Summer
NJU26暑期智能软件工程师训练营课程作业-Coding Agent Harness
## API Key安全配置

本项目不硬编码任何密钥。首次运行时，程序会提示你输入OpenAI API Key，并自动存入系统钥匙串（macOS）/ 凭据管理器（Windows）。

如果使用Docker，请通过环境变量传入（严禁写入镜像）：
docker run -e OPENAI_API_KEY=$OPENAI_API_KEY 你的镜像名