import re
import json
import sys
import pdfplumber
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

WEEKDAY_MAP = {
    "T2": 1, "T3": 2, "T4": 3, "T5": 4, "T6": 5, "T7": 6, "CN": 7,
    "Thứ 2": 1, "Thứ 3": 2, "Thứ 4": 3, "Thứ 5": 4, "Thứ 6": 5, "Thứ 7": 6, "Chủ nhật": 7
}

def cluster_lines(words, tol=3.0, xgap=8.0):
    lines = []
    for w in words:
        placed = False
        for line in lines:
            if abs(line["top"] - w["top"]) <= tol and w["x0"] - line["x1"] <= xgap:
                line["words"].append(w)
                line["top"] = min(line["top"], w["top"])
                line["x1"] = max(line["x1"], w["x1"])
                placed = True
                break
        if not placed:
            line = {"top": w["top"], "words": [w], "x1": w["x1"]}
            lines.append(line)
    for line in lines:
        line["words"].sort(key=lambda w: w["x0"])
        line["x0"] = min(w["x0"] for w in line["words"])
        parts = []
        prev = None
        for w in line["words"]:
            if prev is not None and w["x0"] - prev["x1"] > 0.5:
                parts.append(" ")
            parts.append(w["text"])
            prev = w
        line["text"] = "".join(parts)
        line["tokens"] = line["words"][:]
    lines.sort(key=lambda l: (l["top"], l["x0"]))
    return lines

def find_day_columns(lines):
    cols = {}
    for line in lines:
        words_sorted = line["words"]
        for i, w in enumerate(words_sorted):
            m = re.match(r"^(T[2-7]|CN),?$", w["text"].strip())
            if m and i + 1 < len(words_sorted) and re.fullmatch(r"\d{1,2}", words_sorted[i + 1]["text"].strip()):
                day_num = int(words_sorted[i + 1]["text"].strip())
                cols[m.group(1)] = {"x0": w["x0"], "day": day_num, "day_num": day_num}
    items = sorted(cols.items(), key=lambda kv: kv[1]["x0"])
    bounds = []
    for j, (name, info) in enumerate(items):
        left = info["x0"]
        right = (items[j + 1][1]["x0"] + info["x0"]) / 2.0 if j + 1 < len(items) else 1e9
        bounds.append((name, left, right, info["day"], info["day_num"]))
    return bounds

def column_for(x0, bounds):
    best = None
    best_d = 1e18
    for name, left, right, day, day_num in bounds:
        d = abs(x0 - left)
        if d < best_d:
            best_d = d
            best = (name, day, day_num)
    return best

def build_blocks(lines, bounds):
    groups = {}
    current_slot = None
    for line in lines:
        x0 = line["x0"]
        text = line["text"]
        if x0 < 170:
            m = re.match(r"^(\d{1,2}SA|\d{1,2}CH)$", text.strip())
            if m:
                current_slot = text.strip()
            continue
        if x0 >= 200 and current_slot is not None:
            if not re.search(r"[A-Za-z\u00c0-\u1ef9\u00e0-\u1ef3\u008a-\u00fd0-9]", text):
                continue
            if re.match(r"^\d{1,2}/\d{1,2}/\d{4}", text.strip()):
                continue
            if re.match(r"^\d/\d$", text.strip()):
                continue
            if "mydtu.duytan.edu.vn" in text:
                continue
            col_result = column_for(x0, bounds)
            if col_result is None:
                continue
            day, daynum, day_num = col_result
            if day is None:
                continue
            groups.setdefault(day, []).append((line, daynum, day_num))
    for lines_list in groups.values():
        lines_list.sort(key=lambda t: t[0]["top"])
    return groups

def parse_block(block_lines):
    parts = " ".join(l["text"] for l in block_lines)
    parts = re.sub(r"[^\x00-\x7F\u00e0-\u00ff\u0100-\u017f\u1ea0-\u1ef9\w\s\.\,\-\:/\|&]", "", parts)
    parts = re.sub(r"\s*\|\s*", "|", parts)
    parts = re.sub(r"delete\s*$", "", parts, flags=re.IGNORECASE)
    
    tm = re.search(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", parts)
    start = tm.group(1) if tm else ""
    end = tm.group(2) if tm else ""
    
    seg = parts.split("|")
    code = seg[0].strip() if seg else ""
    name = seg[1].strip() if len(seg) > 1 else ""
    room = ""
    for s in seg[2:]:
        s = re.sub(r"\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}", "", s).strip()
        if s and not re.match(r"^\d{1,2}:\d{2}$", s):
            room = (room + " " + s).strip()
    
    subject_code = ""
    class_code = ""
    if code:
        parts_code = code.split()
        if len(parts_code) >= 2:
            subject_code = parts_code[0]
            class_code = " ".join(parts_code[1:])
        else:
            subject_code = code
    
    return {
        "subject_code": subject_code,
        "class_code": class_code,
        "subject": name,
        "room": room,
        "start_time": start,
        "end_time": end
    }

def parse_pdf(pdf_path: str) -> Dict[str, Any]:
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        words = page.extract_words()
    
    lines = cluster_lines(words)
    bounds = find_day_columns(lines)
    if not bounds:
        raise ValueError("Không tìm thấy hàng ngày (T2/CN) trong PDF")
    
    blocks = build_blocks(lines, bounds)
    
    dates = re.findall(r"(\d{2}/\d{2}/\d{4})", " ".join(l["text"] for l in lines if l["top"] < 20))
    week_start_str, week_end_str = (dates[0], dates[1]) if len(dates) > 1 else ("", "")
    
    week_start = None
    if week_start_str:
        try:
            week_start = datetime.strptime(week_start_str, "%d/%m/%Y")
        except:
            pass
    
    schedule_items = []
    
    for day_name, lines_list in blocks.items():
        daynum = lines_list[0][1]
        day_num = lines_list[0][2] if len(lines_list[0]) > 2 else daynum
        current = []
        prev_top = None
        
        for line_tuple in lines_list:
            line = line_tuple[0]
            if prev_top is not None and line["top"] - prev_top > 12:
                if current:
                    parsed = parse_block(current)
                    if parsed["subject_code"]:
                        item = build_schedule_item(parsed, day_num, week_start)
                        if item:
                            schedule_items.append(item)
                current = []
            current.append(line)
            prev_top = line["top"]
        
        if current:
            parsed = parse_block(current)
            if parsed["subject_code"]:
                item = build_schedule_item(parsed, day_num, week_start)
                if item:
                    schedule_items.append(item)
    
    return {
        "week_start": week_start_str,
        "week_end": week_end_str,
        "items": schedule_items
    }

def build_schedule_item(parsed: Dict, day_num: int, week_start: Optional[datetime]) -> Optional[Dict]:
    if not week_start:
        return None
    
    try:
        target_date = week_start.replace(day=day_num)
        date_str = target_date.strftime("%Y-%m-%d")
        day_of_week = target_date.isoweekday()
        
        week_range = f"{week_start.strftime('%d/%m/%Y')} - {(week_start + timedelta(days=6)).strftime('%d/%m/%Y')}"
        
        return {
            "date": date_str,
            "day_of_week": day_of_week,
            "start_time": parsed["start_time"],
            "end_time": parsed["end_time"],
            "subject": parsed["subject"],
            "subject_code": parsed["subject_code"],
            "class_code": parsed["class_code"],
            "room": parsed["room"],
            "lecturer": "",
            "week_range": week_range,
            "learning_type": "",
            "note": ""
        }
    except Exception as e:
        print(f"Error building schedule item: {e}", file=sys.stderr)
        return None

def main():
    if len(sys.argv) < 2:
        print("Usage: python parse_pdf.py <pdf_path>")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    result = parse_pdf(pdf_path)
    
    if sys.stdout.encoding != 'utf-8':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()