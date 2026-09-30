from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

@dataclass
class Task:
    id: int
    student_name: str
    category: str          # deadline_move / urgent / restore / meeting / other
    description: str
    due_date: date
    is_done: bool
    created_at: datetime
    notes: Optional[str] = None