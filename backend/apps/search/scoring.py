def score_label(cosine: float) -> str:
    score = round(cosine * 100)
    if score >= 85:
        return "Отличное совпадение"
    if score >= 70:
        return "Хорошее совпадение"
    if score >= 55:
        return "Среднее совпадение"
    return "Слабое совпадение"
