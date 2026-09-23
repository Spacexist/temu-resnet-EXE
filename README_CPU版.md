# 模型训练 · CPU 便携版

与 `KitchenRankPortable`（CUDA 版）并列，**源码一致**，仅 `runtime` 不同：

- **PyTorch CPU**（无 CUDA），体积约 **1GB 级**（原版 CUDA runtime 约 **5GB**）
- 向量/训练走 CPU，日更会慢一些，功能相同

## 使用

双击 `模型训练.bat`，操作与 CUDA 版相同。

## 数据目录

默认使用本目录下 `data_store/`。若要从 CUDA 版迁数据，可复制其 `data_store`（或只拷 `lgb`、`published`、模型权重）。

## 依赖重装（维护用）

```bat
runtime\base-python\Scripts\python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
runtime\base-python\Scripts\python.exe -m pip install -r screener\requirements.txt scikit-learn
```

## 未附带 runtime 时

`模型训练.bat` 会回退使用 `py -3`。首次启动前，为同一个 Python 安装依赖：

```bat
py -3 -m pip install -r screener\requirements.txt scikit-learn
```

这会安装清洗所需的 `zhconv` 和训练所需的 `lightgbm`。
