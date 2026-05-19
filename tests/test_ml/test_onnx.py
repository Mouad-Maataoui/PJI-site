from app.ml.onnx_processor_bg import create_background_remover
from app.ml.onnx_processor_up import create_upscaler
from app.ml.model_loader import model_manager

import sys

MODEL_TYPE = "bg_remove"
MODEL_NAME = "birefnet-com"

if __name__ == '__main__':
    
    try:
        model_manager._download_model(MODEL_NAME, model_type=MODEL_TYPE)
    except RuntimeError as e:
        print("Error during model download, ", e)
        sys.exit(1)
    model_path = model_manager.get_model_path(MODEL_NAME)
    
    match MODEL_TYPE:
        case "bg_remove":
            onnx = create_background_remover("birefnet-com", model_path=model_path)
        case "upscale":
            onnx = create_upscaler(model_spec="realesrgan-x4-plus", model_path=model_path)

    print(onnx.session.get_inputs()[0])
    print(onnx.config)
    print(onnx.model_path)
