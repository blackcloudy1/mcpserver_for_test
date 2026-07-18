# Windows Docker 前置条件

本机 Docker Desktop 4.73.0 已安装，但当前 WSL2 引擎无法启动。Docker 日志给出的错误为：

`HCS_E_HYPERV_NOT_INSTALLED`：未启用虚拟化或“虚拟机平台”Windows 可选组件。

请先完成以下一次性设置：

1. 在任务管理器的“性能 → CPU”确认“虚拟化”为“已启用”。若未启用，需要进入 BIOS/UEFI 开启 Intel VT-x/VT-d 或 AMD-V/SVM。
2. 使用管理员 PowerShell 运行：

   ```powershell
   wsl --install --no-distribution
   ```

3. 重启 Windows。
4. 启动 Docker Desktop，等待状态变成 Engine running。
5. 回到本目录执行：

   ```powershell
   docker compose -f compose.security-lab.yml build
   docker compose -f compose.security-lab.yml up -d
   docker compose -f compose.security-lab.yml ps
   ```

这些步骤会修改 Windows 可选功能并要求重启，因此没有在当前会话中自动执行。
