from insightface.app import FaceAnalysis

print("Initializing InsightFace...")

app = FaceAnalysis(
    name="buffalo_l",
    providers=["CPUExecutionProvider"],
)

app.prepare(
    ctx_id=0,
    det_size=(640, 640),
)

print("InsightFace initialized successfully!")
print("Loaded models:")
print(app.models.keys())