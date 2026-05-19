import os
import glob
import numpy as np
import argparse
import cv2
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor
from mmpose.apis import MMPoseInferencer


NUM_KEYPOINTS = 17


def read_batch_parallel(file_list):
    with ThreadPoolExecutor(max_workers=16) as exe:
        frames = list(exe.map(cv2.imread, file_list))
    return [f for f in frames if f is not None]


def process_single_video_folder(inferencer, frame_folder, output_npy_path, batch_size):
    frame_files = sorted(glob.glob(os.path.join(frame_folder, "img_*.jpg")))

    if not frame_files:
        print(f"[CẢNH BÁO] Không tìm thấy img_*.jpg trong: {frame_folder}")
        return

    video_skeleton_data = []

    for i in range(0, len(frame_files), batch_size):
        batch_files = frame_files[i: i + batch_size]
        batch = read_batch_parallel(batch_files)
        if not batch:
            continue

        # FIX: MMPoseInferencer trả về generator — phải dùng next() hoặc list()
        result_generator = inferencer(batch, show=False)
        all_results = list(result_generator)  # consume generator

        for result in all_results:
            predictions = result.get("predictions", [[]])[0]  # list of persons in 1 frame

            if predictions and len(predictions) > 0:
                # Lấy người có bbox_score cao nhất
                best = max(predictions, key=lambda x: x["bbox_score"])
                kps = np.array(best["keypoints"])              # (17, 2)
                kps_score = np.array(best["keypoint_scores"])  # (17,)
                kps_full = np.concatenate(
                    [kps, kps_score[:, None]], axis=1)          # (17, 3)
            else:
                kps_full = np.zeros((NUM_KEYPOINTS, 3), dtype=np.float32)

            video_skeleton_data.append(kps_full)

    if not video_skeleton_data:
        print(f"[BỎ QUA] Không có frame hợp lệ: {frame_folder}")
        return

    np.save(output_npy_path, np.array(video_skeleton_data, dtype=np.float32))


def get_video_folders(src_dir, level):
    if level == 1:
        return [f.path for f in os.scandir(src_dir) if f.is_dir()]
    elif level == 2:
        folders = []
        for class_dir in os.scandir(src_dir):
            if class_dir.is_dir():
                for video_dir in os.scandir(class_dir.path):
                    if video_dir.is_dir():
                        folders.append(video_dir.path)
        return folders
    else:
        raise ValueError("level phải là 1 hoặc 2")


def parse_args():
    parser = argparse.ArgumentParser(description="Trích xuất skeleton (ViTPose)")
    parser.add_argument("src_dir",  type=str, help="Thư mục Rawframes")
    parser.add_argument("out_dir",  type=str, help="Thư mục xuất .npy")
    parser.add_argument("--level",      type=int,   default=1, choices=[1, 2])
    parser.add_argument("--batch_size", type=int,   default=16)
    parser.add_argument("--model",      type=str,   default="vitpose-l",
                        help="vitpose-b / vitpose-l / vitpose-h")
    parser.add_argument("--det_model",  type=str,   default="rtmdet-m",
                        help="Model detect người: rtmdet-m / rtmdet-l")
    parser.add_argument("--det_conf",   type=float, default=0.3,
                        help="Ngưỡng confidence detect người")
    return parser.parse_args()


def main():
    args = parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    print(f"Đang tải ViTPose ({args.model}) + detector ({args.det_model}) ...")

    inferencer = MMPoseInferencer(
        pose2d=args.model,
        det_model=args.det_model,
        device="cuda",
    )

    all_folders = get_video_folders(args.src_dir, args.level)

    todo_folders = []
    skipped = 0
    for folder_path in all_folders:
        out_path = os.path.join(args.out_dir, f"{os.path.basename(folder_path)}.npy")
        if os.path.exists(out_path):
            skipped += 1
        else:
            todo_folders.append(folder_path)

    print(f"Tổng: {len(all_folders)} | Bỏ qua: {skipped} | Cần xử lý: {len(todo_folders)}")

    for folder_path in tqdm(todo_folders, desc="Extracting Skeletons (ViTPose)"):
        out_path = os.path.join(args.out_dir, f"{os.path.basename(folder_path)}.npy")
        process_single_video_folder(inferencer, folder_path, out_path, args.batch_size)

    print("Hoàn tất!")


if __name__ == "__main__":
    main()