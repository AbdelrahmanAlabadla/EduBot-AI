from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import auth, schools, users, documents, chatbot, analytics, admissions, leads

app = FastAPI(
    title="EduBot AI",
    description="Backend API for EduBot AI — SaaS platform for schools and universities",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(schools.router)
app.include_router(users.router)
app.include_router(documents.router)
app.include_router(chatbot.router)
app.include_router(analytics.router)
app.include_router(admissions.router)
app.include_router(leads.router)


@app.get("/")
def root():
    return {"message": "EduBot AI API is running"}
