import os
import torch
import torch.nn as nn
import numpy as np

# 1. 경로 설정
current_dir = os.path.dirname(os.path.realpath(__file__))
backend_dir = os.path.dirname(os.path.dirname(current_dir))
MODEL_PATH = os.path.join(backend_dir, "spliceAI_v1_4000_2000.pt")

class SpliceInference:
    def __init__(self, model_path: str):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        if not os.path.exists(model_path):
            print(f"모델 파일을 찾을 수 없음: {model_path}")
            self.model = None
            return

        # 모델 로드
        data = torch.load(model_path, map_location=self.device, weights_only=False)
        
        # OrderedDict(가중치)인 경우와 모델 객체인 경우 모두 대응
        if isinstance(data, dict) or str(type(data)).find('OrderedDict') != -1:
            print("가중치 데이터(state_dict) 감지. 추론을 위해 모델 구조 정의가 필요할 수 있습니다.")
            # POC 단계에서는 로드된 데이터 자체를 보관
            self.model = data 
        else:
            self.model = data
            if hasattr(self.model, 'eval'):
                self.model.eval()
        
        print(f"SpliceAI 로드 완료 ({self.device})")

    def one_hot_encode(self, seq: str):
        mapping = {'A': 0, 'C': 1, 'G': 2, 'T': 3}
        seq = seq.upper()
        encoding = np.zeros((4, len(seq)), dtype=np.float32)
        for i, base in enumerate(seq):
            if base in mapping:
                encoding[mapping[base], i] = 1.0
        return encoding

    def predict(self, sequence: str):
        if self.model is None:
            return {"error": "Model not loaded"}
        
        # 추론 로직 (가중치만 있을 경우 실제 forward 연산은 모델 클래스 정의가 필요함)
        # 여기서는 API 구조 확인을 위해 더미 결과를 반환하거나 구조를 유지합니다.
        input_data = self.one_hot_encode(sequence)
        
        return {
            "acceptor_probs": [0.01] * len(sequence),
            "donor_probs": [0.02] * len(sequence)
        }

splice_service = SpliceInference(MODEL_PATH)