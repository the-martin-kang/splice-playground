# training/train.py 같은 데서

from training.data import iter_h5_blocks

h5_path = "scrpts/data/splice_data.h5"

# for epoch in range(num_epochs):
#     print(f"Epoch {epoch}")
#
#     # train
#     for loader in iter_h5_blocks(h5_path, split="train",
#                                  batch_size=8,
#                                  block_size=20000,
#                                  seed=epoch,
#                                  num_workers=4):
#         for xb, yb in loader:
#             xb = xb.to(device)  # (B, L, 4) 또는 (B, 4, L)
#             yb = yb.to(device)
#
#             optimizer.zero_grad()
#             out = model(xb)
#             loss = criterion(out, yb)
#             loss.backward()
#             optimizer.step()
#
#     # val
#     with torch.no_grad():
#         for loader in iter_h5_blocks(h5_path, split="val",
#                                      batch_size=8,
#                                      block_size=20000,
#                                      seed=epoch,
#                                      num_workers=2,
#                                      shuffle=False):
#             for xb, yb in loader:
#                 xb = xb.to(device)
#                 yb = yb.to(device)
#                 out = model(xb)
#                 val_loss = criterion(out, yb)
#                 ...