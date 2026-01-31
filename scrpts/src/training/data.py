# training/data.py

import h5py
import numpy as np
import torch
from torch.utils.data import TensorDataset, DataLoader

def iter_h5_blocks(
    h5_path: str,
    split: str = "train",     # "train" / "val" / "test"
    batch_size: int = 8,
    block_size: int = 20000,  # 한 번에 RAM에 올릴 샘플 수
    shuffle: bool = True,
    seed: int = 1337,
    num_workers: int = 0,
):
    """
    HDF5 파일에서 지정한 split("train"/"val"/"test")을
    block_size 단위로 잘라서 DataLoader들을 yield 해주는 제너레이터.

    사용 예시:
        for epoch in range(num_epochs):
            for loader in iter_h5_blocks(h5_path, "train", batch_size=8, block_size=20000, seed=epoch):
                for xb, yb in loader:
                    # xb: (B, L, 4)  -> 필요하면 (B, 4, L)로 transpose
                    # yb: (B, 3, 2*DS)
                    ...
    """
    rng = np.random.default_rng(seed)

    with h5py.File(h5_path, "r") as f:
        grp = f[split]
        X_dset = grp["X"]  # shape: (N, L, 4)
        Y_dset = grp["Y"]  # shape: (N, 3, 2*DS)

        N = X_dset.shape[0]
        block_starts = list(range(0, N, block_size))

        # epoch마다 block 순서 섞고 싶으면 shuffle=True로
        if shuffle:
            rng.shuffle(block_starts)

        for block_start in block_starts:
            block_end = min(block_start + block_size, N)

            # 1) HDF5 → numpy (이 block만 RAM에 올림)
            X_block = X_dset[block_start:block_end]  # (B, L, 4)
            Y_block = Y_dset[block_start:block_end]  # (B, 3, 2*DS)

            # 2) numpy → torch
            X_block = torch.from_numpy(X_block).float()
            Y_block = torch.from_numpy(Y_block).float()

            # 필요하면 여기서 채널 순서 바꿔도 됨: (B, L, 4) -> (B, 4, L)
            # X_block = X_block.permute(0, 2, 1).contiguous()

            ds = TensorDataset(X_block, Y_block)
            loader = DataLoader(
                ds,
                batch_size=batch_size,
                shuffle=shuffle,    # block 내부에서 셔플
                num_workers=num_workers,
            )

            yield loader