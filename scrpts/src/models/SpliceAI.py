import ResBlock

class SpliceAI(nn.Module):
    def __init__(self):
        super().__init__()
        self.stem = nn.Conv1d(in_channels=4, out_channels=32, kernel_size=1, dilation=1)
        self.conv = nn.Conv1d(in_channels=32, out_channels=32, kernel_size=1, dilation=1)
        self.final = nn.Conv1d(in_channels=32, out_channels=3, kernel_size=1, dilation=1)
        # AGCT라 in channel=4

        self.phase1 = nn.Sequential(
            ResBlock(32, 32, kernel_size=11, dilation=1),
            ResBlock(32, 32, kernel_size=11, dilation=1),
            ResBlock(32, 32, kernel_size=11, dilation=1),
            ResBlock(32, 32, kernel_size=11, dilation=1),
        )

        self.phase2 = nn.Sequential(
            ResBlock(32, 32, kernel_size=11, dilation=4),
            ResBlock(32, 32, kernel_size=11, dilation=4),
            ResBlock(32, 32, kernel_size=11, dilation=4),
            ResBlock(32, 32, kernel_size=11, dilation=4)
        )

        self.phase3 = nn.Sequential(
            ResBlock(32, 32, kernel_size=21, dilation=10),
            ResBlock(32, 32, kernel_size=21, dilation=10),
            ResBlock(32, 32, kernel_size=21, dilation=10),
            ResBlock(32, 32, kernel_size=21, dilation=10),
        )

        self.phase4 = nn.Sequential(
            ResBlock(32, 32, kernel_size=41, dilation=25),
            ResBlock(32, 32, kernel_size=41, dilation=25),
            ResBlock(32, 32, kernel_size=41, dilation=25),
            ResBlock(32, 32, kernel_size=41, dilation=25),
        )


    def forward(self, x):
        x = self.stem(x)
        residual = self.conv(x)
        x = self.phase1(x)
        residual = residual + self.conv(x)
        x = self.phase2(x)
        residual = residual + self.conv(x)
        x = self.phase3(x)
        residual = residual + self.conv(x)
        x = self.phase4(x)

        x = residual + self.conv(x)
        x = self.final(x)

        return x