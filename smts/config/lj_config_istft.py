"""These are the Base model hyperparameters.

   TODO: Add intellisense (maybe add all keys as attributes)
   TODO: Give examples of creating alternate configurations
   TODO: Give examples of changing hyperparameters in CLI
"""

from copy import deepcopy
from datetime import datetime
from string import ascii_lowercase, ascii_uppercase

from smts.utils import (
    collapse_whitespace,
    generic_dict_loader,
    load_lj_metadata_hifigan,
    lower,
    nfc_normalize,
    original_hifigan_leaky_relu,
    rel_path_to_abs_path,
    update_config,
)

#########################
#                       #
#         MODEL         #
#    HYPERPARAMETERS    #
#                       #
#########################

BASE_MODEL_HPARAMS = {
    "encoder": {
        "encoder_layer": 4,
        "num_phon_feats": 37
        # etc...
    },
    "decoder": {},
    "variance_predictor": {
        # etc..
    },
    "vocoder": {
        "resblock": "1",
        "upsample_rates": [
            8,
            8,
        ],  # 8, 8, 2, 2 preserves input sampling rate. 8, 8, 4, 2 doubles it for example.
        "upsample_kernel_sizes": [
            16,
            16,
        ],  # must not be less than upsample rate, and must be evenly divisible by upsample rate
        "upsample_initial_channel": 512,
        "resblock_kernel_sizes": [3, 7, 11],
        "resblock_dilation_sizes": [[1, 3, 5], [1, 3, 5], [1, 3, 5]],
        "depthwise_separable_convolutions": {
            "generator": False,
        },
        "activation_function": original_hifigan_leaky_relu,  # for original implementation use utils.original_hifigan_leaky_relu,
        "istft_layer": True,  # Uses C8C8I model https://arxiv.org/pdf/2203.02395.pdf - must change upsample rates and upsample_kernel_sizes appropriately.
    },
    "use_postnet": True,
    "max_seq_len": 1000,
    "multilingual": True,
    "multispeaker": {
        # etc...
    },
}

#########################
#                       #
#       TRAINING        #
#    HYPERPARAMETERS    #
#                       #
#########################

BASE_TRAINING_HPARAMS = {
    "strategy": "vocoder",  # feature_prediction (FS2), vocoder (HiFiGAN), e2e (FS2 + HiFiGAN)
    "train_split": 0.9,  # the rest is val
    "batch_size": 64,
    "train_data_workers": 4,
    "val_data_workers": 1,
    "logger": {  # Uses Tensorboard
        "name": "LJ",
        "save_dir": rel_path_to_abs_path("./logs"),
        "sub_dir": str(int(datetime.today().timestamp())),
        "version": "istft",
    },
    "feature_prediction": {
        "filelist": rel_path_to_abs_path("./preprocessed/LJ/preprocessed_filelist.psv"),
        "filelist_loader": generic_dict_loader,
        "steps": {
            "total": 300000,
            "log": 100,
            "val": 1000,
            "save": 100000,
        },
        "optimizer": {
            # etc....
        },
        "freeze_layers": {
            "encoder": False,
            "decoder": False,
            "postnet": False,
            "variance": {"energy": False, "duration": False, "pitch": False},
        },
    },
    "vocoder": {
        "filelist": rel_path_to_abs_path("./preprocessed/LJ/preprocessed_filelist.psv"),
        "finetune_checkpoint": "",
        # "finetune_checkpoint": rel_path_to_abs_path(
        #     "./logs/LJ/istft/checkpoints/last.ckpt"
        # ),
        "filelist_loader": generic_dict_loader,
        "resblock": "1",
        "learning_rate": 0.0002,
        "adam_b1": 0.8,
        "adam_b2": 0.99,
        "lr_decay": 0.999,
        "seed": 1234,
        "freeze_layers": {"mpd": False, "msd": False, "generator": False},
        "max_epochs": 1000,
        "save_top_k_ckpts": 5,
        "ckpt_steps": None,
        "ckpt_epochs": 1,
        "generator_warmup": 0,
        "gan_type": "wgan",  # original, wgan, wgan-gp
        "gan_optimizer": "rmsprop",  # adam, rmsprop
        "wgan_clip_value": 0.01,
        "use_weighted_sampler": False,
    },
}

#########################
#                       #
#     PREPROCESSING     #
#    HYPERPARAMETERS    #
#                       #
#########################

# These effects are applied to the audio during preprocessing
SOX_EFFECTS = [
    ["channels", "1"],  # convert to mono
    ["rate", "16000"],  # resample
    ["norm", "-3.0"],  # normalize to -3 dB
    [
        "silence",
        "1",  # Above periods silence; ie. allow 1 second of silence at beginning
        "0.1",  # Above periods silence duration
        "1.0%",  # Above periods silence threshold
        "-1",  # See https://linux.die.net/man/1/sox#:~:text=To%20remove%20silence,of%20the%20audio.
        "0.1",  # Below periods silence duration
        "1.0%",  # Below periods silence threshold
    ],  # remove silence throughout the file
]

BASE_PREPROCESSING_HPARAMS = {
    "dataset": "LJ",
    "source_data": [
        {
            "name": "LJ",
            "data_dir": "/home/aip000/tts/corpora/Speech/LJ.Speech.Dataset/LJSpeech-1.1/wavs",
            "filelist_loader": load_lj_metadata_hifigan,
            "filelist": rel_path_to_abs_path("./filelists/lj_full.psv"),
            "sox_effects": SOX_EFFECTS,
        }
    ],
    "save_dir": rel_path_to_abs_path("./preprocessed/LJ"),
    "f0_phone_averaging": True,
    "energy_phone_averaging": True,
    "f0_type": "torch",  # pyworld | kaldi (torchaudio) | cwt (continuous wavelet transform)
    "value_separator": "--",  # used to separate basename from speaker, language, type etc in preprocessed filename
    "audio": {
        "min_audio_length": 0.25,  # seconds
        "max_audio_length": 11,  # seconds
        "max_wav_value": 32768.0,
        "norm_db": -3.0,
        "sil_threshold": 1.0,
        "sil_duration": 0.1,
        "input_sampling_rate": 22050,  # Sampling rate to ensure audio input to vocoder (output spec from feature prediction) is sampled at
        "output_sampling_rate": 22050,  # Sampling rate to ensure audio output of vocoder is sampled at
        "target_bit_depth": 16,
        "alignment_sampling_rate": 22050,  # Sampling rate from TextGrids. These two sampling rates *should* be the same, but they are separated in case it's not practical for your data
        "alignment_bit_depth": 16,
        "fft_window_frames": 1024,  # set this to the input sampling rate
        "fft_hop_frames": 256,  # set this to the input sampling rate
        "f_min": 0,
        "f_max": 8000,
        "n_fft": 1024,  # set this to the input sampling rate
        "n_mels": 80,
        "spec_type": "mel-librosa",  # mel-torch or mel-librosa (real) | linear (real) | raw (complex) see https://pytorch.org/audio/stable/tutorials/audio_feature_extractions_tutorial.html#overview-of-audio-features
        "vocoder_segment_size": 8192,  # this is the size of the segments taken for training HiFI-GAN. set proportional to output sampling rate; 8192 is for output of 22050Hz. This should be a multiple of the upsample hop size which itself is equal to the product of the upsample rates.
    },
}

#########################
#                       #
#   TEXT CONFIGURATION  #
#                       #
#########################


# These values can be overwritten, and the keys are not specifically named,
# so you can add other keys to this dictionary (i.e. "ipa_characters" or other such key names)
# the value of each key here will be turned into a list, so make sure your symbol definitions
# are iterable. And, make sure that if you have digraphs/multigraphs, that they are defined as
# a list of strings.
# Note there is a limit with MLFlow for 250 characters per category: https://github.com/mlflow/mlflow/issues/6183
SYMBOLS = {
    "silence": ["<SIL>"],
    "pad": "_",
    "punctuation": ';:,.!?¡¿—…"«»“” ',
    "lowercase_letters": list(ascii_lowercase),
    "uppercase_letters": list(ascii_uppercase),
}

# Cleaners are defined in the configuration as opposed to editing a cleaners.py file somewhere else.
# Functions are applied to text in sequence.
# Unfortunately, you can't use lambda functions, because PyTorch doesn't support it. See https://github.com/pytorch/pytorch/issues/13300
CLEANERS = [lower, collapse_whitespace, nfc_normalize]


class BaseConfig(dict):
    def __init__(self, *args, **kwargs):
        # Allow BaseConfig to be initialized with values that override the defaults
        # pass by value to not change base hparams
        base = {
            "model": deepcopy(BASE_MODEL_HPARAMS),
            "training": deepcopy(BASE_TRAINING_HPARAMS),
            "preprocessing": deepcopy(BASE_PREPROCESSING_HPARAMS),
            "text": {"symbols": deepcopy(SYMBOLS), "cleaners": CLEANERS},
        }
        # update from kwargs
        config = update_config(base, kwargs)
        # then iter through and update from each arg
        for arg in args:
            if isinstance(arg, dict):
                config = update_config(config, arg)
            else:
                raise ValueError(
                    "Hm, you tried to update the config with an argument that was not a dictionary, please re-formulate"
                )
        super().__init__(*args, **config)