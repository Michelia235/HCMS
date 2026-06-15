"""Train a hand-hygiene action classifier (YOLOv8-cls) -> ONNX.

Image-level classifier on the hand-crops from prep_hygiene_data.py:
    classes = {hand_hygiene, other}
YOLOv8-cls is chosen because it trains in one call, is tiny (yolov8n-cls ~3M),
and exports to ONNX -> drops straight into the camera path (onnxruntime, no
torch) as a model-based replacement for the geometric RubDetector.

Run (system python with ultralytics+torch):
    python scripts/train_hygiene_cls.py --epochs 15
The exported best.onnx is copied to perception/weight_v2/hygiene_cls.onnx.

HONESTY: with the seed dataset (few clips) this OVERFITS and will NOT generalise
-- it only proves the pipeline. Train on many clips/people/sites for real use.
"""
from __future__ import annotations

import argparse
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data", "hygiene_cls")
DEST = os.path.join(ROOT, "perception", "weight_v2", "hygiene_cls.onnx")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=15)
    ap.add_argument("--imgsz", type=int, default=128)
    ap.add_argument("--model", default="yolov8n-cls.pt")
    a = ap.parse_args()

    from ultralytics import YOLO
    if not os.path.isdir(os.path.join(DATA, "train")):
        raise SystemExit(f"no dataset at {DATA} -- run prep_hygiene_data.py first")

    model = YOLO(a.model)
    model.train(data=DATA, epochs=a.epochs, imgsz=a.imgsz, batch=32,
                pretrained=True, verbose=False, plots=False)
    metrics = model.val(data=DATA, split="val", verbose=False)
    top1 = getattr(metrics, "top1", None)
    print(f"[train] val top-1 = {top1}")

    onnx = model.export(format="onnx", opset=12, imgsz=a.imgsz)
    shutil.copy(onnx, DEST)
    print(f"[train] exported -> {DEST}")
    print("NOTE: seed data overfits -> pipeline proof only, not a production model.")


if __name__ == "__main__":
    main()
