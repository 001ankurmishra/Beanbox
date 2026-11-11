from app.models.domain import CamelModel


class PaginationMeta(CamelModel):
    page: int
    limit: int
    total_items: int
    total_pages: int
    has_next: bool
    has_prev: bool
