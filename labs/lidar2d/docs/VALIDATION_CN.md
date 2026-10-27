# 二维平台验证记录

日期：2026-10-27。以下为实际执行结果，**不是 C1、实体手柄或水池实测**。

## 仓库审查与复用决策

起点：主仓库 `origin/main` 提交 `bf7d600`。开发分支 `feat/lidar-slam-2d` 使用单独 checkout，原工作目录及其未跟踪资料保持原样。

检查了根目录 `AGENTS.md`、`pyproject.toml`、`README.md`、`python/cocommand/simulation.py`、`python/cocommand/hardware.py`、原测试与构建说明：

- 现有船模是研究用 3-DOF 动力学并依赖原生控制器，与本次轻量独立平台不匹配，未直接导入。
- 原扫描/障碍物结构服务于研究算法，未作为 SLAM 的真值或定位输入。
- 保留原项目的观测边界、模拟/真实输出分离、人工油门权限原则，通过新 `Scan` 和仅返回舵角的扩展接口表达。
- 研究代码没有修改。主目录只增加入口说明、忽略规则、独立 CI 和实现状态记录。

## 已执行检查

| 检查 | 实际结果 |
|---|---|
| Windows Python 3.11.18 新平台 pytest | 39/39 通过 |
| Windows Python 3.12.14 新平台 pytest | 39/39 通过 |
| 原项目重新配置/编译 | Release 成功，Clang 21.1.0 / Zig 包装器 |
| 原 CTest | 1/1 原生测试程序通过 |
| 原 `python -m unittest discover -s tests/python -v` | 29/29 通过 |
| 官方 SDK + 新 C1 桥接 Windows 编译 | 成功；第三方 SDK 存在零长度数组、pragma 等编译警告 |
| 虚构串口连接失败路径 | 明确打印端口、460800、8N1、SDK 错误；退出码 2 |
| 本机串口列举 | 0 个端口，显示连接适配器/检查驱动提示 |
| 300 帧虚拟扫描记录 | 成功；帧时间 0.1 s，共 30 s 合成场景 |
| 离线重放 | 300 帧；全部栅格数组及估计轨迹与在线结果完全一致 |
| Windows 实际 GUI 启动 | Python 3.11，1200 渲染帧、221 扫描帧；截图人工视觉检查完成 |
| 真实雷达模式错误 GUI | 虚构端口，300 渲染帧；连接错误、1/2/4 秒重试、STALE 提示和正常退出通过 |
| GUI 离线回放 | 150 帧扫描重新建图，显示 REPLAY / OFFLINE；截图检查完成 |
| 手柄模拟量/断连 | 注入模拟轴与设备移除事件，比例输入与归零保护通过 |
| C1 实体、实体手柄、真实船舶、ARM 板 | **未验证** |

测试内容还包括顺/逆时针和安装角转换、毫米/米转换、异常回波、数据只读性、标准格式与损坏行、死区和单扳机映射、校准后的非对称轴、可配置模拟 PWM、过期输入与重新启用、油门权限、射线几何、碰撞、占据/自由/未知空间、三组噪声种子的平移转向估计、圆形及走廊退化、突然搬移拒绝、SDK 模拟进程重连与卡死清理、最新帧队列、离线数据时效标记和 GUI 渲染。

圆形对称环境最初暴露了退化检测缺陷：逐列归一化会放大接近零的航向信息。现改为按扫描距离尺度归一化旋转项；圆形与平行走廊测试均能拒绝退化更新。

## 数值结果与解释

固定 seed=7、500 点/圈、1 cm 距离噪声，30 秒开环比例输入：

| 指标 | 结果 |
|---|---:|
| 成功处理 / 录制 | 300 / 300 帧 |
| 匹配拒绝 / 碰撞步 | 0 / 0 |
| 已观测栅格 | 20,802 |
| 平移 RMSE | 0.001669 m |
| 最终平移误差 | 0.000562 m |
| 航向 RMSE | 0.02368° |
| 含录制的处理 P50 / P95 | 21.24 / 27.87 ms |
| 同文件回放处理 P50 / P95 | 19.62 / 25.47 ms |
| 实际 GUI 中处理 P50 / P95 | 18.81 / 25.26 ms |

误差在**第一帧坐标系**内评价，只进行初始位姿坐标变换，没有用拟合轨迹对齐去减小误差。真值仅由运行编排中的评价器读取，未进入 `LidarSlam.update(scan)`。本例完整回转没有使用回环优化。

这些很小的误差来自理想化静态多边形、无扫描畸变的合成环境，**不代表真实 C1 精度**。P95 只衡量本机本次软件处理耗时，既不是最坏耗时，也不是雷达采样到舵机的端到端延迟保证。并行运行的测试和 GUI 可能影响时序测量。

实际截图：[screenshot.png](evidence/screenshot.png)。机器可读汇总：[results.json](evidence/results.json)。pytest 报告：[Python 3.11](evidence/pytest311.xml)、[Python 3.12](evidence/pytest312.xml)，已去除本机 hostname。

原始扫描、运行目录、虚拟环境、SDK checkout 和编译产物不提交 Git；按 README 的命令可重新生成。当前 Windows 便携 ZIP 只包含独立 SLAM 平台、合成示例扫描、可迁移运行时与 C1 桥接程序，不包含主项目研究内容、完整 SDK 源码或数据手册。

## Windows 便携包运行检查

便携包的独立 Python 3.11.18 运行时实际执行了 39 项测试，全部通过；300 帧无界面仿真和包内示例回放均达到 `TRACKING`，生成 20,802 个已观测栅格。普通仿真、自动演示、示例回放的三个 CMD 入口均成功启动真实图形窗口，正常关闭并保存结果。图形界面截图已检查。

打包前再次运行原项目 CTest（1/1）和 Python unittest（29/29），均通过。ZIP 中只收录 Git 索引中的项目源码、明确选定的运行组件和示例；不收录开发虚拟环境、Git 元数据或临时运行目录。每个分发文件的 SHA-256 记录在 `PACKAGE_SHA256.json`。

## 后续验收

1. 桌面 C1 四方向/已知距离验证，连续扫描频率和真实延迟测量。
2. 慢速手持运动、遮挡、拔插、断电、恢复、退出停止扫描检查。
3. 实体手柄的轴编号、正负方向、校准、死区、热插拔与安全中位检查。
4. 水池光照/反射、船体遮挡、安装偏角、运动去畸变需求与真值对照。

代码提交 `874cab6` 的[远端平台 CI](https://github.com/Zhang-GTIIT/CoCommand-USV-Authority-Consistent-Predictive-Safety-Filtering-for-Shared-Vessel-Control/actions/runs/40476873396) **6/6 任务成功**：Windows/Linux × Python 3.11/3.12 的测试、仿真和回放，以及 Windows/Linux SDK 桥接构建。同一提交的[原项目 CI](https://github.com/Zhang-GTIIT/CoCommand-USV-Authority-Consistent-Predictive-Safety-Filtering-for-Shared-Vessel-Control/actions/runs/40476873363)也成功。

首轮远端检查中，Linux 新平台测试、SDK 构建以及原项目回归通过；Windows 在 checkout 时因原仓库历史材料路径超过 MAX_PATH 失败，尚未运行测试。工作流已设置 Git `core.longpaths`，并关闭矩阵 fail-fast 以保留各平台独立结果。

启用长路径后，Windows/Linux × Python 3.11/3.12 四个任务均通过。Windows SDK 的编译器识别仍受长构建路径影响，工作流对 SDK 构建采用短临时目录和工作区盘符映射后也通过。本地桥接另由 Clang 工具链编译成功。
