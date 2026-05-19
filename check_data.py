import os
import numpy as np
import argparse
from tqdm import tqdm


def parse_args():
    parser = argparse.ArgumentParser(description="Kiểm tra RGB + Skeleton features")
    parser.add_argument("--rgb_dir", type=str, default="D:/dataset/I3D_features")
    parser.add_argument("--ske_dir", type=str, default="D:/dataset/Skeleton_features")
    return parser.parse_args()


def main():
    args = parse_args()

    # ── Lấy danh sách video name từ mỗi folder ──────────────────────────
    rgb_files  = {f.replace("-rgb.npz", "") for f in os.listdir(args.rgb_dir)  if f.endswith("-rgb.npz")}
    ske_files  = {f.replace(".npy", "")     for f in os.listdir(args.ske_dir)  if f.endswith(".npy")}

    both       = rgb_files & ske_files
    only_rgb   = rgb_files - ske_files
    only_ske   = ske_files - rgb_files

    print("=" * 55)
    print(f"  RGB features    : {len(rgb_files):>5} video")
    print(f"  Skeleton files  : {len(ske_files):>5} video")
    print(f"  Có ĐỦ cả 2      : {len(both):>5} video  ✅")
    print(f"  Chỉ có RGB      : {len(only_rgb):>5} video  ⚠️")
    print(f"  Chỉ có Skeleton : {len(only_ske):>5} video  ⚠️")
    print("=" * 55)

    if not both:
        print("[LỖI] Không có video nào có đủ cả 2 features!")
        return

    # ── Kiểm tra chi tiết trên sample ngẫu nhiên ────────────────────────
    import random
    samples = random.sample(sorted(both), min(10, len(both)))

    print(f"\nKiểm tra chi tiết 10 video ngẫu nhiên:")
    print(f"{'Video':<30} {'RGB shape':<20} {'Skeleton shape':<20} {'Status'}")
    print("-" * 85)

    rgb_shapes, ske_shapes = [], []
    errors = []

    for vid in tqdm(samples, desc="Checking", leave=False):
        try:
            rgb = np.load(os.path.join(args.rgb_dir, f"{vid}-rgb.npz"))["feature"]
            ske = np.load(os.path.join(args.ske_dir, f"{vid}.npy"))

            rgb_shapes.append(rgb.shape)
            ske_shapes.append(ske.shape)

            status = "✅ OK"
            # Kiểm tra NaN/Inf
            if np.isnan(rgb).any() or np.isinf(rgb).any():
                status = "❌ RGB có NaN/Inf"
                errors.append(vid)
            elif np.isnan(ske).any() or np.isinf(ske).any():
                status = "❌ Skeleton có NaN/Inf"
                errors.append(vid)
            # Kiểm tra skeleton có detect được người không
            elif (ske[:, :, 2] == 0).all():
                status = "⚠️  Skeleton toàn 0 (không detect được người)"

            print(f"{vid:<30} {str(rgb.shape):<20} {str(ske.shape):<20} {status}")

        except Exception as e:
            print(f"{vid:<30} {'ERROR':<20} {'ERROR':<20} ❌ {e}")
            errors.append(vid)

    # ── Thống kê tổng hợp ────────────────────────────────────────────────
    print("\n" + "=" * 55)
    print("THỐNG KÊ TỔNG HỢP")
    print("=" * 55)

    if rgb_shapes:
        rgb_chunks = [s[1] for s in rgb_shapes]
        ske_frames = [s[0] for s in ske_shapes]
        print(f"  RGB - chunks/video : min={min(rgb_chunks)}, max={max(rgb_chunks)}, avg={np.mean(rgb_chunks):.1f}")
        print(f"  RGB - feature dim  : {rgb_shapes[0][2]}")
        print(f"  Skeleton - frames  : min={min(ske_frames)}, max={max(ske_frames)}, avg={np.mean(ske_frames):.1f}")
        print(f"  Skeleton - kpts    : {ske_shapes[0][1]} keypoints x {ske_shapes[0][2]} (x,y,conf)")

    print(f"\n  Lỗi phát hiện: {len(errors)} video")
    if errors:
        for e in errors:
            print(f"    - {e}")

    print("\n✅ Data sẵn sàng để train!" if not errors else "\n⚠️  Kiểm tra lại các video bị lỗi trước khi train.")


if __name__ == "__main__":
    main()
