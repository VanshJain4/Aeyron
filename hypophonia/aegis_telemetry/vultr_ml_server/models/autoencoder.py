"""
PyTorch Autoencoder: 5-dim voice features → bottleneck 2 → 5-dim. MSE loss.
Inputs assumed min-max scaled [0, 1].
"""
import torch
import torch.nn as nn

INPUT_DIM = 5
ENCODER_DIMS = (5, 4, 2)
DECODER_DIMS = (2, 4, 5)


class Autoencoder(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(ENCODER_DIMS[0], ENCODER_DIMS[1]),
            nn.ReLU(),
            nn.Linear(ENCODER_DIMS[1], ENCODER_DIMS[2]),
            nn.ReLU(),
        )
        self.decoder = nn.Sequential(
            nn.Linear(DECODER_DIMS[0], DECODER_DIMS[1]),
            nn.ReLU(),
            nn.Linear(DECODER_DIMS[1], DECODER_DIMS[2]),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        z = self.encoder(x)
        return self.decoder(z)
