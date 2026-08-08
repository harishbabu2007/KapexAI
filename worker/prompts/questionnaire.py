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
- an explicit refusal to engage with the questionnaire (e.g. "I don't want to answer", "stop asking me")

Mark it VALID if it answers at least one question on-topic, even if partial or incomplete.

IMPORTANT: an honest answer that the entrepreneur is unsure or hasn't decided yet — such as "not sure", "I don't know", "haven't decided", "no clue yet", "need to figure it out" — is a VALID answer for that question. It reflects real business uncertainty and must NOT be rejected or re-asked.

Return ONLY valid JSON, nothing else:
{{"valid": true|false, "reason": "<short explanation>"}}"""

VALIDATE_ANSWERS_TEMPLATE = ChatPromptTemplate.from_messages(
    [("human", VALIDATE_ANSWERS_PROMPT)]
)

VALIDATE_STRUCTURED_ANSWER_PROMPT = """\
You check whether an entrepreneur's typed answer genuinely responds to its questionnaire question. You only reject clear garbage.

Question:
{question}

The entrepreneur's answer:
{answer}

Mark valid=false ONLY when the answer is:
- gibberish, random keystrokes, or filler (e.g. "asdf", "hehe", "lol", "bruh", "loool", repeated keystrokes, lorem ipsum)
- completely off-topic or unrelated to the question
- an explicit refusal to engage (e.g. "I don't want to answer", "stop asking")

In every other case mark valid=true. In particular:
- A short or partial answer is valid if it is on-topic, even if it only addresses part of a compound question.
- "not sure", "I don't know", "haven't decided", "idk", "no idea" are VALID answers.
- Spelling mistakes, casual or informal wording, and incomplete sentences are VALID.

Return ONLY valid JSON, nothing else:
{{"valid": true|false}}"""

VALIDATE_STRUCTURED_ANSWER_TEMPLATE = ChatPromptTemplate.from_messages(
    [("human", VALIDATE_STRUCTURED_ANSWER_PROMPT)]
)

CLARIFY_REQUEST_PROMPT = """\
You keep a business questionnaire interview on track by deciding whether an entrepreneur's message is a clarifying question about the questionnaire itself, rather than an attempt to answer it.

Questions:
{questions}

The entrepreneur wrote the following message while the questionnaire is still pending:
{message}

Mark clarification=true when the message contains a question ABOUT the questionnaire or its questions — for example asking to rephrase something in simpler words, what a term means, why a question is being asked, how to answer, or an example. This is still true when the user ALSO tried to answer some of the questions in the same message — a clarification request mixed with partial answers is still a clarification request, and the partial answers should not be silently rejected.

Mark clarification=false when the message is purely an attempt to answer the questions (even partially, informally, or with "not sure"/"I don't know"), or is gibberish/nonsense with no question about the questionnaire.

Return ONLY valid JSON, nothing else:
{{"clarification": true|false}}"""

CLARIFY_REQUEST_TEMPLATE = ChatPromptTemplate.from_messages(
    [("human", CLARIFY_REQUEST_PROMPT)]
)

EXPLAIN_QUESTIONS_PROMPT = """\
You are a business consultant helping an entrepreneur understand the questionnaire you just asked them. The entrepreneur is confused and asked:

{user_message}

Business idea:
{idea}

Questions:
{questions}

Rephrase each question in simple, plain, friendly words that an everyday person can understand, and briefly say why it matters for their business. If the entrepreneur asked about a specific question (e.g. by number or topic), focus your explanation on that one. Keep it short, warm, and encouraging, using markdown bullets. End with a one-line prompt inviting them to answer. Never give up on the questionnaire — you are only clarifying, the interview continues after this."""

EXPLAIN_QUESTIONS_TEMPLATE = ChatPromptTemplate.from_messages(
    [("human", EXPLAIN_QUESTIONS_PROMPT)]
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
