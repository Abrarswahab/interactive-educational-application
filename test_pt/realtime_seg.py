import cv2
import numpy as np
from ultralytics import YOLO

model = YOLO(r"C:\Users\kokoh\Downloads\best.pt")

cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("Error: Could not open camera.")
    exit()

print("Press 'q' to quit.")

while True:
    ret, frame = cap.read()
    if not ret:
        print("Error: Failed to grab frame.")
        break

    results = model(frame, verbose=False)
    result = results[0]

    # Start with a copy of the original frame
    output = frame.copy()

    # Draw segmentation masks with transparency
    if result.masks is not None:
        masks = result.masks.data.cpu().numpy()
        boxes = result.boxes

        for i, mask in enumerate(masks):
            # Resize mask to frame size
            mask_resized = cv2.resize(mask, (frame.shape[1], frame.shape[0]))
            mask_bool = mask_resized > 0.5

            # Pick a random but consistent color per class
            class_id = int(boxes.cls[i].item())
            color = tuple(int(c) for c in np.array([
                (class_id * 67 + 100) % 256,
                (class_id * 113 + 50) % 256,
                (class_id * 41 + 180) % 256,
            ]))

            # Blend mask color into the frame
            overlay = output.copy()
            overlay[mask_bool] = (
                overlay[mask_bool] * 0.45 + np.array(color) * 0.55
            ).astype(np.uint8)
            output = overlay

            # Draw mask contour outline
            mask_uint8 = (mask_resized * 255).astype(np.uint8)
            contours, _ = cv2.findContours(mask_uint8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(output, contours, -1, color, 2)

            # Get bounding box and label
            x1, y1, x2, y2 = map(int, boxes.xyxy[i].tolist())
            conf = float(boxes.conf[i].item())
            label = model.names[class_id]
            text = f"{label}  {conf:.0%}"

            # Draw label background
            (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
            cv2.rectangle(output, (x1, y1 - th - 10), (x1 + tw + 8, y1), color, -1)
            cv2.putText(output, text, (x1 + 4, y1 - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)

    # Object count overlay in top-left
    count = len(result.boxes) if result.boxes is not None else 0
    cv2.rectangle(output, (0, 0), (220, 36), (0, 0, 0), -1)
    cv2.putText(output, f"Objects detected: {count}", (8, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 180), 2, cv2.LINE_AA)

    cv2.imshow("YOLO11s Real-Time Segmentation", output)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
