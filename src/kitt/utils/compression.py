"""Compression and chunking for large result files."""

import gzip
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any


class ResultCompression:
    """Handle compression and chunking of large result files."""

    @staticmethod
    def save_outputs(
        outputs: list[Any],
        base_path: Path,
        chunk_size_mb: int = 50,
    ) -> list[Path]:
        """Save outputs with compression and chunking.

        Args:
            outputs: List of output objects to save.
            base_path: Base path for output files (without extension).
            chunk_size_mb: Target chunk size in MB.

        Returns:
            List of created file paths.
        """
        chunk_files: list[Path] = []
        chunk_num = 0
        current_chunk: list[str] = []
        current_size = 0.0

        for output in outputs:
            serialized = json.dumps(output, default=str) + "\n"
            size_mb = len(serialized.encode()) / (1024 * 1024)

            if current_size + size_mb > chunk_size_mb and current_chunk:
                chunk_path = ResultCompression._write_chunk(
                    current_chunk, base_path, chunk_num
                )
                chunk_files.append(chunk_path)
                chunk_num += 1
                current_chunk = []
                current_size = 0.0

            current_chunk.append(serialized)
            current_size += size_mb

        if current_chunk:
            chunk_path = ResultCompression._write_chunk(
                current_chunk, base_path, chunk_num
            )
            chunk_files.append(chunk_path)

        return chunk_files

    @staticmethod
    def _write_chunk(data: list[str], base_path: Path, chunk_num: int) -> Path:
        """Write compressed chunk to disk."""
        base_path.parent.mkdir(parents=True, exist_ok=True)
        filename = base_path.parent / f"{base_path.name}_chunk_{chunk_num:04d}.jsonl.gz"

        with gzip.open(filename, "wt", encoding="utf-8") as f:
            f.writelines(data)

        return Path(filename)

    @staticmethod
    def load_outputs(base_path: Path) -> Iterator[Any]:
        """Load outputs from chunked compressed files.

        Args:
            base_path: Base path used when saving.

        Yields:
            Parsed output objects.
        """
        pattern = f"{base_path.name}_chunk_*.jsonl.gz"
        chunk_files = sorted(base_path.parent.glob(pattern))

        for chunk_file in chunk_files:
            with gzip.open(chunk_file, "rt", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        yield json.loads(line)

    @staticmethod
    def save_single(data: Any, path: Path) -> Path:
        """Save a single object as compressed JSON.

        Args:
            data: Object to serialize and compress.
            path: Output path (will have .gz appended if not present).

        Returns:
            Path to the created file.
        """
        if not str(path).endswith(".gz"):
            path = Path(str(path) + ".gz")

        path.parent.mkdir(parents=True, exist_ok=True)

        with gzip.open(path, "wt", encoding="utf-8") as f:
            json.dump(data, f, default=str)

        return path

    @staticmethod
    def load_single(path: Path) -> Any:
        """Load a single compressed JSON file."""
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)
