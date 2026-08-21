import re
import csv
import io
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

WEEKDAY_MAP = {
    'T2': 1, 'T3': 2, 'T4': 3, 'T5': 4, 'T6': 5, 'T7': 6, 'CN': 7,
    'Thứ 2': 1, 'Thứ 3': 2, 'Thứ 4': 3, 'Thứ 5': 4, 'Thứ 6': 5, 'Thứ 7': 6, 'Chủ Nhật': 7,
    'Mon': 1, 'Tue': 2, 'Wed': 3, 'Thu': 4, 'Fri': 5, 'Sat': 6, 'Sun': 7
}

def parse_web_copied_text(text: str, semester_start: datetime = None) -> List[Dict[str, Any]]:
    """
    Parse text copied directly from myDTU web page (not CSV).
    Handles the multi-line, space-separated format.
    """
    items = []
    
    if semester_start is None:
        now = datetime.now()
        semester_start = now - timedelta(days=now.weekday())
    
    # Split by course code patterns
    parts = re.split(r'\n(?="?(?:CR|CS|ENG|ES|HIS|IS|SE|IT|MA|PH)\s+\w+)', text)
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
        
        # Skip header and non-course parts
        if not re.match(r'"?(?:CR|CS|ENG|ES|HIS|IS|SE|IT|MA|PH)\s+\w+', part):
            continue
        
        # Clean up
        part = part.replace('"', '')
        part = part.replace('\n', ' ')
        
        # Extract fields using regex for each field
        # Pattern: Mã lớp (CR 424 C), Tên môn, Loại hình, Tuần học, Lịch học, Phòng, Địa điểm, Hủy
        
        # Extract mã lớp (first 2-3 words like CR 424 C)
        ma_lop_match = re.match(r'((?:CR|CS|ENG|ES|HIS|IS|SE|IT|MA|PH)\s+\S+(?:\s+\S+)?)', part)
        if not ma_lop_match:
            continue
        ma_lop = ma_lop_match.group(1).strip()
        remaining = part[ma_lop_match.end():].strip()
        
        # Extract tên môn - it's the text between mã lớp and loại hình
        # Look for LEC/LAB/DEM/PRJ as delimiter
        loai_match = re.search(r'\b(LEC|LAB|DEM|PRJ)\b', remaining)
        ten_mon = ''
        loai_hinh = ''
        if loai_match:
            loai_hinh = loai_match.group(1)
            # Subject name is between ma_lop and loai_hinh
            ten_mon = remaining[:loai_match.start()].strip()
            remaining = remaining[loai_match.end():].strip()
        else:
            # Fallback: take first chunk as subject name until we hit a known pattern
            # Find first occurrence of week pattern or time pattern
            week_pos = re.search(r'\d+--\d+', remaining)
            time_pos = re.search(r'(?:T[2-7]|CN)\s*:\s*\d{1,2}:\d{2}', remaining)
            first_pos = len(remaining)
            if week_pos:
                first_pos = min(first_pos, week_pos.start())
            if time_pos:
                first_pos = min(first_pos, time_pos.start())
            ten_mon = remaining[:first_pos].strip()
            remaining = remaining[first_pos:].strip()
        
        # Extract loại hình (LEC, LAB, DEM, PRJ) - already done above
        if not loai_hinh:
            loai_match = re.search(r'\b(LEC|LAB|DEM|PRJ)\b', remaining)
            loai_hinh = loai_match.group(1) if loai_match else ''
            if loai_match:
                remaining = remaining[loai_match.end():].strip()
        
        # Extract tuần học (1--18, 11--18, etc.)
        tuan_match = re.search(r'(\d+--\d+)', remaining)
        tuan_hoc = tuan_match.group(1) if tuan_match else '1--18'
        if tuan_match:
            remaining = remaining[tuan_match.end():].strip()
        
        # Extract lịch học (T2: 13:00 -15:00 T5: 13:00 -15:00)
        lich_match = re.search(r'((?:T[2-7]|CN)\s*:\s*\d{1,2}:\d{2}\s*[-–]\s*\d{1,2}:\d{2}(?:\s+(?:T[2-7]|CN)\s*:\s*\d{1,2}:\d{2}\s*[-–]\s*\d{1,2}:\d{2})*)', remaining)
        lich_hoc = lich_match.group(1) if lich_match else ''
        if lich_match:
            remaining = remaining[:lich_match.start()] + remaining[lich_match.end():]
            remaining = remaining.strip()
        
        # Extract room/location - remaining text after cleaning cancel section
        # Remove cancel section first
        remaining = re.sub(r'\|Tuần hủy:.*?(?=\||$)', '', remaining)
        # Also remove trailing numbers (ĐVHT) and footer text
        remaining = re.sub(r'\s+\d+\s*$', '', remaining)
        remaining = re.sub(r'Chú ý:.*$', '', remaining)
        remaining = re.sub(r'Tìm kiếm.*$', '', remaining)
        remaining = re.sub(r'--Chọn.*$', '', remaining)
        remaining = re.sub(r'Copyright.*$', '', remaining)
        phong = remaining.strip()
        
        # Clean room - remove extra spaces, keep meaningful parts
        phong = re.sub(r'\s+', ' ', phong).strip()
        
        # Parse subject code
        subject_code, class_code = parse_subject_code(ma_lop)
        
        # Parse week range
        start_week, end_week = parse_week_range(tuan_hoc)
        
        # Parse cancelled weeks (from "Tuần hủy" section in original part)
        cancel_weeks = set()
        huy_match = re.search(r'\|Tuần hủy:(.+?)(?=\||$)', part)
        if huy_match:
            cancel_text = huy_match.group(1)
            cancel_weeks = set(parse_cancel_weeks(cancel_text))
        
        # Parse schedule times
        sessions = parse_schedule_time(lich_hoc)
        
        # Generate schedule items for each week
        for week_num in range(start_week, end_week + 1):
            if week_num in cancel_weeks:
                continue
            
            week_start_date = calculate_dates_from_week(week_num, semester_start)
            week_range = f"{week_start_date.strftime('%d/%m/%Y')} - {(week_start_date + timedelta(days=6)).strftime('%d/%m/%Y')}"
            
            for day, start_time, end_time in sessions:
                class_date = week_start_date + timedelta(days=day - 1)
                
                items.append({
                    'date': class_date.strftime('%Y-%m-%d'),
                    'day_of_week': class_date.isoweekday(),
                    'start_time': start_time,
                    'end_time': end_time,
                    'subject': ten_mon if ten_mon else ma_lop,
                    'subject_code': subject_code,
                    'class_code': class_code,
                    'room': phong,
                    'lecturer': '',
                    'week_range': week_range,
                    'learning_type': loai_hinh,
                    'note': ''
                })
    
    return items

def parse_week_range(week_str: str) -> tuple:
    """Parse '1--18' or '11--18' -> (start_week, end_week)"""
    if not week_str:
        return (1, 18)
    match = re.search(r'(\d+)\s*--\s*(\d+)', week_str)
    if match:
        return (int(match.group(1)), int(match.group(2)))
    return (1, 18)

def parse_cancel_weeks(cancel_str: str) -> List[int]:
    """Parse 'Hủy 1, 2, 3, 4' -> [1,2,3,4]"""
    if not cancel_str or 'hủy' not in cancel_str.lower():
        return []
    nums = re.findall(r'\d+', cancel_str)
    return [int(n) for n in nums]

def parse_schedule_time(time_str: str) -> List[tuple]:
    """
    Parse 'T2: 13:00 -15:00\nT5: 13:00 -15:00' -> 
    [(2, '13:00', '15:00'), (5, '13:00', '15:00')]
    """
    sessions = []
    lines = time_str.strip().split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Match: T2: 13:00 -15:00 or Thứ 2: 13:00-15:00
        match = re.match(r'(T[2-7]|CN|Thứ\s*[2-7]|Chủ\s*Nhật)\s*[:\-]\s*(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})', line, re.IGNORECASE)
        if match:
            day_str = match.group(1).upper().replace(' ', '')
            start = match.group(2)
            end = match.group(3)
            day = WEEKDAY_MAP.get(day_str)
            if day:
                sessions.append((day, start, end))
    return sessions

def parse_subject_code(full_code: str) -> tuple:
    """Parse 'CR 424 C' -> ('CR', '424 C')"""
    if not full_code:
        return ('', '')
    parts = full_code.strip().split()
    if len(parts) >= 2:
        return (parts[0], ' '.join(parts[1:]))
    return (full_code, '')

def calculate_dates_from_week(week_num: int, semester_start: datetime) -> datetime:
    """Calculate Monday of given week number from semester start"""
    # Week 1 = semester_start week
    return semester_start + timedelta(weeks=week_num - 1)

def parse_registration_text(text: str, semester_start: datetime = None) -> List[Dict[str, Any]]:
    """
    Parse registration text (TSV/CSV format) to schedule items.
    
    Expected columns (tab or comma separated):
    Tên lớp, Tên môn, Loại hình, Tuần học, Lịch học, Thời gian, Phòng, Địa điểm, Lịch bổ sung, Số ĐVHT, Hủy Đăng ký /Bỏ Lớp
    """
    # First try web-copied format parser
    items = parse_web_copied_text(text, semester_start)
    if items:
        return items
    
    # Fallback to CSV/TSV parser
    # Try to detect delimiter
    sample_lines = text.strip().split('\n')[:5]
    delimiter = '\t'
    if sample_lines and ',' in sample_lines[0] and '\t' not in sample_lines[0]:
        delimiter = ','
    
    # Parse CSV/TSV
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    
    # Normalize fieldnames (remove BOM, spaces)
    if reader.fieldnames:
        reader.fieldnames = [f.strip().replace('\ufeff', '') for f in reader.fieldnames]
    
    # Default semester start: current week Monday
    if semester_start is None:
        now = datetime.now()
        semester_start = now - timedelta(days=now.weekday())
    
    for row in reader:
        # Skip empty rows
        if not any(row.values()):
            continue
        
        def get_field(row, *keys):
            for k in keys:
                v = row.get(k)
                if v is not None:
                    return v.strip()
            return ''
        
        # Extract fields (handle different possible column names)
        ten_lop = get_field(row, 'Tên lớp', 'Mã lớp', 'Class')
        ten_mon = get_field(row, 'Tên môn', 'Môn học', 'Subject')
        loai_hinh = get_field(row, 'Loại hình', 'Type')
        tuan_hoc = get_field(row, 'Tuần học', 'Tuần', 'Weeks')
        lich_hoc = get_field(row, 'Lịch học', 'Thứ', 'Schedule')
        thoi_gian = get_field(row, 'Thời gian', 'Giờ', 'Time')
        phong = get_field(row, 'Phòng', 'Room')
        dia_diem = get_field(row, 'Địa điểm', 'Location')
        lich_bo_sung = get_field(row, 'Lịch bổ sung', 'Extra')
        huy_dang_ky = get_field(row, 'Hủy Đăng ký /Bỏ Lớp', 'Hủy', 'Cancelled')
        
        if not ten_lop or not ten_mon:
            continue
        
        # Parse subject code
        subject_code, class_code = parse_subject_code(ten_lop)
        
        # Parse week range
        start_week, end_week = parse_week_range(tuan_hoc)
        
        # Parse cancelled weeks
        cancel_weeks = set(parse_cancel_weeks(huy_dang_ky))
        
        # Parse schedule times
        sessions = parse_schedule_time(lich_hoc)
        if not sessions and thoi_gian:
            sessions = parse_schedule_time(thoi_gian)
        
        # Combine room and location
        room = phong
        if dia_diem and dia_diem != phong:
            room = f"{phong}, {dia_diem}" if phong else dia_diem
        
        # Generate schedule items for each week
        for week_num in range(start_week, end_week + 1):
            if week_num in cancel_weeks:
                continue
            
            week_start_date = calculate_dates_from_week(week_num, semester_start)
            week_range = f"{week_start_date.strftime('%d/%m/%Y')} - {(week_start_date + timedelta(days=6)).strftime('%d/%m/%Y')}"
            
            for day, start_time, end_time in sessions:
                class_date = week_start_date + timedelta(days=day - 1)
                
                items.append({
                    'date': class_date.strftime('%Y-%m-%d'),
                    'day_of_week': class_date.isoweekday(),
                    'start_time': start_time,
                    'end_time': end_time,
                    'subject': ten_mon,
                    'subject_code': subject_code,
                    'class_code': class_code,
                    'room': room,
                    'lecturer': '',
                    'week_range': week_range,
                    'learning_type': loai_hinh,
                    'note': lich_bo_sung
                })
    
    return items

def parse_simple_text(text: str) -> List[Dict[str, Any]]:
    """
    Parse simple text format (one class per line, tab/space separated).
    Fallback for non-CSV text.
    """
    items = []
    lines = text.strip().split('\n')
    
    # Try to parse as TSV first
    if '\t' in text:
        return parse_registration_text(text)
    
    # Try comma
    if ',' in text and text.count(',') > len(lines) * 2:
        return parse_registration_text(text)
    
    return items

# Test function
if __name__ == '__main__':
    sample = """Tên lớp\tTên môn\tLoại hình\tTuần học\tLịch học\tThời gian\tPhòng\tĐịa điểm\tLịch bổ sung\tSố ĐVHT\tHủy Đăng ký /Bỏ Lớp
CR 424 C\tLập Trình Ứng Dụng cho các Thiết Bị Di Động\tLEC\t1--18\t234567CN\tT2: 13:00 -15:00\nT5: 13:00 -15:00\tOnline 25 506\tOnline\n78A Phan Văn Trị\t\t3\t
CS 303 K\tPhân Tích & Thiết Kế Hệ Thống\tLEC\t1--18\t234567CN\tT2: 15:15 -17:15\nT5: 15:15 -17:15\tOnline 35 305\tOnline\n78A Phan Văn Trị\t\t3\t
CS 316 S\tGiới Thiệu Cấu Trúc Dữ Liệu & Giải Thuật\tLEC\t1--8\t234567CN\tT3: 09:15 -11:15\nT6: 09:15 -11:15\tOnline 29 508\tOnline\n78A Phan Văn Trị\t\t2\t"""
    
    result = parse_registration_text(sample)
    import json
    print(json.dumps(result[:3], ensure_ascii=False, indent=2))
    print(f'Total items: {len(result)}')