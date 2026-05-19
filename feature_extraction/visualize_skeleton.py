import os
import glob
import numpy as np
import argparse
import cv2
import random

SKELETON_EDGES = [
    (0, 1), (0, 2), (1, 3), (2, 4),
    (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),
    (5, 11), (6, 12), (11, 12),
    (11, 13), (13, 15), (12, 14), (14, 16),
]

NUM_KEYPOINTS = 17


def draw_skeleton_on_frame(frame, keypoints, conf_thresh=0.3):
    canvas = frame.copy()
    for (i, j) in SKELETON_EDGES:
        xi, yi, ci = keypoints[i]
        xj, yj, cj = keypoints[j]
        if ci > conf_thresh and cj > conf_thresh:
            cv2.line(canvas, (int(xi), int(yi)), (int(xj), int(yj)), (0, 200, 255), 2)
    for x, y, c in keypoints:
        if c > conf_thresh:
            cv2.circle(canvas, (int(x), int(y)), 4, (0, 255, 0), -1)
    return canvas


def draw_skeleton_only(shape, keypoints, conf_thresh=0.3):
    h, w = shape
    canvas = np.ones((h, w, 3), dtype=np.uint8) * 30
    for (i, j) in SKELETON_EDGES:
        xi, yi, ci = keypoints[i]
        xj, yj, cj = keypoints[j]
        if ci > conf_thresh and cj > conf_thresh:
            cv2.line(canvas, (int(xi), int(yi)), (int(xj), int(yj)), (0, 200, 255), 2)
    for x, y, c in keypoints:
        if c > conf_thresh:
            cv2.circle(canvas, (int(x), int(y)), 4, (0, 255, 0), -1)
    return canvas


def compare_video(video_name, ske_dir, rawframes_dir, conf_thresh, save):
    npy_path = os.path.join(ske_dir, f"{video_name}.npy")
    frame_folder = os.path.join(rawframes_dir, video_name)

    if not os.path.exists(npy_path):
        print(f"[LỖI] Không tìm thấy: {npy_path}")
        return
    if not os.path.exists(frame_folder):
        print(f"[LỖI] Không tìm thấy rawframes: {frame_folder}")
        return

    skeleton_data = np.load(npy_path)           # (T, 17, 3)
    frame_files = sorted(glob.glob(os.path.join(frame_folder, "img_*.jpg")))

    if not frame_files:
        print(f"[LỖI] Không tìm thấy img_*.jpg trong: {frame_folder}")
        return

    T = min(len(skeleton_data), len(frame_files))
    print(f"Video: {video_name} | Frames: {T}")

    # Lấy kích thước ảnh gốc
    sample = cv2.imread(frame_files[0])
    h, w = sample.shape[:2]

    writer = None
    if save:
        out_path = f"{video_name}_compare.mp4"
        writer = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*"mp4v"), 25, (w * 2, h))
        print(f"Lưu ra: {out_path}")

    for i in range(T):
        frame = cv2.imread(frame_files[i])
        if frame is None:
            continue

        # Bên phải: skeleton đè lên ảnh gốc
        right = draw_skeleton_on_frame(frame, skeleton_data[i], conf_thresh)

        # Bên trái: video gốc
        left = frame.copy()

        # Label
        cv2.putText(left,  "Video goc",  (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2)
        cv2.putText(right, "Skeleton",   (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0),     2)
        cv2.putText(left,  f"Frame {i+1}/{T}", (10, h-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200,200,200), 1)

        # Ghép ngang
        combined = np.hstack([left, right])

        if writer:
            writer.write(combined)
        else:
            cv2.imshow(f"So sanh: {video_name}  [Q] quit  [Space] pause", combined)
            key = cv2.waitKey(40)
            if key == ord('q'):
                break
            elif key == ord(' '):
                cv2.waitKey(0)

    if writer:
        writer.release()
        print("Lưu xong!")
    else:
        cv2.destroyAllWindows()


def parse_args():
    parser = argparse.ArgumentParser(description="So sánh video gốc vs skeleton")
    parser.add_argument("ske_dir",       type=str, help="Thư mục Skeleton_features")
    parser.add_argument("rawframes_dir", type=str, help="Thư mục Rawframes")
    parser.add_argument("--video",  type=str,   default=None,  help="Tên video cụ thể")
    parser.add_argument("--n",      type=int,   default=1,     help="Số video ngẫu nhiên")
    parser.add_argument("--conf",   type=float, default=0.3,   help="Ngưỡng confidence")
    parser.add_argument("--save",   action="store_true",       help="Lưu ra .mp4")
    return parser.parse_args()


def main():
    args = parse_args()

    if args.video:
        videos = [args.video]
    else:
        all_npy = [f.replace(".npy", "") for f in os.listdir(args.ske_dir) if f.endswith(".npy")]
        videos = random.sample(all_npy, min(args.n, len(all_npy)))
        print(f"Chọn ngẫu nhiên {len(videos)} video: {videos}")

    for vid in videos:
        compare_video(vid, args.ske_dir, args.rawframes_dir, args.conf, args.save)


if __name__ == "__main__":
    main()