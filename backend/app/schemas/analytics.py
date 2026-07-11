from pydantic import BaseModel
from typing import Optional, List


class TopQuestion(BaseModel):
    question_text: str
    count: int


class VisitorStats(BaseModel):
    visitors_today: int
    total_conversations: int
    avg_messages_per_conversation: float
    languages: dict


class LeadStats(BaseModel):
    new_leads: int
    contacted_leads: int
    converted_leads: int
    popular_programs: dict
    grade_interest: dict


class DashboardResponse(BaseModel):
    top_questions: List[TopQuestion]
    visitor_stats: VisitorStats
    lead_stats: LeadStats
    unanswered_count: int
    answer_success_rate: float
