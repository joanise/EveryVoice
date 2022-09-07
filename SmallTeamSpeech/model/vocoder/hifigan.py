import itertools

import pytorch_lightning as pl
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.nn import AvgPool1d, Conv1d, Conv2d, ConvTranspose1d
from torch.nn.utils import remove_weight_norm, spectral_norm, weight_norm

from config.base_config import BaseConfig

LRELU_SLOPE = 0.1


def init_weights(m, mean=0.0, std=0.01):
    classname = m.__class__.__name__
    if classname.find("Conv") != -1:
        m.weight.data.normal_(mean, std)


def get_padding(kernel_size, dilation=1):
    return int((kernel_size * dilation - dilation) / 2)


class ResBlock1(torch.nn.Module):
    # TODO: refactor to depthwise-separable convolutions in generator
    def __init__(self, config, channels, kernel_size=3, dilation=(1, 3, 5)):
        super(ResBlock1, self).__init__()
        self.config = config
        self.convs1 = nn.ModuleList(
            [
                weight_norm(
                    Conv1d(
                        channels,
                        channels,
                        kernel_size,
                        1,
                        dilation=dilation[0],
                        padding=get_padding(kernel_size, dilation[0]),
                    )
                ),
                weight_norm(
                    Conv1d(
                        channels,
                        channels,
                        kernel_size,
                        1,
                        dilation=dilation[1],
                        padding=get_padding(kernel_size, dilation[1]),
                    )
                ),
                weight_norm(
                    Conv1d(
                        channels,
                        channels,
                        kernel_size,
                        1,
                        dilation=dilation[2],
                        padding=get_padding(kernel_size, dilation[2]),
                    )
                ),
            ]
        )
        self.convs1.apply(init_weights)

        self.convs2 = nn.ModuleList(
            [
                weight_norm(
                    Conv1d(
                        channels,
                        channels,
                        kernel_size,
                        1,
                        dilation=1,
                        padding=get_padding(kernel_size, 1),
                    )
                ),
                weight_norm(
                    Conv1d(
                        channels,
                        channels,
                        kernel_size,
                        1,
                        dilation=1,
                        padding=get_padding(kernel_size, 1),
                    )
                ),
                weight_norm(
                    Conv1d(
                        channels,
                        channels,
                        kernel_size,
                        1,
                        dilation=1,
                        padding=get_padding(kernel_size, 1),
                    )
                ),
            ]
        )
        self.convs2.apply(init_weights)

    def forward(self, x):
        for c1, c2 in zip(self.convs1, self.convs2):
            xt = F.leaky_relu(x, LRELU_SLOPE)
            xt = c1(xt)
            xt = F.leaky_relu(xt, LRELU_SLOPE)
            xt = c2(xt)
            x = xt + x
        return x

    def remove_weight_norm(self):
        for layer in self.convs1:
            remove_weight_norm(layer)
        for layer in self.convs2:
            remove_weight_norm(layer)


class ResBlock2(torch.nn.Module):
    def __init__(self, config: BaseConfig, channels, kernel_size=3, dilation=(1, 3)):
        super(ResBlock2, self).__init__()
        self.config = config
        self.convs = nn.ModuleList(
            [
                weight_norm(
                    Conv1d(
                        channels,
                        channels,
                        kernel_size,
                        1,
                        dilation=dilation[0],
                        padding=get_padding(kernel_size, dilation[0]),
                    )
                ),
                weight_norm(
                    Conv1d(
                        channels,
                        channels,
                        kernel_size,
                        1,
                        dilation=dilation[1],
                        padding=get_padding(kernel_size, dilation[1]),
                    )
                ),
            ]
        )
        self.convs.apply(init_weights)

    def forward(self, x):
        for c in self.convs:
            xt = F.leaky_relu(x, LRELU_SLOPE)
            xt = c(xt)
            x = xt + x
        return x

    def remove_weight_norm(self):
        for layer in self.convs:
            remove_weight_norm(layer)


class Generator(torch.nn.Module):
    def __init__(self, config: BaseConfig):
        super(Generator, self).__init__()
        self.config = config
        self.model_vocoder_config = config["model"]["vocoder"]
        self.num_kernels = len(self.model_vocoder_config["resblock_kernel_sizes"])
        self.num_upsamples = len(self.model_vocoder_config["upsample_rates"])
        self.conv_pre = weight_norm(
            Conv1d(
                self.config["preprocessing"]["audio"]["n_mels"],
                self.model_vocoder_config["upsample_initial_channel"],
                7,
                1,
                padding=3,
            )
        )
        resblock = (
            ResBlock1 if self.model_vocoder_config["resblock"] == "1" else ResBlock2
        )

        self.ups = nn.ModuleList()
        for i, (u, k) in enumerate(
            zip(
                self.model_vocoder_config["upsample_rates"],
                self.model_vocoder_config["upsample_kernel_sizes"],
            )
        ):
            self.ups.append(
                weight_norm(
                    ConvTranspose1d(
                        self.model_vocoder_config["upsample_initial_channel"]
                        // (2**i),
                        self.model_vocoder_config["upsample_initial_channel"]
                        // (2 ** (i + 1)),
                        k,
                        u,
                        padding=(k - u) // 2,
                    )
                )
            )

        self.resblocks = nn.ModuleList()
        for i in range(len(self.ups)):
            ch = self.model_vocoder_config["upsample_initial_channel"] // (2 ** (i + 1))
            for k, d in zip(
                self.model_vocoder_config["resblock_kernel_sizes"],
                self.model_vocoder_config["resblock_dilation_sizes"],
            ):
                self.resblocks.append(resblock(self.config, ch, k, d))

        self.conv_post = weight_norm(Conv1d(ch, 1, 7, 1, padding=3))
        self.ups.apply(init_weights)
        self.conv_post.apply(init_weights)

    def forward(self, x):
        x = self.conv_pre(x)
        for i in range(self.num_upsamples):
            x = F.leaky_relu(x, LRELU_SLOPE)
            x = self.ups[i](x)
            xs = None
            for j in range(self.num_kernels):
                if xs is None:
                    xs = self.resblocks[i * self.num_kernels + j](x)
                else:
                    xs += self.resblocks[i * self.num_kernels + j](x)
            x = xs / self.num_kernels
        x = F.leaky_relu(x)
        x = self.conv_post(x)
        x = torch.tanh(x)

        return x

    def remove_weight_norm(self):
        print("Removing weight norm...")
        for layer in self.ups:
            remove_weight_norm(layer)
        for layer in self.resblocks:
            layer.remove_weight_norm()
        remove_weight_norm(self.conv_pre)
        remove_weight_norm(self.conv_post)


class DiscriminatorP(torch.nn.Module):
    def __init__(self, period, kernel_size=5, stride=3, use_spectral_norm=False):
        super(DiscriminatorP, self).__init__()
        self.period = period
        norm_f = weight_norm if use_spectral_norm is False else spectral_norm
        self.convs = nn.ModuleList(
            [
                norm_f(
                    Conv2d(
                        1,
                        32,
                        (kernel_size, 1),
                        (stride, 1),
                        padding=(get_padding(5, 1), 0),
                    )
                ),
                norm_f(
                    Conv2d(
                        32,
                        128,
                        (kernel_size, 1),
                        (stride, 1),
                        padding=(get_padding(5, 1), 0),
                    )
                ),
                norm_f(
                    Conv2d(
                        128,
                        512,
                        (kernel_size, 1),
                        (stride, 1),
                        padding=(get_padding(5, 1), 0),
                    )
                ),
                norm_f(
                    Conv2d(
                        512,
                        1024,
                        (kernel_size, 1),
                        (stride, 1),
                        padding=(get_padding(5, 1), 0),
                    )
                ),
                norm_f(Conv2d(1024, 1024, (kernel_size, 1), 1, padding=(2, 0))),
            ]
        )
        self.conv_post = norm_f(Conv2d(1024, 1, (3, 1), 1, padding=(1, 0)))

    def forward(self, x):
        fmap = []

        # 1d to 2d
        b, c, t = x.shape
        if t % self.period != 0:  # pad first
            n_pad = self.period - (t % self.period)
            x = F.pad(x, (0, n_pad), "reflect")
            t = t + n_pad
        x = x.view(b, c, t // self.period, self.period)

        for layer in self.convs:
            x = layer(x)
            x = F.leaky_relu(x, LRELU_SLOPE)
            fmap.append(x)
        x = self.conv_post(x)
        fmap.append(x)
        x = torch.flatten(x, 1, -1)

        return x, fmap


class MultiPeriodDiscriminator(torch.nn.Module):
    def __init__(self):
        super(MultiPeriodDiscriminator, self).__init__()
        self.discriminators = nn.ModuleList(
            [
                DiscriminatorP(2),
                DiscriminatorP(3),
                DiscriminatorP(5),
                DiscriminatorP(7),
                DiscriminatorP(11),
            ]
        )

    def forward(self, y, y_hat):
        y_d_rs = []
        y_d_gs = []
        fmap_rs = []
        fmap_gs = []
        for d in self.discriminators:
            y_d_r, fmap_r = d(y)
            y_d_g, fmap_g = d(y_hat)
            y_d_rs.append(y_d_r)
            fmap_rs.append(fmap_r)
            y_d_gs.append(y_d_g)
            fmap_gs.append(fmap_g)

        return y_d_rs, y_d_gs, fmap_rs, fmap_gs


class DiscriminatorS(torch.nn.Module):
    def __init__(self, use_spectral_norm=False):
        super(DiscriminatorS, self).__init__()
        norm_f = weight_norm if use_spectral_norm is False else spectral_norm
        self.convs = nn.ModuleList(
            [
                norm_f(Conv1d(1, 128, 15, 1, padding=7)),
                norm_f(Conv1d(128, 128, 41, 2, groups=4, padding=20)),
                norm_f(Conv1d(128, 256, 41, 2, groups=16, padding=20)),
                norm_f(Conv1d(256, 512, 41, 4, groups=16, padding=20)),
                norm_f(Conv1d(512, 1024, 41, 4, groups=16, padding=20)),
                norm_f(Conv1d(1024, 1024, 41, 1, groups=16, padding=20)),
                norm_f(Conv1d(1024, 1024, 5, 1, padding=2)),
            ]
        )
        self.conv_post = norm_f(Conv1d(1024, 1, 3, 1, padding=1))

    def forward(self, x):
        fmap = []
        for layer in self.convs:
            x = layer(x)
            x = F.leaky_relu(x, LRELU_SLOPE)
            fmap.append(x)
        x = self.conv_post(x)
        fmap.append(x)
        x = torch.flatten(x, 1, -1)

        return x, fmap


class MultiScaleDiscriminator(torch.nn.Module):
    def __init__(self):
        super(MultiScaleDiscriminator, self).__init__()
        self.discriminators = nn.ModuleList(
            [
                DiscriminatorS(use_spectral_norm=True),
                DiscriminatorS(),
                DiscriminatorS(),
            ]
        )
        self.meanpools = nn.ModuleList(
            [AvgPool1d(4, 2, padding=2), AvgPool1d(4, 2, padding=2)]
        )

    def forward(self, y, y_hat):
        y_d_rs = []
        y_d_gs = []
        fmap_rs = []
        fmap_gs = []
        for i, d in enumerate(self.discriminators):
            if i != 0:
                y = self.meanpools[i - 1](y)
                y_hat = self.meanpools[i - 1](y_hat)
            y_d_r, fmap_r = d(y)
            y_d_g, fmap_g = d(y_hat)
            y_d_rs.append(y_d_r)
            fmap_rs.append(fmap_r)
            y_d_gs.append(y_d_g)
            fmap_gs.append(fmap_g)

        return y_d_rs, y_d_gs, fmap_rs, fmap_gs


class HiFiGAN(pl.LightningModule):
    def __init__(self, config: BaseConfig):
        super().__init__()
        self.config = config
        self.mpd = MultiPeriodDiscriminator()
        self.msd = MultiScaleDiscriminator()
        self.generator = Generator(config)
        self.save_hyperparameters()
        # TODO: figure out continue from checkpoint
        # TODO: figure out multiple nodes/gpus: https://pytorch-lightning.readthedocs.io/en/1.4.0/advanced/multi_gpu.html

    def forward(self, x):
        return self.generator(x)

    def configure_optimizers(self):
        optim_g = torch.optim.AdamW(
            self.generator.parameters(),
            self.config["training"]["vocoder"]["learning_rate"],
            betas=[
                self.config["training"]["vocoder"]["adam_b1"],
                self.config["training"]["vocoder"]["adam_b2"],
            ],
        )
        optim_d = torch.optim.AdamW(
            itertools.chain(self.msd.parameters(), self.mpd.parameters()),
            self.config["training"]["vocoder"]["learning_rate"],
            betas=[
                self.config["training"]["vocoder"]["adam_b1"],
                self.config["training"]["vocoder"]["adam_b2"],
            ],
        )
        scheduler_g = torch.optim.lr_scheduler.ExponentialLR(
            optim_g, gamma=self.config["training"]["vocoder"]["lr_decay"]
        )
        scheduler_d = torch.optim.lr_scheduler.ExponentialLR(
            optim_d, gamma=self.config["training"]["vocoder"]["lr_decay"]
        )
        return [optim_g, optim_d], [scheduler_g, scheduler_d]

    def feature_loss(self, fmap_r, fmap_g):
        loss = 0
        for dr, dg in zip(fmap_r, fmap_g):
            for rl, gl in zip(dr, dg):
                loss += torch.mean(torch.abs(rl - gl))

        return loss * 2

    def discriminator_loss(self, disc_real_outputs, disc_generated_outputs):
        loss = 0
        r_losses = []
        g_losses = []
        for dr, dg in zip(disc_real_outputs, disc_generated_outputs):
            r_loss = torch.mean((1 - dr) ** 2)
            g_loss = torch.mean(dg**2)
            loss += r_loss + g_loss
            r_losses.append(r_loss.item())
            g_losses.append(g_loss.item())

        return loss, r_losses, g_losses

    def generator_loss(self, disc_outputs):
        g_loss = 0
        gen_losses = []
        for dg in disc_outputs:
            loss = torch.mean((1 - dg) ** 2)
            gen_losses.append(loss)
            g_loss += loss

        return (g_loss,)

    def training_step(self, batch, batch_idx, optimizer_idx):
        x, y, _, y_mel = batch
        # y = y.unsqueeze(1) # TODO: is this needed?
        # train generator
        if optimizer_idx == 0:
            # generate waveform
            self.generated_wav = self(x)
            # create mel
            generated_mel_spec = self.generated_wav  # TODO: pass this through mel spec
            # calculate loss
            y_df_hat_r, y_df_hat_g, fmap_f_r, fmap_f_g = self.mpd(y, self.generated_wav)
            y_ds_hat_r, y_ds_hat_g, fmap_s_r, fmap_s_g = self.msd(y, self.generated_wav)
            loss_fm_f = self.feature_loss(fmap_f_r, fmap_f_g)
            loss_fm_s = self.feature_loss(fmap_s_r, fmap_s_g)
            loss_gen_f, _ = self.generator_loss(y_df_hat_g)
            loss_gen_s, _ = self.generator_loss(y_ds_hat_g)
            loss_mel = F.l1_loss(y_mel, generated_mel_spec) * 45
            result = loss_gen_s + loss_gen_f + loss_fm_s + loss_fm_f + loss_mel
            # log generator loss
            self.log("g_loss", result, prog_bar=True)

        # train discriminators
        if optimizer_idx == 1:
            y_g_hat = self(x)
            # MPD
            y_df_hat_r, y_df_hat_g, _, _ = self.mpd(y, y_g_hat.detach())
            loss_disc_f, _, _ = self.discriminator_loss(y_df_hat_r, y_df_hat_g)

            # MSD
            y_ds_hat_r, y_ds_hat_g, _, _ = self.msd(y, y_g_hat.detach())
            loss_disc_s, _, _ = self.discriminator_loss(y_ds_hat_r, y_ds_hat_g)
            # calculate loss
            result = loss_disc_s + loss_disc_f
            # log discriminator loss
            self.log("d_loss", result, prog_bar=True)
        return result

    def validation_step(self, batch, batch_idx):
        x, y, _, y_mel = batch
        # generate waveform
        self.generated_wav = self(x)
        # create mel
        generated_mel_spec = self.generated_wav  # TODO: pass this through mel spec
        val_err_tot = F.l1_loss(y_mel, generated_mel_spec).item()
        # # TODO: Log audio and mel spec
        # # Below is taken from HiFiGAN
        # sw.add_audio('gt/y_{}'.format(j), y[0], steps, h.sampling_rate)
        #                             sw.add_figure('gt/y_spec_{}'.format(j), plot_spectrogram(x[0]), steps)

        #                         sw.add_audio('generated/y_hat_{}'.format(j), y_g_hat[0], steps, h.sampling_rate)
        #                         y_hat_spec = mel_spectrogram(y_g_hat.squeeze(1), h.n_fft, h.num_mels,
        #                                                      h.sampling_rate, h.hop_size, h.win_size,
        #                                                      h.fmin, h.fmax)
        #                         sw.add_figure('generated/y_hat_spec_{}'.format(j),
        #                                       plot_spectrogram(y_hat_spec.squeeze(0).cpu().numpy()), steps)
        # Log mel loss
        self.log("val_mel_loss", val_err_tot, prog_bar=True)