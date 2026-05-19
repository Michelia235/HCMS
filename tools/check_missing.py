import json
import os
import pandas as pd

json_path = "annotations/NurViD_annotations.json"
excel_path = "dataset/clip_report.xlsx"

with open(json_path, "r") as f:
    data = json.load(f)

expected_clips = set()
for key in data.keys():
    v_url = data[key]["url"]
    v_id = v_url.split("=")[-1]
    annotations = data[key]["annotations"]
    for i in range(len(annotations)):
        expected_clips.add(f"{v_id}_{i+1}.mp4")

try:
    df = pd.read_excel(excel_path)
    processed_clips = set()
    for path in df["Video Name"]:
        filename = os.path.basename(path)
        processed_clips.add(filename)
except FileNotFoundError:
    print(f"Không tìm thấy file {excel_path}. Hãy chắc chắn bạn đã chạy clip.py thành công.")
    exit()

# 3. So sánh để tìm ra các clip bị thiếu
missing_clips = expected_clips - processed_clips

# 4. In báo cáo
print("="*40)
print("BÁO CÁO ĐỐI SOÁT DỮ LIỆU")
print("="*40)
print(f"Tổng số clip dự kiến (JSON): {len(expected_clips)}")
print(f"Tổng số clip thực tế (Excel): {len(processed_clips)}")
print(f"Số clip bị lỗi/thiếu:       {len(missing_clips)}")
print("="*40)

if missing_clips:
    print("\nDANH SÁCH CÁC CLIP CHƯA ĐƯỢC XỬ LÝ:")
    sorted_missing = sorted(list(missing_clips))
    for clip in sorted_missing[:20]:
        print(f" - {clip}")
    
    if len(missing_clips) > 20:
        print(f"   ... và {len(missing_clips) - 20} clip khác.")
        
    with open("dataset/missing_clips.txt", "w") as f:
        for clip in sorted_missing:
            f.write(f"{clip}\n")
    print("\nĐã lưu toàn bộ danh sách lỗi vào file: dataset/missing_clips.txt")
else:
    print("\nTuyệt vời! 100% dữ liệu đã được xử lý thành công, không sót clip nào.")