import cv2
import numpy as np
from insightface.app import FaceAnalysis

PROFILE_IMAGE = r"C:\Users\User\Desktop\face_test\profile.jpg"
SELFIE_IMAGE = r"C:\Users\User\Desktop\face_test\selfie.jpg"

print("Initializing InsightFace...")

app = FaceAnalysis(
    name="buffalo_l",
    providers=["CPUExecutionProvider"],
)

app.prepare(
    ctx_id=0,
    det_size=(640, 640),
)

print("Model ready.")

profile_img = cv2.imread(PROFILE_IMAGE)
selfie_img = cv2.imread(SELFIE_IMAGE)

if profile_img is None:
    raise Exception(f"Could not read profile image: {PROFILE_IMAGE}")

if selfie_img is None:
    raise Exception(f"Could not read selfie image: {SELFIE_IMAGE}")

print("Detecting profile face...")
profile_faces = app.get(profile_img)

print("Detecting selfie face...")
selfie_faces = app.get(selfie_img)

print(f"Profile faces detected: {len(profile_faces)}")
print(f"Selfie faces detected: {len(selfie_faces)}")

if len(profile_faces) == 0:
    raise Exception("No face detected in profile image.")

if len(selfie_faces) == 0:
    raise Exception("No face detected in selfie image.")

if len(profile_faces) > 1:
    print("WARNING: Multiple faces detected in profile image.")

if len(selfie_faces) > 1:
    print("WARNING: Multiple faces detected in selfie image.")

profile_embedding = profile_faces[0].embedding
selfie_embedding = selfie_faces[0].embedding

# Normalize embeddings
profile_embedding = profile_embedding / np.linalg.norm(profile_embedding)
selfie_embedding = selfie_embedding / np.linalg.norm(selfie_embedding)

# Cosine similarity
similarity = float(
    np.dot(profile_embedding, selfie_embedding)
)

print()
print("==============================")
print("FACE COMPARISON RESULT")
print("==============================")
print(f"Cosine similarity: {similarity:.4f}")
print(f"Similarity percentage: {similarity * 100:.2f}%")
print("==============================")