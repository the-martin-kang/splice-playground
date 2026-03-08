import torch
import numpy as np
from app.services.splice_model import SpliceAI
from app.services.splice_service import SplicePredictor
import os

def test_inference():
    # 1. 모델 파일 존재 확인
    model_name = "spliceAI_v1_4000_2000.pt"
    # 실제 파일이 있는 경로로 수정하세요 (예: ./app/core/weights/...)
    model_path = os.path.join("app", "core", "weights", model_name)
    
    if not os.path.exists(model_path):
        print(f"❌ 에러: 모델 파일을 찾을 수 없습니다. 경로를 확인하세요: {model_path}")
        return

    print(f"🚀 테스트 시작: {model_name} 로드 중...")
    
    # 2. 예측기 객체 생성
    # (위에서 만든 SplicePredictor 클래스가 app/services/splice_service.py에 있어야 함)
    try:
        predictor = SplicePredictor(model_name)
    except Exception as e:
        print(f"❌ 모델 로드 중 오류 발생: {e}")
        return

    # 3. 가짜 유전자 서열 생성 (테스트용 100bp)
    test_seq = "ATGC" * 25  # 100bp
    print(f"🧬 테스트 서열 생성 완료 (길이: {len(test_seq)}bp)")

    # 4. 추론 실행
    try:
        result = predictor.predict(test_seq)
        
        print("\n✅ 추론 성공!")
        print(f"📊 결과 형태(Shape): {result.shape} (클래스 수, 서열 길이)")
        
        # 5. 결과 값 해석
        # result[0]: None(정상), result[1]: Acceptor, result[2]: Donor 확률
        print("\n--- 첫 5개 염기의 예측 확률 ---")
        for i in range(5):
            print(f"Pos {i} ({test_seq[i]}): "
                  f"Normal: {result[0, i]:.4f}, "
                  f"Acceptor: {result[1, i]:.4f}, "
                  f"Donor: {result[2, i]:.4f}")
            
    except Exception as e:
        print(f"❌ 추론 도중 오류 발생: {e}")

if __name__ == "__main__":
    test_inference()