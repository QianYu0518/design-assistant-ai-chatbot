# Knowledge Base

# --- 1. ACCESSIBILITY (WCAG 2.2) ---
# Perceivable: Contrast
MIN_TEXT_CONTRAST = 4.5
MIN_LARGE_TEXT_CONTRAST = 3.0
MIN_UI_COMPONENT_CONTRAST = 3.0

# Operable: Touch Targets
MIN_TOUCH_TARGET_AA = 24  # CSS Pixels
MIN_TOUCH_TARGET_AAA = 44

# --- 2. USABILITY HEURISTICS (Nielsen) ---
HEURISTICS = {
    "Visibility": "Visibility of System Status: Show loading states or progress.",
    "Match": "Match system to real world: Use natural language, avoid jargon.",
    "Control": "User control: Provide 'Undo', 'Cancel', or 'Back' options.",
    "Consistency": "Consistency and standards: Buttons/UI must look uniform.",
    "Error Prevention": "Prevent errors: Guard destructive actions (e.g. Delete).",
    "Recognition": "Recognition over recall: Use clear labels and icons.",
    "Flexibility": "Flexibility: Provide shortcuts/filters for power users.",
    "Aesthetic": "Aesthetic design: Avoid clutter/minimalist whitespace.",
    "Error Recovery": "Help users recover: Messages must be plain-text and helpful.",
    "Help": "Help: Search or help icons must be easily accessible."
}

# --- 3. SCORING & SEVERITY ---
WEIGHTS = {
    "CRITICAL": 25, # Blockers: Contrast failures, missing buttons
    "MAJOR": 15,    # Friction: Small targets, high clutter
    "MINOR": 5      # Polish: Spacing, font inconsistencies
}

# --- 4. AI PROMPT BRIDGE ---
def get_rules_string():
    """Converts Python constants into a string for the AI to read."""
    rules_text = f"""
    AUDIT THRESHOLDS:
    - Text Contrast: Min {MIN_TEXT_CONTRAST}:1 (Large text: {MIN_LARGE_TEXT_CONTRAST}:1)
    - UI Component Contrast: Min {MIN_UI_COMPONENT_CONTRAST}:1
    - Touch Target Size: Min {MIN_TOUCH_TARGET_AA}x{MIN_TOUCH_TARGET_AA}px
    - Max Mobile Width: 320px
    
    HEURISTIC DEFINITIONS:
    """
    for key, val in HEURISTICS.items():
        rules_text += f"- {key}: {val}\n"
    
    return rules_text