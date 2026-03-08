import torch
import torch.nn as nn

class ResidualBlock(nn.Module):
    def __init__(self, filter_size, dilation):
        super(ResidualBlock, self).__init__()
        # 가중치 키의 인덱스(0, 2, 3, 5)와 일치시키기 위해 Sequential 구조를 조정합니다.
        self.path = nn.Sequential(
            nn.BatchNorm1d(32),                         # path.0
            nn.ReLU(),                                  # path.1 (가중치 없음)
            nn.Conv1d(32, 32, filter_size, 
                      dilation=dilation, 
                      padding=dilation*(filter_size-1)//2), # path.2
            nn.BatchNorm1d(32),                         # path.3
            nn.ReLU(),                                  # path.4 (가중치 없음)
            nn.Conv1d(32, 32, filter_size, 
                      dilation=dilation, 
                      padding=dilation*(filter_size-1)//2)  # path.5
        )

    def forward(self, x):
        return x + self.path(x)

class SpliceAI(nn.Module):
    def __init__(self):
        super(SpliceAI, self).__init__()
        # stem.weight, stem.bias
        self.stem = nn.Conv1d(4, 32, 1)
        # conv.weight, conv.bias
        self.conv = nn.Conv1d(32, 32, 1)
        
        # phase1 ~ phase4: 각 4개의 ResidualBlock
        # 가중치 키 예시: phase1.0.path.0.weight ...
        self.phase1 = nn.Sequential(*[ResidualBlock(11, 1) for _ in range(4)])
        self.phase2 = nn.Sequential(*[ResidualBlock(11, 4) for _ in range(4)])
        self.phase3 = nn.Sequential(*[ResidualBlock(21, 10) for _ in range(4)])
        self.phase4 = nn.Sequential(*[ResidualBlock(41, 25) for _ in range(4)])
        
        # final.weight, final.bias
        self.final = nn.Conv1d(32, 3, 1)

    def forward(self, x):
        x = self.stem(x)
        # 가중치 키에 'conv'가 별도로 존재하므로 잔차 연결 없이 수행하거나 
        # 구조에 따라 x = x + self.conv(x) 형태일 수 있습니다. 
        # 제공된 키 리스트 순서상 stem -> conv -> phase 순차 통과가 일반적입니다.
        x = x + self.conv(x) 
        
        x = self.phase1(x)
        x = x + self.phase2(x) # 일부 구현에선 phase 간에도 잔차 연결을 사용합니다.
        x = x + self.phase3(x)
        x = x + self.phase4(x)
        
        return self.final(x)