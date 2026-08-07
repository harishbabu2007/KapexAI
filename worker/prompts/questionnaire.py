from langchain_core.prompts import ChatPromptTemplate

MAX_QUESTIONS = 5

PLAN_QUESTIONNAIRE_PROMPT = """\
You are a business consultant interviewing an entrepreneur who just shared their business idea.

Business idea: {idea}

First, extract every concrete detail already stated in the idea (target location, customer segment, product, scale, funding, etc.) into the "facts" object. Take as much as you can from the prompt.

Then, generate up to {max_questions} deep, specific questions to fill the most important remaining gaps for writing a strong business report: market and competitors, target customer, pricing and revenue model, differentiation, capital and costs, operations, regulations.

Rules:
- Between 1 and {max_questions} questions, no more. Fewer is better if the idea is already detailed.
- Questions must be concrete and build on the idea, not generic yes/no questions.
- Do NOT ask about anything already covered by the extracted facts.

Return ONLY valid JSON with this exact shape, nothing else:
{{"facts": {{"business_about": "<full idea text>", "business_location": "<if stated else empty string>", "business_vision": "<if stated else empty string>", "target_customers": "<if stated else empty string>"}},
 "questions": [{{"key": "q1", "question": "..."}}, {{"key": "q2", "question": "..."}}]}}

Make sure the JSON is valid and complete."""

PLAN_QUESTIONNAIRE_TEMPLATE = ChatPromptTemplate.from_messages(
    [("human", PLAN_QUESTIONNAIRE_PROMPT)]
)

PARSE_ANSWERS_PROMPT = """\
You are processing an entrepreneur's free-form answers to a questionnaire about their business.

Questions:
{questions}

The entrepreneur replied with the following text (may be numbered, separated by newlines, or one big paragraph):

{answers}

Return ONLY valid JSON: an array of strings aligned 1:1 with the questions above (same order and count). Use an empty string for any question that was not answered.

Example: ["answer 1", "answer 2"]"""

PARSE_ANSWERS_TEMPLATE = ChatPromptTemplate.from_messages(
    [("human", PARSE_ANSWERS_PROMPT)]
)

VALIDATE_ANSWERS_PROMPT = """\
You are validating an entrepreneur's reply to a business questionnaire to keep the interview on track.

Questions:
{questions}

The entrepreneur replied with:
{answers}

Decide whether the reply is a genuine attempt to answer the questions with business-related content.

Mark it INVALID if it is:
- gibberish, random characters, or filler (e.g. "asdf", "bla bla", lorem ipsum, repeated keystrokes)
- completely off-topic or unrelated to the questions
- a refusal to answer, or an attempt to change the subject or derail the questionnaire

Mark it VALID if it answers at least one question meaningfully, even if partial or incomplete.

Return ONLY valid JSON, nothing else:
{{"valid": true|false, "reason": "<short explanation>"}}"""

VALIDATE_ANSWERS_TEMPLATE = ChatPromptTemplate.from_messages(
    [("human", VALIDATE_ANSWERS_PROMPT)]
)

IS_IDEA_PROMPT = """\
You determine whether an entrepreneur's message contains an actual business idea worth a business questionnaire.

Message:
{idea}

Mark real_idea as true when the message describes a business, product, service, or a business question/help request with meaningful content (e.g. "I want to open a coffee shop in Pune", "an app that helps people meal-plan", "help me with pricing for my bakery").

Mark real_idea as false when the message is just a command to start the questionnaire (e.g. "start the business questionnaire", "begin the questionnaire", "questionnaire"), a greeting, small talk, gibberish, or empty.

Return ONLY valid JSON, nothing else:
{{"real_idea": true|false}}"""

IS_IDEA_TEMPLATE = ChatPromptTemplate.from_messages(
    [("human", IS_IDEA_PROMPT)]
)
