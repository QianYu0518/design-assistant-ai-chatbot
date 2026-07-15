import cv2
import numpy as np
import rules

def get_luminance(color_bgr):
    # Calculates relative luminance. Safely handles various input types
    try:
        # Standardizing to floats for precise division
        b = float(color_bgr[0]) / 255.0
        g = float(color_bgr[1]) / 255.0
        r = float(color_bgr[2]) / 255.0
    except (IndexError, TypeError, ValueError):
        return 0 

    # WCAG Relative Luminance Formula: 0.2126*R + 0.7152*G + 0.0722*B
    standardized = []
    for c in [r, g, b]:
        if c <= 0.03928:
            standardized.append(c / 12.92)
        else:
            standardized.append(((c + 0.055) / 1.055) ** 2.4)
            
    return 0.2126 * standardized[0] + 0.7152 * standardized[1] + 0.0722 * standardized[2]


def calculate_contrast(color1, color2):
    # Calculates the contrast ratio between foreground and background
    l1 = get_luminance(color1)
    l2 = get_luminance(color2)
    return round((max(l1, l2) + 0.05) / (min(l1, l2) + 0.05), 2)

def calculate_whitespace_ratio(img_gray):
    # Canny edge detection helps identify "busy" vs "empty" areas
    edges = cv2.Canny(img_gray, 50, 150)
    kernel = np.ones((5,5), np.uint8)
    busy_areas = cv2.dilate(edges, kernel, iterations=2)
    empty_pixels = cv2.countNonZero(cv2.bitwise_not(busy_areas))
    return round((empty_pixels / (img_gray.shape[0] * img_gray.shape[1])) * 100, 2)

def perform_cv_audit(image_bytes):
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None: return {"error": "Invalid image"}, image_bytes

    h, w = img.shape[:2]

    scale = 1.0 

    if w > 1024:
        scale = 1024 / w
        img = cv2.resize(img, (1024, int(h * scale)))
    
    # Visual Debugging: Create a copy to draw on
    debug_img = img.copy()
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Detection logic
    corners = [img[0,0], img[0,-1], img[-1,0], img[-1,-1]]
    bg_color = np.mean(corners, axis=0) 

    thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                   cv2.THRESH_BINARY_INV, 11, 2)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    small_elements = 0
    contrast_issues = 0
    sampled_ratios = []

    for cnt in contours:
        x, y, w_box, h_box = cv2.boundingRect(cnt)
        area = cv2.contourArea(cnt)
        
        # Ignore "Noise" (tiny dots) but keep "Small Targets"
        if area < 150: continue 

        # 1. Touch Target Check (WCAG 2.5.5)
        actual_w = w_box / scale
        actual_h = h_box / scale

        if actual_w < rules.MIN_TOUCH_TARGET_AA or actual_h < rules.MIN_TOUCH_TARGET_AA:
            small_elements += 1
            # Draw a YELLOW box around small targets
            cv2.rectangle(debug_img, (x, y), (x + w_box, y + h_box), (0, 255, 255), 1)
        
        # 2. Contrast Check (WCAG 1.4.3)
        if w_box > 15 and h_box > 15:
            roi = img[y:y+h_box, x:x+w_box]
            avg_color = cv2.mean(roi)[:3]
            ratio = calculate_contrast(avg_color, bg_color)
            sampled_ratios.append(ratio)
            
            if ratio < rules.MIN_TEXT_CONTRAST:
                contrast_issues += 1
                # Draw a RED box around contrast failures
                cv2.rectangle(debug_img, (x, y), (x + w_box, y + h_box), (0, 0, 255), 2)
            
    whitespace = calculate_whitespace_ratio(gray)
    avg_contrast = round(sum(sampled_ratios)/len(sampled_ratios), 1) if sampled_ratios else "N/A"
    
    # Encode the DEBUG image so Gemini can see the boxes
    _, compressed = cv2.imencode('.jpg', debug_img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    
    return {
        "whitespace_ratio": whitespace,
        "is_cluttered": whitespace < 15,
        "small_elements_found": small_elements,
        "contrast_issues_found": contrast_issues,
        "average_contrast_ratio": avg_contrast,
    }, compressed.tobytes()