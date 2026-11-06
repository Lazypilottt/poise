"""Question bank and selection logic for practice sessions."""

from __future__ import annotations

import random

ROLE_CHOICES = [
    ("software", "Software Engineering"),
    ("data", "Data Science / Analytics"),
    ("product", "Product Management"),
    ("design", "UI/UX Design"),
    ("general", "General / Other"),
]

LEVEL_CHOICES = [
    ("student", "Student / Fresher"),
    ("junior", "1-3 years experience"),
    ("senior", "3+ years experience"),
]

OPENERS = [
    "Tell me about yourself.",
    "Walk me through your resume.",
    "Why are you interested in this role?",
    "What motivates you in your work?",
]

BEHAVIOURAL = [
    "Describe a time you disagreed with a teammate. How did you resolve it?",
    "Tell me about a mistake you made and what you learned from it.",
    "Describe a situation where you had to meet a tight deadline.",
    "Tell me about a time you took ownership of a problem nobody else was solving.",
    "Describe a time you received critical feedback. What did you do with it?",
    "Tell me about a time you had to learn something new very quickly.",
]

ROLE_QUESTIONS = {
    "software": [
        "Explain a technical project you're proud of and the hardest bug you hit while building it.",
        "How would you design a URL shortener that handles millions of requests a day?",
        "How do you decide when code is ready to ship?",
        "Explain the difference between a process and a thread to a non-technical person.",
        "How do you approach reviewing someone else's code?",
    ],
    "data": [
        "Walk me through a data analysis project from raw data to insight.",
        "How would you explain overfitting to a business stakeholder?",
        "A key metric dropped 20% overnight. How would you investigate?",
        "How do you decide which model to use for a new prediction problem?",
        "Tell me about a time your analysis changed a decision.",
    ],
    "product": [
        "How would you prioritise features with limited engineering time?",
        "Pick a product you use daily. What would you improve and why?",
        "How do you measure whether a feature launch was successful?",
        "Tell me about a time you said no to a stakeholder request.",
        "How would you validate a new product idea before building it?",
    ],
    "design": [
        "Walk me through your design process on a recent project.",
        "How do you handle feedback that conflicts with user research?",
        "How do you make an interface accessible?",
        "Tell me about a design decision you made based on data.",
        "How do you balance user needs with business goals?",
    ],
    "general": [
        "What are your greatest strengths, and how have you used them?",
        "Where do you see yourself in five years?",
        "How do you organise your work when you have several priorities?",
        "What do you know about our company, and why do you want to join?",
        "Tell me about an achievement you're proud of.",
    ],
}

LEVEL_QUESTIONS = {
    "student": "Which course or college project best prepared you for this role, and why?",
    "junior": "What is the most important thing you learned in your first job?",
    "senior": "Tell me about a time you mentored someone or led a team through a difficult project.",
}

SKILL_TEMPLATE = "Tell me about a project where you used {skill}. What would you do differently now?"

CLOSER = "Do you have any questions for us?"


def parse_skills(raw: str) -> list[str]:
    return [s.strip() for s in raw.replace("\n", ",").split(",") if s.strip()][:10]


def select_questions(
    role: str,
    level: str,
    skills: list[str] | None = None,
    count: int = 5,
    seed: int | None = None,
) -> list[str]:
    """Build a balanced question set: opener, role-specific, skill/level, behavioural, closer."""
    rng = random.Random(seed)
    role_pool = ROLE_QUESTIONS.get(role, ROLE_QUESTIONS["general"])

    questions = [rng.choice(OPENERS)]
    personalised = [SKILL_TEMPLATE.format(skill=rng.choice(skills))] if skills else []
    personalised.append(LEVEL_QUESTIONS.get(level, LEVEL_QUESTIONS["student"]))

    middle = rng.sample(role_pool, k=min(2, len(role_pool)))
    middle.append(personalised[0])
    middle.append(rng.choice(BEHAVIOURAL))
    middle.extend(rng.sample(role_pool, k=len(role_pool)))  # fallbacks if count is large

    for q in middle:
        if len(questions) >= count - 1:
            break
        if q not in questions:
            questions.append(q)

    if count > 1:
        questions.append(CLOSER if count >= 5 else rng.choice(BEHAVIOURAL))
    return questions[:count]
