from enum import Enum
from pathlib import Path
from typing import Annotated, List, Optional, Union

from annotated_types import Ge, Le
from pydantic import Field, FilePath, ValidationInfo, model_validator

from everyvoice.config.shared_types import ConfigModel, PartialLoadConfig, init_context
from everyvoice.config.utils import (
    PossiblyRelativePath,
    PossiblyRelativePathMustExist,
    PossiblySerializedCallable,
    load_partials,
)
from everyvoice.utils import generic_dict_loader, load_config_from_json_or_yaml_path


class DatasetTextRepresentation(str, Enum):
    characters = "characters"
    ipa_phones = "ipa_phones"
    arpabet = "arpabet"  # always gets mapped to phones


class AudioSpecTypeEnum(str, Enum):
    mel = "mel"  # TorchAudio implementation
    mel_librosa = "mel-librosa"  # Librosa implementation
    linear = "linear"  # TorchAudio Linear Spectrogram
    raw = "raw"  # TorchAudio Complex Spectrogram


class AudioConfig(ConfigModel):
    min_audio_length: float = Field(
        0.4,
        description="The minimum length of an audio sample in seconds. Audio shorter than this will be ignored during preprocessing.",
    )
    max_audio_length: float = Field(
        11.0,
        description="The maximum length of an audio sample in seconds. Audio longer than this will be ignored during preprocessing. Increasing the max_audio_length will result in larger memory usage. If you are running out of memory, consider lowering the max_audio_length.",
    )
    max_wav_value: float = Field(
        32767.0,
        description="Advanced. The maximum value allowed to be in your wav files. For 16-bit audio, this should be (2**16)/2 - 1.",
    )
    input_sampling_rate: int = Field(
        22050,
        description="The sampling rate describes the number of samples per second of audio. The 'input_sampling_rate' is with respect to your vocoder, or spec-to-wav model. This means that the spectrograms predicted by your text-to-spec model will also be calculated from audio at this sampling rate. If you change this value, your audio will automatically be re-sampled during preprocessing.",
    )
    output_sampling_rate: int = Field(
        22050,
        description="Advanced. The sampling rate describes the number of samples per second of audio. The 'output_sampling_rate' is with respect to your vocoder, or spec-to-wav model. This means that the wav files generated by your vocoder or spec-to-wav model will be at this sampling rate. If you change this value, you will also need to change the upsample rates in your vocoder. Your audio will automatically be re-sampled during preprocessing.",
    )
    alignment_sampling_rate: int = Field(
        22050,
        description="Advanced. The sampling rate describes the number of samples per second of audio. The 'alignment_sampling_rate' describes the sampling rate used when training an alignment model. If you change this value, your audio will automatically be re-sampled during preprocessing.",
    )
    target_bit_depth: int = Field(
        16,
        description="Advanced. This is the bit depth of each sample in your audio files.",
    )
    n_fft: int = Field(
        1024,
        title="FFT Size",
        description="Advanced. This is the number of bins used by the Fast Fourier Transform (FFT).",
    )
    fft_window_size: int = Field(
        1024,
        title="FFT Window Size",
        description="Advanced. This is the window size used by the Fast Fourier Transform (FFT).",
    )
    fft_hop_size: int = Field(
        256,
        title="FFT Hop Size",
        description="Advanced. This is the hop size for calculating the Short-Time Fourier Transform (STFT) which calculates a sequence of spectrograms from a single audio file. Another way of putting it is that the hop size is equal to the amount of non-intersecting samples from the audio in each spectrogram.",
    )
    f_min: int = Field(
        0,
        title="Minimum Frequency",
        description="Advanced. This is the minimum frequency for the lowest frequency bin when calculating the spectrogram.",
    )
    f_max: int = Field(
        8000,
        title="Maximum Frequency",
        description="Advanced. This is the maximum frequency for the highest frequency bin when calculating the spectrogram.",
    )
    n_mels: int = Field(
        80,
        title="Number of Mel bins",
        description="Advanced. This is the number of filters in the Mel-scale spaced filterbank.",
    )
    spec_type: Union[AudioSpecTypeEnum, str] = Field(
        AudioSpecTypeEnum.mel_librosa.value,
        description="Advanced. Defines how to calculate the spectrogram. 'mel' uses the TorchAudio implementation for a Mel spectrogram. 'mel-librosa' uses Librosa's implementation. 'linear' calculates a non-Mel linear spectrogram and 'raw' calculates a complex-valued spectrogram. 'linear' and 'raw' are not currently supported by EveryVoice. We recommend using 'mel-librosa'.",
    )
    vocoder_segment_size: int = Field(
        8192,
        description="Advanced. The vocoder, or spec-to-wav model is trained by sampling random fixed-size sections of the audio. This value specifies the number of samples in those sections.",
    )


class Dataset(PartialLoadConfig):
    dataset_text_representation: DatasetTextRepresentation = Field(
        DatasetTextRepresentation.characters,
        description="The level of representation used in the text of your Dataset.",
    )
    label: str = Field("YourDataSet", description="A label for the source of data")
    data_dir: PossiblyRelativePath = Field(
        Path("/please/create/a/path/to/your/dataset/data"),
        description="The path to the directory with your audio files.",
    )
    filelist: PossiblyRelativePath = Field(
        Path("/please/create/a/path/to/your/dataset/filelist"),
        description="The path to your dataset's filelist.",
    )
    filelist_loader: PossiblySerializedCallable = Field(
        generic_dict_loader,
        description="Advanced. The file-loader function to use to load your dataset's filelist.",
    )
    sox_effects: list = Field(
        [["channels", "1"]],
        description="Advanced. A list of SoX effects to apply to your audio prior to preprocessing. Run python -c 'import torchaudio; print(torchaudio.sox_effects.effect_names())' to see a list of supported effects.",
    )


class PreprocessingConfig(PartialLoadConfig):
    dataset: str = Field("YourDataSet", description="The name of the dataset.")
    train_split: Annotated[float, Ge(0.0), Le(1.0)] = Field(
        0.9,
        description="The amount of the dataset to use for training. The rest will be used as validation. Hold some of the validation set out for a test set if you are performing experiments.",
    )
    dataset_split_seed: int = Field(
        1234,
        description="The seed to use when splitting the dataset into train and validation sets.",
    )
    save_dir: PossiblyRelativePathMustExist = Field(
        Path("./preprocessed/YourDataSet"),
        description="The directory to save preprocessed files to.",
    )
    audio: AudioConfig = Field(
        default_factory=AudioConfig,
        description="Configuration settings for audio.",
    )
    path_to_audio_config_file: Optional[FilePath] = Field(
        None, description="The path to an audio configuration file."
    )
    source_data: List[Dataset] = Field(
        default_factory=lambda: [Dataset()],
        description="A list of datasets.",
    )

    @model_validator(mode="before")  # type: ignore
    def load_partials(self, info: ValidationInfo):
        config_path = (
            info.context.get("config_path", None) if info.context is not None else None
        )
        return load_partials(
            self,  # type: ignore
            ("audio",),
            config_path=config_path,
        )

    @staticmethod
    def load_config_from_path(path: Path) -> "PreprocessingConfig":
        """Load a config from a path"""
        config = load_config_from_json_or_yaml_path(path)
        with init_context({"config_path": path}):
            config = PreprocessingConfig(**config)
        return config
