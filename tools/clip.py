import json
import os
import pandas as pd
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ffmpeg_path = os.path.join(BASE_DIR, "ffmpeg.exe")

env = os.environ.copy()
env["PATH"] = BASE_DIR + os.pathsep + env["PATH"]

with open("annotations/NurViD_annotations.json", "r") as f:
    data = json.load(f)

video_info = []

for video_name in list(data.keys()):
    video_id = data[video_name]["url"].split("=")[-1]
    video_file = os.path.join("dataset/Original_videos", video_id + ".mp4")

    if not os.path.exists(video_file):
        print(f"[BỎ QUA] {video_file}")
        continue

    operation_id = data[video_name]["operationID"]
    annotations = data[video_name]["annotations"]

    for i, annotation in enumerate(annotations):
        start_time = annotation["segment"][0]
        end_time = annotation["segment"][1]
        duration = end_time - start_time

        os.makedirs("dataset/Segments", exist_ok=True)
        out_path = os.path.join("dataset/Segments", f"{video_id}_{i+1}.mp4")

        command = [ffmpeg_path, "-ss", str(start_time), "-i", video_file, "-t", str(duration), "-c", "copy", "-y", out_path]

        ret = subprocess.run(command, env=env)

        if ret.returncode != 0:
            print(f"[LỖI] {out_path}")
        else:
            print(f"[OK] {out_path}")

        video_info.append({
            "Video Name": out_path,
            "Operation ID": operation_id,
            "Action ID": annotation["actionID"]
        })

pd.DataFrame(video_info).to_excel("dataset/clip_report.xlsx", index=False)
print(f"Xong: {len(video_info)} clips")