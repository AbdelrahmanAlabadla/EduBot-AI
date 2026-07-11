from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database.connection import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.models.analytics_event import AnalyticsEvent
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.lead import Lead
from app.schemas.analytics import DashboardResponse, TopQuestion, VisitorStats, LeadStats

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    school_id = current_user.school_id
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    top_qs = (
        db.query(AnalyticsEvent.question_text, func.count(AnalyticsEvent.id).label("count"))
        .filter(
            AnalyticsEvent.school_id == school_id,
            AnalyticsEvent.event_type == "question_asked",
            AnalyticsEvent.question_text.isnot(None),
        )
        .group_by(AnalyticsEvent.question_text)
        .order_by(func.count(AnalyticsEvent.id).desc())
        .limit(10)
        .all()
    )
    top_questions = [TopQuestion(question_text=q, count=c) for q, c in top_qs if q]

    unanswered = (
        db.query(func.count(AnalyticsEvent.id))
        .filter(
            AnalyticsEvent.school_id == school_id,
            AnalyticsEvent.event_type == "failed_answer",
        )
        .scalar()
        or 0
    )
    total_asked = (
        db.query(func.count(AnalyticsEvent.id))
        .filter(
            AnalyticsEvent.school_id == school_id,
            AnalyticsEvent.event_type == "question_asked",
        )
        .scalar()
        or 0
    )
    success_rate = ((total_asked - unanswered) / total_asked * 100) if total_asked > 0 else 100.0

    visitors_today = (
        db.query(func.count(func.distinct(Conversation.visitor_id)))
        .filter(
            Conversation.school_id == school_id,
            Conversation.created_at >= today_start,
        )
        .scalar()
        or 0
    )
    total_convs = (
        db.query(func.count(Conversation.id))
        .filter(Conversation.school_id == school_id)
        .scalar()
        or 0
    )
    total_msgs = (
        db.query(func.count(Message.id))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .filter(Conversation.school_id == school_id)
        .scalar()
        or 0
    )
    avg_msgs = round(total_msgs / total_convs, 1) if total_convs > 0 else 0.0

    lang_rows = (
        db.query(Conversation.language, func.count(Conversation.id))
        .filter(Conversation.school_id == school_id)
        .group_by(Conversation.language)
        .all()
    )
    languages = {lang or "unknown": count for lang, count in lang_rows}

    new_leads = (
        db.query(func.count(Lead.id))
        .filter(Lead.school_id == school_id, Lead.status == "new")
        .scalar()
        or 0
    )
    contacted_leads = (
        db.query(func.count(Lead.id))
        .filter(Lead.school_id == school_id, Lead.status == "contacted")
        .scalar()
        or 0
    )
    converted_leads = (
        db.query(func.count(Lead.id))
        .filter(Lead.school_id == school_id, Lead.status == "converted")
        .scalar()
        or 0
    )

    prog_rows = (
        db.query(Lead.interested_program, func.count(Lead.id))
        .filter(Lead.school_id == school_id, Lead.interested_program.isnot(None))
        .group_by(Lead.interested_program)
        .order_by(func.count(Lead.id).desc())
        .limit(5)
        .all()
    )
    popular_programs = {p or "Unknown": c for p, c in prog_rows}

    grade_rows = (
        db.query(Lead.student_grade, func.count(Lead.id))
        .filter(Lead.school_id == school_id, Lead.student_grade.isnot(None))
        .group_by(Lead.student_grade)
        .order_by(func.count(Lead.id).desc())
        .limit(5)
        .all()
    )
    grade_interest = {g or "Unknown": c for g, c in grade_rows}

    return DashboardResponse(
        top_questions=top_questions,
        visitor_stats=VisitorStats(
            visitors_today=visitors_today,
            total_conversations=total_convs,
            avg_messages_per_conversation=avg_msgs,
            languages=languages,
        ),
        lead_stats=LeadStats(
            new_leads=new_leads,
            contacted_leads=contacted_leads,
            converted_leads=converted_leads,
            popular_programs=popular_programs,
            grade_interest=grade_interest,
        ),
        unanswered_count=unanswered,
        answer_success_rate=round(success_rate, 1),
    )
