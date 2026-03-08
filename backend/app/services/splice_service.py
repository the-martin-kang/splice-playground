import torch
import numpy as np
import os
from app.services.splice_model import SpliceAI

class SplicePredictor:
    def __init__(self, model_filename: str):
        # 1. 경로 설정 (app/core/weights 폴더 안에 모델이 있다고 가정)
        current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        model_path = os.path.join(current_dir, "core", "weights", model_filename)
        
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        # 2. 모델 객체 생성 및 가중치 로드
        self.model = SpliceAI().to(self.device)
        try:
            # map_location을 사용하여 GPU가 없어도 CPU에서 로드 가능하게 함
            state_dict = torch.load(model_path, map_location=self.device)
            self.model.load_state_dict(state_dict)
            self.model.eval()  # 중요: 추론 모드로 전환 (BatchNorm 고정)
            print(f"✅ SpliceAI 모델 로드 완료: {model_filename} ({self.device})")
        except Exception as e:
            print(f"❌ 모델 로드 실패: {e}")

    def _one_hot_encode(self, sequence: str):
        """ATCG 서열을 모델이 이해하는 숫자(텐서)로 변환"""
        mapping = {'A': 0, 'C': 1, 'G': 2, 'T': 3}
        seq_len = len(sequence)
        # (4, L) 형태의 행렬 생성
        encoded = np.zeros((4, seq_len), dtype=np.float32)
        for i, base in enumerate(sequence.upper()):
            if base in mapping:
                encoded[mapping[base], i] = 1.0
            # N이나 기타 문자는 [0, 0, 0, 0]으로 남음
        return torch.tensor(encoded).unsqueeze(0).to(self.device) # (1, 4, L) 형태로 반환

    def predict(self, sequence: str):
        """서열을 넣어 스플라이싱 확률 점수를 반환"""
        input_tensor = self._one_hot_encode(sequence)
        
        with torch.no_grad(): # 기울기 계산 비활성화 (추론 속도 향상)
            logits = self.model(input_tensor)
            # Softmax를 통해 0~1 사이 확률값으로 변환
            # 결과 크기: [1, 3, L] -> (Batch, Classes, Length)
            probs = torch.softmax(logits, dim=1)
            
        return probs.cpu().numpy()[0] # (3, L) 형태로 반환