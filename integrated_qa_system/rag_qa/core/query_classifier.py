# -*- coding: utf-8 -*-
# 标准库
import json
import os
import sys
# 第三方库
import numpy as np
import torch
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from transformers import BertTokenizer, BertForSequenceClassification
from transformers import Trainer, TrainingArguments

# 路径设置：先把 rag_qa 和项目根目录加入 sys.path，再导入项目内模块（base.logger）。
# 否则从其他目录启动时 `from base import logger` 会 ImportError（与 core/vector_store.py 同样的问题）。
current_dir = os.path.dirname(os.path.abspath(__file__))  # core/
rag_qa_path = os.path.dirname(current_dir)                # rag_qa/
project_root = os.path.dirname(rag_qa_path)               # integrated_qa_system/
sys.path.insert(0, rag_qa_path)
sys.path.insert(0, project_root)
from base import logger


class QueryClassifier:
    # 数据集默认指向 classify_data 下已有的文件，避免依赖启动时的工作目录（cwd）
    DEFAULT_DATA_FILE = os.path.join(rag_qa_path, "classify_data", "model_generic_5000.json")

    def __init__(self, model_path=None):
        # 模型目录默认放在 rag_qa/bert_query_classifier，与 bge 系列模型同级，不依赖 cwd
        self.model_path = model_path or os.path.join(rag_qa_path, "bert_query_classifier")
        # 加载 BERT 分词器（模型已下载到本地 HuggingFace 缓存，离线可用）
        self.tokenizer = BertTokenizer.from_pretrained("bert-base-chinese")
        self.model = None
        # 区分"加载了已训练模型"与"随机初始化的新模型"，防止拿没训练过的模型做预测
        self.is_trained = False
        # 确定设备（GPU 或 CPU）
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        logger.info(f"使用设备: {self.device}")
        # 定义标签映射
        self.label_map = {"通用知识": 0, "专业咨询": 1}
        # 加载模型
        self.load_model()

    def load_model(self):
        # 检查模型路径是否存在
        if os.path.exists(self.model_path):
            # 加载预训练模型
            self.model = BertForSequenceClassification.from_pretrained(self.model_path)
            self.model.to(self.device)
            self.is_trained = True
            logger.info(f"加载已训练模型: {self.model_path}")
        else:
            # 目录不存在 → 说明还没训练过。初始化随机权重，仅用于 train_model() 训练阶段。
            self.model = BertForSequenceClassification.from_pretrained("bert-base-chinese", num_labels=2)
            self.model.to(self.device)
            self.is_trained = False
            logger.warning(
                f"未找到已训练模型目录 {self.model_path}，已初始化为随机权重。"
                "若仅用于预测，请先调用 train_model() 训练并保存模型。"
            )

    def save_model(self):
        """保存模型"""
        self.model.save_pretrained(self.model_path)
        self.tokenizer.save_pretrained(self.model_path)
        logger.info(f"模型保存至: {self.model_path}")

    def preprocess_data(self, texts, labels):
        """预处理数据为 BERT 输入格式"""
        encodings = self.tokenizer(
            texts,
            truncation=True,
            padding=True,
            max_length=128,
            return_tensors="pt"
        )
        return encodings, [self.label_map[label] for label in labels]

    def create_dataset(self, encodings, labels):
        """创建 PyTorch 数据集"""

        class Dataset(torch.utils.data.Dataset):
            def __init__(self, encodings, labels):
                self.encodings = encodings
                self.labels = labels

            def __getitem__(self, idx):
                item = {key: val[idx] for key, val in self.encodings.items()}
                item["labels"] = torch.tensor(self.labels[idx])
                return item

            def __len__(self):
                return len(self.labels)

        return Dataset(encodings, labels)

    def _load_dataset(self, data_file):
        """读取标注数据，同时兼容 JSONL（每行一个 JSON）和标准 JSON 数组两种格式。

        Args:
            data_file: 数据集文件路径。

        Returns:
            (texts, labels): 查询文本列表和对应的字符串标签列表。

        Raises:
            ValueError: 数据为空，或存在 label_map 之外的标签。
        """
        with open(data_file, "r", encoding="utf-8") as f:
            content = f.read()

        try:
            # 先尝试把整个文件当 JSON 解析（单个对象或数组）
            parsed = json.loads(content)
            items = parsed if isinstance(parsed, list) else [parsed]
        except json.JSONDecodeError:
            # 整体解析失败 → 按 JSONL 逐行解析，跳过空行
            items = [json.loads(line) for line in content.splitlines() if line.strip()]

        if not items:
            raise ValueError(f"数据集 {data_file} 为空")

        texts = [item["query"] for item in items]
        labels = [item["label"] for item in items]
        unknown = set(labels) - set(self.label_map)
        if unknown:
            raise ValueError(f"数据集存在未定义标签 {unknown}，目前支持: {list(self.label_map)}")
        return texts, labels

    def train_model(self, data_file=DEFAULT_DATA_FILE):
        """训练 BERT 分类模型"""
        # 加载数据集
        if not os.path.exists(data_file):
            logger.error(f"数据集文件 {data_file} 不存在")
            raise FileNotFoundError(f"数据集文件 {data_file} 不存在")

        texts, raw_labels = self._load_dataset(data_file)
        logger.info(
            f"加载数据集: {len(texts)} 条，"
            f"类别分布: {dict(zip(*np.unique(raw_labels, return_counts=True)))}"
        )

        # 数据划分
        # 类别不均衡时必须 stratify，否则小类可能被全部切到训练集/验证集导致训练塌掉
        split_kwargs = dict(test_size=0.2, random_state=42)
        if len(set(raw_labels)) > 1:
            split_kwargs["stratify"] = raw_labels
        train_texts, val_texts, train_labels, val_labels = train_test_split(
            texts, raw_labels, **split_kwargs
        )

        # 预处理（内部会把字符串标签映射为数字）
        train_encodings, train_labels = self.preprocess_data(train_texts, train_labels)
        val_encodings, val_labels = self.preprocess_data(val_texts, val_labels)

        # 创建数据集
        train_dataset = self.create_dataset(train_encodings, train_labels)
        val_dataset = self.create_dataset(val_encodings, val_labels)

        # 设置训练参数
        training_args = TrainingArguments(
            output_dir=os.path.join(rag_qa_path, "bert_results"),
            num_train_epochs=3,
            per_device_train_batch_size=8,
            per_device_eval_batch_size=8,
            warmup_ratio=0.06,  # 按总步数比例预热，比固定 warmup_steps=500 更适合小数据集
            weight_decay=0.01,
            logging_dir=os.path.join(rag_qa_path, "bert_logs"),
            logging_steps=10,
            eval_strategy="epoch",
            save_strategy="epoch",
            load_best_model_at_end=True,
            save_total_limit=1,  # 只保存一个检查点，即最优的模型
            metric_for_best_model="eval_loss",
            fp16=False,  # 禁用混合精度
        )

        # 初始化 Trainer
        trainer = Trainer(
            model=self.model,
            args=training_args,
            train_dataset=train_dataset,
            eval_dataset=val_dataset,
            compute_metrics=self.compute_metrics
        )

        # 训练模型
        logger.info("开始训练 BERT 模型...")
        trainer.train()
        self.is_trained = True
        self.save_model()

        # 评估模型
        self.evaluate_model(val_texts, val_labels)

    def compute_metrics(self, eval_pred):
        """计算评估指标"""
        logits, labels = eval_pred
        predictions = np.argmax(logits, axis=-1)
        accuracy = (predictions == labels).mean()
        return {"accuracy": accuracy}

    def evaluate_model(self, texts, labels):
        """评估模型性能（labels 需为数字标签）"""
        # 仅对 texts 进行分词，labels 已为数字
        encodings = self.tokenizer(
            texts,
            truncation=True,
            padding=True,
            max_length=128,
            return_tensors="pt"
        )
        dataset = self.create_dataset(encodings, labels)

        trainer = Trainer(model=self.model, args=TrainingArguments(output_dir=os.path.join(rag_qa_path, "bert_results")))
        predictions = trainer.predict(dataset)
        pred_labels = np.argmax(predictions.predictions, axis=-1)
        true_labels = labels  # 直接使用数字标签

        logger.info("分类报告:")
        logger.info(classification_report(
            true_labels,
            pred_labels,
            target_names=list(self.label_map.keys())
        ))
        logger.info("混淆矩阵:")
        logger.info(confusion_matrix(true_labels, pred_labels))

    def predict_category(self, query):
        # 模型未加载 / 未训练时预测结果没有意义，直接抛错，
        # 避免路由层拿到"随机分类"还静默地把问题分流到错误模块
        if self.model is None:
            logger.error("模型未加载，无法进行分类")
            raise RuntimeError("模型未加载，无法进行分类")
        if not self.is_trained:
            logger.error("模型未训练，预测结果无意义。请先调用 train_model() 训练并保存模型。")
            raise RuntimeError("模型未训练，无法进行有意义分类")
        # 对查询进行编码
        encoding = self.tokenizer(query, truncation=True, padding=True, max_length=128, return_tensors="pt")
        # 将编码移到指定设备
        encoding = {k: v.to(self.device) for k, v in encoding.items()}
        # 不计算梯度，进行预测
        with torch.no_grad():
            # 获取模型输出
            outputs = self.model(**encoding)
            # 获取预测结果
            prediction = torch.argmax(outputs.logits, dim=1).item()
        # 根据预测结果返回类别
        return "专业咨询" if prediction == 1 else "通用知识"


if __name__ == "__main__":
    # 首次运行：当前还没有训练好的模型，先训练（自动使用 classify_data/model_generic_5000.json）。
    # 训练完成后模型保存在 rag_qa/bert_query_classifier/，之后可以注释掉 train_model 只做预测。
    classifier = QueryClassifier()
    #classifier.train_model()

    # 训练结束，跑几个示例预测
    test_queries = [
        "AI 产品的技术架构是什么",
        "数据库的索引优化怎么做？",
        "5*9等于多少？",
        "AI 有哪些主流框架？"
    ]
    for query in test_queries:
        category = classifier.predict_category(query)
        print(f"查询: {query} -> 分类: {category}")