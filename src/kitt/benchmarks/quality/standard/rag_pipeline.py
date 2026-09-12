"""RAG pipeline benchmark — end-to-end retrieval-augmented generation."""

import logging
import time
from typing import Any

from kitt.benchmarks.base import BenchmarkResult, LLMBenchmark
from kitt.benchmarks.registry import register_benchmark

logger = logging.getLogger(__name__)

# Simple built-in Q&A pairs with supporting documents
BUILT_IN_CORPUS = [
    {
        "question": "What is the speed of light?",
        "answer": "299792458",
        "documents": [
            "The speed of light in vacuum is exactly 299,792,458 metres per second.",
            "Light travels at different speeds through different media.",
            "Einstein's theory of relativity established that nothing can travel faster than light.",
        ],
    },
    {
        "question": "What year was the first moon landing?",
        "answer": "1969",
        "documents": [
            "Apollo 11 was the American spaceflight that first landed humans on the Moon in 1969.",
            "Neil Armstrong was the first person to walk on the Moon.",
            "The space race between the US and USSR dominated the 1960s.",
        ],
    },
    {
        "question": "What is the chemical symbol for gold?",
        "answer": "Au",
        "documents": [
            "Gold has the chemical symbol Au, from the Latin word 'aurum'.",
            "Gold is a transition metal with atomic number 79.",
            "Silver has the chemical symbol Ag.",
        ],
    },
]


class SimpleRetriever:
    """Simple TF-IDF-like retriever using word overlap scoring."""

    def __init__(self, documents: list[str]) -> None:
        self.documents = documents
        self._word_sets = [set(doc.lower().split()) for doc in documents]

    def retrieve(self, query: str, top_k: int = 3) -> list[str]:
        """Retrieve top_k most relevant documents for query."""
        query_words = set(query.lower().split())
        scores = []
        for i, word_set in enumerate(self._word_sets):
            overlap = len(query_words & word_set)
            total = len(query_words | word_set)
            score = overlap / total if total > 0 else 0
            scores.append((score, i))

        scores.sort(reverse=True)
        return [self.documents[i] for _, i in scores[:top_k]]


@register_benchmark
class RAGPipelineBenchmark(LLMBenchmark):
    """Benchmark end-to-end RAG pipeline performance."""

    name = "rag_pipeline"
    version = "1.0.0"
    category = "quality_standard"
    description = "End-to-end retrieval-augmented generation benchmark"

    def _execute(self, engine, config: dict[str, Any]) -> BenchmarkResult:
        corpus = config.get("corpus", BUILT_IN_CORPUS)
        max_tokens = config.get("max_tokens", 256)
        temperature = config.get("temperature", 0.0)
        top_k = config.get("top_k", 3)
        sample_size = config.get("sample_size")

        if sample_size and sample_size < len(corpus):
            corpus = corpus[:sample_size]

        # Build retriever from all documents
        all_docs = []
        for item in corpus:
            all_docs.extend(item.get("documents", []))
        retriever = SimpleRetriever(all_docs)

        outputs: list[dict[str, Any]] = []
        errors: list[str] = []
        correct = 0
        total = len(corpus)
        e2e_latencies: list[float] = []
        retrieval_latencies: list[float] = []
        generation_latencies: list[float] = []

        for i, item in enumerate(corpus):
            question = item["question"]
            expected = item.get("answer", "")

            try:
                # Retrieval phase
                retrieval_start = time.perf_counter()
                retrieved = retriever.retrieve(question, top_k=top_k)
                retrieval_ms = (time.perf_counter() - retrieval_start) * 1000
                retrieval_latencies.append(retrieval_ms)

                # Generation phase
                context = "\n".join(retrieved)
                prompt = self._build_prompt(question, context)

                gen_start = time.perf_counter()
                result = engine.generate(
                    prompt=prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                gen_ms = (time.perf_counter() - gen_start) * 1000
                generation_latencies.append(gen_ms)

                e2e_ms = retrieval_ms + gen_ms
                e2e_latencies.append(e2e_ms)

                answer = result.output.strip()
                is_correct = expected.lower() in answer.lower() if expected else True

                if is_correct:
                    correct += 1

                outputs.append(
                    {
                        "index": i,
                        "question": question,
                        "expected": expected,
                        "answer": answer[:200],
                        "correct": is_correct,
                        "retrieved_docs": len(retrieved),
                        "retrieval_ms": round(retrieval_ms, 2),
                        "generation_ms": round(gen_ms, 2),
                        "e2e_ms": round(e2e_ms, 2),
                    }
                )

            except Exception as e:
                errors.append(f"Question {i}: {e}")

        metrics: dict[str, Any] = {
            "answer_accuracy": round(correct / total, 4) if total else 0,
            "correct": correct,
            "total": total,
        }

        if e2e_latencies:
            metrics["e2e_latency_ms"] = round(
                sum(e2e_latencies) / len(e2e_latencies), 2
            )
        if retrieval_latencies:
            metrics["retrieval_latency_ms"] = round(
                sum(retrieval_latencies) / len(retrieval_latencies), 2
            )
        if generation_latencies:
            metrics["generation_latency_ms"] = round(
                sum(generation_latencies) / len(generation_latencies), 2
            )

        return BenchmarkResult(
            test_name=self.name,
            test_version=self.version,
            passed=len(errors) == 0,
            metrics=metrics,
            outputs=outputs,
            errors=errors,
        )

    def _build_prompt(self, question: str, context: str) -> str:
        return (
            f"Answer the following question using the provided context.\n\n"
            f"Context:\n{context}\n\n"
            f"Question: {question}\n\n"
            f"Answer:"
        )
