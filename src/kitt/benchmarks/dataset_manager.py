"""Dataset management: load from HuggingFace or local directory."""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class DatasetManager:
    """Manage dataset loading from multiple sources."""

    @staticmethod
    def load_from_huggingface(
        dataset_id: str,
        split: str = "test",
        sample_size: int | None = None,
        text_field: str = "question",
    ) -> list[str]:
        """Load prompts from a HuggingFace dataset.

        Args:
            dataset_id: HuggingFace dataset identifier (e.g., 'cais/mmlu').
            split: Dataset split to use.
            sample_size: Maximum number of samples (None = all).
            text_field: Field name containing the prompt text.

        Returns:
            List of prompt strings.

        Raises:
            RuntimeError: If the datasets library is not installed.
        """
        try:
            from datasets import load_dataset
        except ImportError:
            raise RuntimeError(
                "HuggingFace datasets not installed. Install with: pip install datasets"
            ) from None

        logger.info(f"Loading dataset '{dataset_id}' split='{split}'...")
        dataset = load_dataset(dataset_id, split=split)

        prompts = []
        for item in dataset:
            if text_field in item:
                prompts.append(str(item[text_field]))
            elif "text" in item:
                prompts.append(str(item["text"]))
            elif "input" in item:
                prompts.append(str(item["input"]))
            else:
                # Use first string field
                for value in item.values():
                    if isinstance(value, str):
                        prompts.append(value)
                        break

        if sample_size is not None:
            prompts = prompts[:sample_size]

        logger.info(f"Loaded {len(prompts)} prompts from '{dataset_id}'")
        return prompts

    @staticmethod
    def load_from_directory(
        path: Path,
        sample_size: int | None = None,
    ) -> list[str]:
        """Load prompts from a local directory.

        Supports:
        - .jsonl files (one JSON object per line with 'prompt' or 'text' field)
        - .txt files (one prompt per line)
        - .json files (list of strings or list of objects with 'prompt' field)

        Args:
            path: Path to directory or file.
            sample_size: Maximum number of samples (None = all).

        Returns:
            List of prompt strings.
        """
        if path.is_file():
            prompts = DatasetManager._load_single_file(path)
        elif path.is_dir():
            prompts = []
            for ext in ["*.jsonl", "*.txt", "*.json"]:
                for file_path in sorted(path.glob(ext)):
                    prompts.extend(DatasetManager._load_single_file(file_path))
        else:
            raise FileNotFoundError(f"Dataset path not found: {path}")

        if sample_size is not None:
            prompts = prompts[:sample_size]

        logger.info(f"Loaded {len(prompts)} prompts from '{path}'")
        return prompts

    @staticmethod
    def _load_single_file(path: Path) -> list[str]:
        """Load prompts from a single file."""
        suffix = path.suffix.lower()

        if suffix == ".jsonl":
            return DatasetManager._load_jsonl(path)
        elif suffix == ".json":
            return DatasetManager._load_json(path)
        elif suffix == ".txt":
            return DatasetManager._load_txt(path)
        else:
            logger.warning(f"Unsupported file type: {path}")
            return []

    @staticmethod
    def _load_jsonl(path: Path) -> list[str]:
        """Load from JSONL (one JSON object per line)."""
        prompts = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if isinstance(obj, str):
                    prompts.append(obj)
                elif isinstance(obj, dict):
                    for key in ["prompt", "text", "input", "question"]:
                        if key in obj:
                            prompts.append(str(obj[key]))
                            break
        return prompts

    @staticmethod
    def _load_json(path: Path) -> list[str]:
        """Load from JSON file."""
        with open(path) as f:
            data = json.load(f)

        if isinstance(data, list):
            prompts = []
            for item in data:
                if isinstance(item, str):
                    prompts.append(item)
                elif isinstance(item, dict):
                    for key in ["prompt", "text", "input", "question"]:
                        if key in item:
                            prompts.append(str(item[key]))
                            break
            return prompts

        return []

    @staticmethod
    def _load_txt(path: Path) -> list[str]:
        """Load from text file (one prompt per line)."""
        with open(path) as f:
            return [line.strip() for line in f if line.strip()]
