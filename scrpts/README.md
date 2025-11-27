## Configs
- 자원부족으로 Toy set으로 PoC를 하고 추후 full dataset을 넣은 모델을 사용 할 예정이다.
- Toy dataset
    - Group 'train':
        - X shape=(16072, 7000, 4)
        - Y shape=(16072, 5000, 3)
    - Group 'val':
        - X shape=(1865, 15000, 4)
        - Y shape=(1865, 3, 20000)
    - Group 'test':
        - X shape=(8384, 15000, 4)
        - Y shape=(8384, 3, 20000)

    
- full dataset
    - Group 'train':
        - X shape=(218124, 15000, 4)
        - Y shape=(218124, 3, 20000)
        - chunk_size=10000(.h5 file)
    - Group 'val':
        - X shape=(24236, 15000, 4)
        - Y shape=(24236, 3, 20000)
        - chunk_size=10000
    - Group 'test':
        - X shape=(21385, 15000, 4)
        - Y shape=(21385, 3, 20000)
        - chunk_size=10000
