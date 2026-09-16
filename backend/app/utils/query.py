from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

LIKE_ESCAPE = "\\"


def contains_pattern(term: str) -> str:
    """ILIKE pattern matching `term` literally (so '%' and '_' in user input aren't wildcards)."""
    escaped = term.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2).replace("%", r"\%").replace("_", r"\_")
    return f"%{escaped}%"


def count_rows(db: Session, query: Select) -> int:
    return db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0


def summarize(text: str, limit: int = 160) -> str:
    """Shorten to at most `limit` characters, breaking at a word boundary."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0]
    return f"{cut}…"
