import math
from typing import Any, List, Union, Optional
from dataclasses import dataclass
from sqlalchemy.orm import Query


@dataclass
class PageResult:
    items: List[Any]
    total_records: int
    current_page: int
    total_pages: int
    page_size: int
    start_record: int
    end_record: int
    has_prev: bool
    has_next: bool
    prev_page: int
    next_page: int
    page_numbers: List[Union[int, str]]


def generate_page_numbers(current_page: int, total_pages: int, delta: int = 2) -> List[Union[int, str]]:
    """
    Generate responsive windowed page numbers with ellipsis.
    Example: [1, 2, 3, 4, 5] or [1, '...', 4, 5, 6, '...', 20]
    """
    if total_pages <= 7:
        return list(range(1, total_pages + 1))

    pages: List[Union[int, str]] = []
    left = max(2, current_page - delta)
    right = min(total_pages - 1, current_page + delta)

    pages.append(1)

    if left > 2:
        pages.append("...")

    for p in range(left, right + 1):
        pages.append(p)

    if right < total_pages - 1:
        pages.append("...")

    pages.append(total_pages)
    return pages


def paginate_query(
    query: Query,
    page: Optional[Union[int, str]] = 1,
    page_size: Optional[Union[int, str]] = 25,
    max_page_size: int = 100
) -> PageResult:
    """
    Paginate a SQLAlchemy Query efficiently using SQL LIMIT and OFFSET.
    """
    try:
        page_int = max(1, int(page)) if page is not None else 1
    except (ValueError, TypeError):
        page_int = 1

    try:
        size_int = max(1, min(int(page_size), max_page_size)) if page_size is not None else 25
    except (ValueError, TypeError):
        size_int = 25

    total_records = query.count()
    total_pages = max(1, math.ceil(total_records / size_int))
    current_page = min(page_int, total_pages)

    offset = (current_page - 1) * size_int
    items = query.offset(offset).limit(size_int).all()

    start_record = (offset + 1) if total_records > 0 else 0
    end_record = min(offset + size_int, total_records)

    return PageResult(
        items=items,
        total_records=total_records,
        current_page=current_page,
        total_pages=total_pages,
        page_size=size_int,
        start_record=start_record,
        end_record=end_record,
        has_prev=current_page > 1,
        has_next=current_page < total_pages,
        prev_page=max(1, current_page - 1),
        next_page=min(total_pages, current_page + 1),
        page_numbers=generate_page_numbers(current_page, total_pages)
    )


def paginate_list(
    items_list: List[Any],
    page: Optional[Union[int, str]] = 1,
    page_size: Optional[Union[int, str]] = 25,
    max_page_size: int = 100
) -> PageResult:
    """
    Paginate an in-memory list (e.g., grouped sessions/aggregations) while returning identical PageResult metadata.
    """
    try:
        page_int = max(1, int(page)) if page is not None else 1
    except (ValueError, TypeError):
        page_int = 1

    try:
        size_int = max(1, min(int(page_size), max_page_size)) if page_size is not None else 25
    except (ValueError, TypeError):
        size_int = 25

    total_records = len(items_list)
    total_pages = max(1, math.ceil(total_records / size_int))
    current_page = min(page_int, total_pages)

    offset = (current_page - 1) * size_int
    paged_items = items_list[offset:offset + size_int]

    start_record = (offset + 1) if total_records > 0 else 0
    end_record = min(offset + size_int, total_records)

    return PageResult(
        items=paged_items,
        total_records=total_records,
        current_page=current_page,
        total_pages=total_pages,
        page_size=size_int,
        start_record=start_record,
        end_record=end_record,
        has_prev=current_page > 1,
        has_next=current_page < total_pages,
        prev_page=max(1, current_page - 1),
        next_page=min(total_pages, current_page + 1),
        page_numbers=generate_page_numbers(current_page, total_pages)
    )
