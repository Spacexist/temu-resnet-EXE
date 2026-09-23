# 模型训练 · CPU 便携版

与 `KitchenRankPortable`（CUDA 版）并列，**源码一致**，仅 `runtime` 不同：

- **PyTorch CPU**（无 CUDA），体积约 **1GB 级**（原版 CUDA runtime 约 **5GB**）
- 向量/训练走 CPU，日更会慢一些，功能相同

## 使用

双击 `模型训练.bat`，操作与 CUDA 版相同。

## 数据目录

默认使用本目录下 `data_store/`。若要从 CUDA 版迁数据，可复制其 `data_store`（或只拷 `lgb`、`published`、模型权重）。

## 依赖重装（维护用）

双击 `环境安装.bat`。

脚本会优先复用 `D:\Desktop\自动组货\bundle\python-cpu` 里的 CPU 版 `torch/torchvision`，再安装项目依赖。若该目录不存在，会从 PyTorch CPU 源安装。

## 未附带 runtime 时

首次启动前先双击：

```bat
环境安装.bat
```

安装完成后再双击 `模型训练.bat`。若 `env` 缺失，`模型训练.bat` 也会自动调用安装脚本。
