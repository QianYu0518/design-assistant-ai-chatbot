import os
import logging
import uvicorn
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from dotenv import load_dotenv
from cv_analysis import perform_cv_audit
from typing import Optional
import rules
from database import db_helper
import time
import random

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY not found in .env file.")

app = FastAPI(title="AI UI Auditor", version="1.0.0")

app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_methods=["*"],
    allow_headers=["*"]
)

client = genai.Client(api_key=API_KEY)

def classify_ui(cv):
    whitespace = cv.get("whitespace_ratio", 0)
    small_elements = cv.get("small_elements_found", 0)
    contrast = cv.get("contrast_issues_found", 0)

    # Heuristic scoring
    score = 100

    # Penalties
    if whitespace < 15:
        score -= 20
    elif whitespace > 80:
        score -= 10

    if small_elements > 50:
        score -= 25
    elif small_elements > 20:
        score -= 10

    if contrast > 10:
        score -= 25
    elif contrast > 5:
        score -= 10

    # Convert score into category
    if score >= 80:
        return "GOOD", score
    elif score >= 50:
        return "AVERAGE", score
    else:
        return "POOR", score
    
def send_message_with_retry(chat, content, max_retries=4):
    for attempt in range(max_retries):
        try:
            return chat.send_message(content)

        except Exception as e:
            error_text = str(e)

            # Retry only for temporary Gemini outages
            if "503" not in error_text and "UNAVAILABLE" not in error_text:
                raise

            if attempt == max_retries - 1:
                raise

            wait_time = (2 ** attempt) + random.uniform(0, 1)

            logger.warning(
                f"Gemini unavailable. Retry {attempt + 1}/{max_retries} "
                f"after {wait_time:.2f}s"
            )

            time.sleep(wait_time)

# --- Security Guardrail Definition ---
SYSTEM_INSTRUCTION = f"""
You are a Senior UX/UI and Accessibility Auditor. 

PERSONALITY:
- Professional, insightful, and slightly witty.
- Use emojis sparingly to keep it modern.
- DO NOT start every response with a greeting. Only greet the user if they greet you first.

STRICT DESIGN FOCUS:
- Your core job is to analyze UI based on WCAG and Nielsen Heuristics.
- If a user asks something totally unrelated (sports, recipes, etc.), politely decline:
  "I'm specialized in UX/UI auditing. I can't help with that, but I'd love to audit a screenshot or answer a design question!"
- Always reference heuristics by their short name in parentheses, e.g., (Visibility) or (Aesthetic).

TECHNICAL KNOWLEDGE BASE (Use these for your audits):
- Target Size: {rules.MIN_TOUCH_TARGET_AA}px (AA) or {rules.MIN_TOUCH_TARGET_AAA}px (AAA).
- Contrast: {rules.MIN_LARGE_TEXT_CONTRAST}:1 for normal text.
- Heuristics to use: {rules.HEURISTICS}
"""

def build_audit_prompt(cv_data, ui_quality, ui_score, user_query=None):
    # 1. Get the strict rules from rules.py
    audit_rules = rules.get_rules_string()
    
    # 2. Build the factual data string from OpenCV
    analysis_data = f"""
    IMAGE ANALYSIS DATA (FACTS):

    - UI Quality Level: {ui_quality}
    - UI Score: {ui_score}/100

    - Whitespace Ratio: {cv_data.get('whitespace_ratio', 0)}%
    - Small Interactive Elements: {cv_data.get('small_elements_found', 0)}
    - Contrast Issues: {cv_data.get('contrast_issues_found', 0)}
    """

    # 3. Create the Base Prompt
    base_prompt = f"""
    SYSTEM ROLE: You are an expert Technical UI Auditor.
    
    {audit_rules}

    {analysis_data}

    TASK:
    You are a professional UI/UX auditor.

    First, consider the UI QUALITY LEVEL:

    - If GOOD → emphasize strengths, only minor suggestions.
    - If AVERAGE → balanced feedback.
    - If POOR → highlight real usability issues.

    IMPORTANT RULE:
    Do NOT force problems. If UI is good, you may return fewer than 3 issues or even state "No major usability issues detected".
    """

    # 4. Handle the User Query
    if user_query:
        base_prompt += f"\nUSER CONTEXT/QUESTION: {user_query}\nINSTRUCTION: Address the user's question specifically while following the output constraints below."

    # 5. Final Output Constraint
    constraint = """
    \nOUTPUT FORMAT (STRICT - MUST FOLLOW EXACTLY): 
    You must output up to 3 findings only.

    Each finding MUST follow this exact format:

    ### Point X: Title

    **Finding**:
    <text>

    **Severity**:
    <Critical | Major | Minor>

    **Practical Fix**:
    <text>

    ---

    Rules:
    - If UI is GOOD, you may output 0–2 findings.
    - If UI is AVERAGE, output 2–3 findings.
    - If UI is POOR, output up to 3 findings.
    - You may include strengths if relevant.
    - "Finding:", "Severity:", and "Practical Fix:" MUST be on separate lines.
    - Do NOT combine fields on the same line.
    - Do NOT use inline formatting like "Severity: Minor Practical Fix:".
    - Always add a line break after each label.
    - Always separate sections using "---".
    - Maximum 3 findings only.

    """
    
    return base_prompt + constraint

@app.post("/analyze/ui-screenshot")
async def analyze_ui_screenshot(
    file: Optional[UploadFile] = File(None),
    query: Optional[str] = Form(None),
    history: Optional[str] = Form(None)
):
    total_timer_start = time.time()
    
    is_file_provided = file is not None and file.filename != ""
    is_query_provided = query is not None and query.strip() != ""

    if not is_file_provided and not is_query_provided:
        raise HTTPException(status_code=400, detail="Please provide a question or an image.")

    try:
        # Configuration for the model to use the System Instruction properly
        model_id = 'gemini-2.5-flash'
        config = {"system_instruction": SYSTEM_INSTRUCTION}

        # Parse Hstory
        import json
        past_messages = json.loads(history) if history else []

        # Initialize the Chat Session with history
        chat = client.chats.create(
            model=model_id,
            config=config,
            history=past_messages
        )

        # CASE 1: TEXT ONLY
        if not is_file_provided:

            ai_timer_start = time.time()

            response = send_message_with_retry(chat, query)

            ai_timer_end = time.time()

            logger.info(f"AI Response Time: {ai_timer_end - ai_timer_start:.6f}s")

            return {"status": "success", "opencv_data": None, "gemini_response": response.text}

        # CASE 2: IMAGE (+ Optional Text)

        upload_tiemr_start = time.perf_counter()

        image_data = await file.read()

        upload_tiemr_end = time.perf_counter()

        upload_time_ms = (upload_tiemr_end - upload_tiemr_start) * 1000

        if len(image_data) == 0:
            raise ValueError("The uploaded file is empty.")
        
        # Run the Computer Vision Audit
        opencv_timer_start = time.time()

        cv_results, optimized_image = perform_cv_audit(image_data)

        logger.info(
            f"Optimized image size: "
            f"{len(optimized_image)/1024:.1f} KB"
        )

        opencv_timer_end = time.time()

        opencv_time = opencv_timer_end - opencv_timer_start
        
        # UI classification (IMPORTANT)
        ui_quality, ui_score = classify_ui(cv_results)
        
        # Prepare the image part for Gemini
        image_part = genai.types.Part.from_bytes(data = optimized_image, mime_type = "image/jpeg")

        # Build the dynamic prompt using the CV data
        audit_prompt = build_audit_prompt(cv_results,ui_quality,ui_score,query)

        ai_timer_start = time.time()
        
        response = send_message_with_retry(
            chat,
            [image_part, audit_prompt]
        )

        ai_timer_end = time.time()

        ai_time = ai_timer_end - ai_timer_start

        db_timer_start = time.time()

        await db_helper.save_audit(
            filename=file.filename if is_file_provided else "text_query",
            query=query or "N/A",
            metrics=cv_results if is_file_provided else {"note": "text-only query"},
            report=response.text
        )

        db_timer_end = time.time()

        db_time = db_timer_end - db_timer_start

        total_timer_end = time.time() 
        
        total_time = total_timer_end - total_timer_start

        # Log Result
        logger.info(f"Upload Time: {upload_time_ms:.3f}s")
        logger.info(f"OpenCV Time: {opencv_time:.2f}s")
        logger.info(f"AI Time: {ai_time:.2f}s")
        logger.info(f"Database Time: {db_time:.2f}s")
        logger.info(f"Total Time: {total_time:.2f}s")

        return {
            "status": "success",
            "opencv_data": cv_results,
            "gemini_response": response.text,
        }
        
    except Exception as e:
        logger.error(f"Analysis Error: {str(e)}")

        error_text = str(e)

        if "503" in error_text or "UNAVAILABLE" in error_text:
            raise HTTPException(
                status_code=503,
                detail="Gemini temporarily unavailable. Please try again."
            )

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
