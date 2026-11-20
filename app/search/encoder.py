"""Локальный E5. Модель и токенизатор загружаются только при первом использовании."""
from functools import lru_cache
from math import isfinite
from threading import Lock
from typing import Protocol

from app.search.text import CHUNK_VERSION

MODEL_ID = "intfloat/multilingual-e5-small"
MODEL_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
INDEX_MODEL = f"{MODEL_ID}@{MODEL_REVISION}:{CHUNK_VERSION}"
DIMENSIONS = 384
WINDOW = 512
DEFAULT_THRESHOLD = 0.94
MODEL_FILES = [
    "config.json", "model.safetensors", "modules.json", "sentence_bert_config.json",
    "tokenizer.json", "tokenizer_config.json", "sentencepiece.bpe.model",
    "special_tokens_map.json", "1_Pooling/config.json",
]
_load_lock = Lock()


class EncoderUnavailable(RuntimeError):
    pass


class Encoder(Protocol):
    model: str
    dimensions: int

    def passages(self, values: list[str]) -> list[list[float]]: ...
    def query(self, value: str) -> list[float]: ...


def checked_vectors(values: list[list[float]], count: int, dimensions: int) -> list[list[float]]:
    if len(values) != count or any(len(value) != dimensions
                                   or not all(isfinite(item) for item in value)
                                   or not any(value) for value in values):
        raise EncoderUnavailable("Энкодер вернул неверное количество или размерность векторов")
    return values


class LocalE5:
    model = INDEX_MODEL
    dimensions = DIMENSIONS

    def __init__(self):
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(
                MODEL_ID,
                revision=MODEL_REVISION,
                device="cpu",
                local_files_only=True,
                trust_remote_code=False,
            )
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            raise EncoderUnavailable("Локальная модель E5 недоступна") from exc
        self._model.max_seq_length = WINDOW

    def _encode(self, values: list[str], prefix: str) -> list[list[float]]:
        if not values:
            return []
        inputs = [prefix + value for value in values]
        try:
            tokens = self._model.tokenizer(inputs, add_special_tokens=True,
                                           truncation=False, verbose=False)["input_ids"]
            if any(len(item) > WINDOW for item in tokens):
                raise EncoderUnavailable("Текст превышает окно локальной модели E5")
            result = self._model.encode(inputs, normalize_embeddings=True,
                                        batch_size=16, show_progress_bar=False).tolist()
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            raise EncoderUnavailable("Не удалось вычислить векторы E5") from exc
        return checked_vectors(result, len(values), self.dimensions)

    def passages(self, values: list[str]) -> list[list[float]]:
        return self._encode(values, "passage: ")

    def query(self, value: str) -> list[float]:
        return self._encode([value], "query: ")[0]


@lru_cache(maxsize=1)
def _cached_encoder() -> LocalE5:
    return LocalE5()


def get_local_encoder() -> LocalE5:
    # functools сохраняет значение, но допускает параллельное вычисление при cache miss.
    with _load_lock:
        return _cached_encoder()
