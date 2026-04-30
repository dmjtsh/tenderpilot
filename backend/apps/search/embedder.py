"""
Singleton-обёртка над fastembed для генерации векторов.

multilingual-e5-large требует префиксы:
  "query: <text>"   — для поисковых запросов
  "passage: <text>" — для индексируемых документов
"""
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastembed import TextEmbedding
    from apps.tenders.models import Tender

logger = logging.getLogger(__name__)

MODEL_NAME = "intfloat/multilingual-e5-large"
EMBEDDING_DIM = 1024


class Embedder:
    _instance: "Embedder | None" = None
    _model: "TextEmbedding | None" = None

    def __new__(cls) -> "Embedder":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _get_model(self) -> "TextEmbedding":
        if self._model is None:
            from fastembed import TextEmbedding  # lazy import — тяжёлая зависимость
            logger.info("Loading embedding model %s...", MODEL_NAME)
            self._model = TextEmbedding(model_name=MODEL_NAME)
            logger.info("Embedding model loaded.")
        return self._model

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        """Векторизация документов для индексации."""
        prefixed = [f"passage: {t}" for t in texts]
        model = self._get_model()
        return [v.tolist() for v in model.embed(prefixed)]

    def embed_query(self, text: str) -> list[float]:
        """Векторизация поискового запроса."""
        model = self._get_model()
        result = list(model.embed([f"query: {text}"]))
        return result[0].tolist()


embedder = Embedder()


def tender_text(tender: "Tender") -> str:
    from apps.tenders.okved import okved_to_text

    okpd_names = okved_to_text(tender.okpd_codes or [])
    ai_summary = (tender.ai_summary or "")[:500]

    parts = [
        tender.title + ".",
        ai_summary,
        f"Вид работ: {okpd_names}." if okpd_names else "",
        f"Заказчик: {tender.customer.name}." if tender.customer_id else "",
        f"Регион: {tender.region}." if tender.region else "",
        f"Закон: {tender.law_type}." if tender.law_type else "",
    ]
    return " ".join(p for p in parts if p)
